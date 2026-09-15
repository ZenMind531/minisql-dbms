"""Validate statements and annotate expression types before planning.

Analysis never executes statements or changes the supplied Catalog. Bindings
for the most recently analyzed statement are exposed in column_bindings,
keyed by column name; AST column names themselves remain unchanged.
"""

from database_system.sql_compiler.ast_nodes import (
    ASTNode, AggregateExpr, AggregateFunction, Assignment, BinaryExpr,
    BinaryOperator, ColumnDef, CreateTableStmt, DeleteStmt, DropTableStmt, Expr,
    IdentifierExpr, InsertStmt, LiteralExpr, LiteralKind, SelectStmt,
    ShowDatabasesStmt, ShowTablesStmt, Stmt, TypeKind, TypeSpec, UnaryExpr,
    UnaryOperator, UpdateStmt,
)
from database_system.sql_compiler.catalog import Catalog
from database_system.utils.errors import SemanticError


# Central operator rules: (operator, operand kinds) -> result kind.
BINARY_RULES = {}
for _op in (BinaryOperator.ADD, BinaryOperator.SUBTRACT,
            BinaryOperator.MULTIPLY, BinaryOperator.DIVIDE):
    BINARY_RULES[_op, TypeKind.INT, TypeKind.INT] = TypeKind.INT
for _op in (BinaryOperator.EQUAL, BinaryOperator.NOT_EQUAL,
            BinaryOperator.LESS_THAN, BinaryOperator.LESS_THAN_OR_EQUAL,
            BinaryOperator.GREATER_THAN, BinaryOperator.GREATER_THAN_OR_EQUAL):
    for _kind in (TypeKind.INT, TypeKind.VARCHAR):
        BINARY_RULES[_op, _kind, _kind] = TypeKind.BOOL
for _op in (BinaryOperator.EQUAL, BinaryOperator.NOT_EQUAL,
            BinaryOperator.AND, BinaryOperator.OR):
    BINARY_RULES[_op, TypeKind.BOOL, TypeKind.BOOL] = TypeKind.BOOL
UNARY_RULES = {
    (UnaryOperator.PLUS, TypeKind.INT): TypeKind.INT,
    (UnaryOperator.MINUS, TypeKind.INT): TypeKind.INT,
    (UnaryOperator.NOT, TypeKind.BOOL): TypeKind.BOOL,
}


class SemanticAnalyzer:
    def __init__(self, catalog: Catalog):
        self.catalog = catalog
        self.column_bindings: dict[str, ColumnDef] = {}

    @staticmethod
    def _error(node: ASTNode, message: str) -> SemanticError:
        return SemanticError(message, line=node.line, column=node.column)

    def _bind(self, table: str, name: str, node: ASTNode) -> ColumnDef:
        definition = self.catalog.find_column(table, name)
        if definition is None:
            raise self._error(node, f"column '{name}' does not exist in table '{table}'")
        self.column_bindings[name] = definition
        return definition

    def analyze(self, stmt: Stmt) -> Stmt:
        """Return the input statement with resolved types filled in."""
        self.column_bindings.clear()
        if isinstance(stmt, CreateTableStmt):
            if self.catalog.find_table(stmt.table) is not None:
                raise self._error(stmt, f"table '{stmt.table}' already exists")
            # Reuse Catalog's complete schema validation without registering
            # the table in the live catalog (execution owns that side effect).
            Catalog().create_table(stmt.table, stmt.columns)
            return stmt
        if isinstance(stmt, DropTableStmt):
            return self._drop_table(stmt)
        if isinstance(stmt, (ShowDatabasesStmt, ShowTablesStmt)):
            return stmt
        if not isinstance(stmt, (SelectStmt, InsertStmt, DeleteStmt, UpdateStmt)):
            raise self._error(stmt, f"unsupported statement: {type(stmt).__name__}")
        schema = self.catalog.find_table(stmt.table)
        if schema is None:
            raise self._error(stmt, f"table '{stmt.table}' does not exist")
        if isinstance(stmt, InsertStmt):
            self._insert(stmt, schema.columns)
        elif isinstance(stmt, UpdateStmt):
            self._update(stmt, schema.columns)
        elif isinstance(stmt, SelectStmt):
            self._select(stmt, schema.columns)
        elif isinstance(stmt, DeleteStmt):
            if stmt.where is not None:
                result = self._expression(stmt.where, stmt.table)
                if result.kind is not TypeKind.BOOL:
                    raise self._error(stmt.where, "WHERE expression must have BOOL type")
        return stmt

    def _select(self, stmt: SelectStmt, schema_columns: list[ColumnDef]) -> None:
        """Validate SELECT statement with aggregate function support."""
        select_exprs = stmt.select_exprs
        has_aggregate = self._has_aggregates_in_select(select_exprs)

        if stmt.columns is None:
            for col in schema_columns:
                self.column_bindings[col.name] = col
        else:
            for i, col_name in enumerate(stmt.columns):
                if i < len(select_exprs) and isinstance(select_exprs[i], AggregateExpr):
                    continue
                self._bind(stmt.table, col_name, stmt)

        for item in stmt.order_by:
            self._bind(stmt.table, item.column_name, item)

        for expr in select_exprs:
            if isinstance(expr, AggregateExpr):
                self._validate_aggregate(expr, stmt.table)
            else:
                self._expression(expr, stmt.table)

        if has_aggregate or stmt.group_by or stmt.having is not None:
            for col_name in stmt.group_by:
                self._bind(stmt.table, col_name, stmt)

            if stmt.columns is not None:
                for i, col_name in enumerate(stmt.columns):
                    if i >= len(select_exprs):
                        continue
                    expr = select_exprs[i]
                    if isinstance(expr, IdentifierExpr):
                        if col_name not in stmt.group_by:
                            raise self._error(expr, f"column '{col_name}' must appear in GROUP BY or be in aggregate function")

        if stmt.where is not None:
            if self._contains_aggregate_expr(stmt.where):
                raise self._error(stmt.where, "WHERE clause cannot contain aggregate functions; use HAVING instead")
            result = self._expression(stmt.where, stmt.table)
            if result.kind is not TypeKind.BOOL:
                raise self._error(stmt.where, "WHERE expression must have BOOL type")

        if stmt.having is not None:
            if not has_aggregate and not stmt.group_by:
                raise self._error(stmt.having, "HAVING clause requires GROUP BY or aggregate functions in SELECT")
            result = self._expression(stmt.having, stmt.table)
            if result.kind is not TypeKind.BOOL:
                raise self._error(stmt.having, "HAVING expression must have BOOL type")

    def _validate_aggregate(self, expr: AggregateExpr, table: str) -> TypeSpec:
        """Validate aggregate function and return its result type."""
        if expr.argument is None:
            if expr.function is not AggregateFunction.COUNT:
                raise self._error(expr, f"{expr.function.value}(*) is not valid; only COUNT(*) accepts *")
            expr.resolved_type = TypeSpec(TypeKind.INT)
            return expr.resolved_type

        arg_type = self._expression(expr.argument, table)

        if expr.function is AggregateFunction.COUNT:
            result = TypeSpec(TypeKind.INT)
        elif expr.function in (AggregateFunction.SUM, AggregateFunction.AVG):
            if arg_type.kind is not TypeKind.INT:
                raise self._error(expr, f"{expr.function.value} requires INT argument, got {arg_type.kind}")
            result = TypeSpec(TypeKind.INT)
        elif expr.function in (AggregateFunction.MIN, AggregateFunction.MAX):
            result = arg_type
        else:
            raise self._error(expr, f"unknown aggregate function: {expr.function}")

        expr.resolved_type = result
        return result

    def _has_aggregates_in_select(self, select_exprs: list[Expr]) -> bool:
        """Check if SELECT list contains any aggregate functions."""
        return any(isinstance(expr, AggregateExpr) for expr in select_exprs)

    def _contains_aggregate_expr(self, expr: Expr) -> bool:
        """Recursively check if expression contains aggregate functions."""
        if isinstance(expr, AggregateExpr):
            return True
        if isinstance(expr, UnaryExpr):
            return self._contains_aggregate_expr(expr.operand)
        if isinstance(expr, BinaryExpr):
            return self._contains_aggregate_expr(expr.left) or self._contains_aggregate_expr(expr.right)
        return False

    def _drop_table(self, stmt: DropTableStmt) -> DropTableStmt:
        """Validate DROP TABLE statement."""
        if stmt.table == "__catalog__":
            raise self._error(stmt, "cannot drop system catalog table '__catalog__'")
        if self.catalog.find_table(stmt.table) is None:
            raise self._error(stmt, f"table '{stmt.table}' does not exist")
        return stmt

    def _update(self, stmt: UpdateStmt, schema_columns: list[ColumnDef]) -> None:
        """Validate UPDATE statement assignments and WHERE clause."""
        # Check for duplicate column assignments
        seen_columns = set()
        for assignment in stmt.assignments:
            if assignment.column_name in seen_columns:
                raise self._error(assignment, f"duplicate assignment to column '{assignment.column_name}'")
            seen_columns.add(assignment.column_name)
            # Verify column exists and bind it
            target = self._bind(stmt.table, assignment.column_name, assignment)
            # Validate assignment expression type matches column type
            actual = self._expression(assignment.value, stmt.table)
            expected = target.type_spec
            if actual.kind is not expected.kind:
                raise self._error(assignment.value, f"column '{target.name}' expects {expected.kind}, got {actual.kind}")
            if expected.kind is TypeKind.VARCHAR:
                # For string literals, check length constraint
                if isinstance(assignment.value, LiteralExpr) and assignment.value.literal_kind is LiteralKind.STRING:
                    size = len(assignment.value.value.encode("utf-8"))
                    if size > expected.length:
                        raise self._error(assignment.value, f"column '{target.name}' allows {expected.length} UTF-8 bytes, got {size}")
        # Validate WHERE clause if present
        if stmt.where is not None:
            result = self._expression(stmt.where, stmt.table)
            if result.kind is not TypeKind.BOOL:
                raise self._error(stmt.where, "WHERE expression must have BOOL type")

    def _insert(self, stmt: InsertStmt, schema_columns: list[ColumnDef]) -> None:
        targets = schema_columns
        if stmt.columns is not None:
            targets = []
            seen = set()
            for name in stmt.columns:
                if name in seen:
                    raise self._error(stmt, f"duplicate INSERT column '{name}'")
                seen.add(name)
                targets.append(self._bind(stmt.table, name, stmt))
            # There are no NULL values or column defaults in this SQL subset.
            if len(targets) != len(schema_columns):
                raise self._error(stmt, "INSERT must supply every table column; defaults and NULL are unsupported")
        if len(stmt.values) != len(targets):
            raise self._error(stmt, f"INSERT expects {len(targets)} values, got {len(stmt.values)}")
        for value, target in zip(stmt.values, targets):
            self.column_bindings[target.name] = target
            # VALUES has no source row, even if an identifier names a target column.
            actual = self._expression(value, None)
            expected = target.type_spec
            if actual.kind is not expected.kind:
                raise self._error(value, f"column '{target.name}' expects {expected.kind}, got {actual.kind}")
            if expected.kind is TypeKind.VARCHAR:
                # Only string literals produce VARCHAR in the current grammar.
                size = len(value.value.encode("utf-8"))
                if size > expected.length:
                    raise self._error(value, f"column '{target.name}' allows {expected.length} UTF-8 bytes, got {size}")

    def _expression(self, expr: Expr, table: str | None) -> TypeSpec:
        expr.resolved_type = None
        if isinstance(expr, LiteralExpr):
            if expr.literal_kind is LiteralKind.INTEGER:
                result = TypeSpec(TypeKind.INT)
            elif expr.literal_kind is LiteralKind.STRING:
                # TypeSpec represents bounded SQL types (1..255), not literal
                # sizes. Exact byte length is checked separately at assignment.
                result = TypeSpec(TypeKind.VARCHAR, 255)
            else:
                raise self._error(expr, "unsupported FLOAT type")
        elif isinstance(expr, IdentifierExpr):
            if table is None:
                raise self._error(expr, f"column '{expr.name}' cannot be referenced in INSERT VALUES without a source row")
            result = self._bind(table, expr.name, expr).type_spec
        elif isinstance(expr, UnaryExpr):
            operand = self._expression(expr.operand, table)
            kind = UNARY_RULES.get((expr.op, operand.kind))
            if kind is None:
                raise self._error(expr, f"operator {expr.op} does not accept {operand.kind}")
            result = TypeSpec(kind)
        elif isinstance(expr, BinaryExpr):
            left = self._expression(expr.left, table)
            right = self._expression(expr.right, table)
            kind = BINARY_RULES.get((expr.op, left.kind, right.kind))
            if kind is None:
                raise self._error(expr, f"operator {expr.op} does not accept {left.kind} and {right.kind}")
            result = TypeSpec(kind)
        elif isinstance(expr, AggregateExpr):
            result = self._validate_aggregate(expr, table)
        else:
            raise self._error(expr, f"unsupported expression: {type(expr).__name__}")
        expr.resolved_type = result
        return result


__all__ = ["SemanticAnalyzer"]
