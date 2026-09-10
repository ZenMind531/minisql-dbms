"""Validate statements and annotate expression types before planning.

Analysis never executes statements or changes the supplied Catalog. Bindings
for the most recently analyzed statement are exposed in column_bindings,
keyed by column name; AST column names themselves remain unchanged.
"""

from database_system.sql_compiler.ast_nodes import (
    ASTNode, BinaryExpr, BinaryOperator, ColumnDef, CreateTableStmt, DeleteStmt,
    Expr, IdentifierExpr, InsertStmt, LiteralExpr, LiteralKind, SelectStmt,
    ShowDatabasesStmt, ShowTablesStmt, Stmt, TypeKind, TypeSpec, UnaryExpr,
    UnaryOperator,
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
        if isinstance(stmt, (ShowDatabasesStmt, ShowTablesStmt)):
            return stmt
        if not isinstance(stmt, (SelectStmt, InsertStmt, DeleteStmt)):
            raise self._error(stmt, f"unsupported statement: {type(stmt).__name__}")
        schema = self.catalog.find_table(stmt.table)
        if schema is None:
            raise self._error(stmt, f"table '{stmt.table}' does not exist")
        if isinstance(stmt, InsertStmt):
            self._insert(stmt, schema.columns)
        else:
            if isinstance(stmt, SelectStmt):
                names = stmt.columns if stmt.columns is not None else [c.name for c in schema.columns]
                for name in names:
                    self._bind(stmt.table, name, stmt)
                for item in stmt.order_by:
                    self._bind(stmt.table, item.column_name, item)
            if stmt.where is not None:
                result = self._expression(stmt.where, stmt.table)
                if result.kind is not TypeKind.BOOL:
                    raise self._error(stmt.where, "WHERE expression must have BOOL type")
        return stmt

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
        else:
            raise self._error(expr, f"unsupported expression: {type(expr).__name__}")
        expr.resolved_type = result
        return result


__all__ = ["SemanticAnalyzer"]
