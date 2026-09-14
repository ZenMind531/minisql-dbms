"""Executor：把 Logical Plan 跑成结果（T031）。

四种计划各有出口：

    CreateTable            → "OK"
    Insert                 → "N row(s) inserted"
    Delete                 → "N row(s) deleted"
    Project/Filter/SeqScan → list[tuple]（已过滤、已投影）

表达式求值集中在 ``_evaluate``：行 + 表达式 → 值。它只认 tuple 和 AST，
不碰页、不碰字节——那些活在 StorageEngine 那一层。
"""

from __future__ import annotations

import operator
from typing import TYPE_CHECKING, Any, Callable, Iterator, TypeAlias

from database_system.engine.storage_engine import StorageEngine
from database_system.sql_compiler.ast_nodes import (
    BinaryExpr, BinaryOperator, Expr, IdentifierExpr, LiteralExpr, UnaryExpr,
    UnaryOperator,
)
from database_system.sql_compiler.catalog import Catalog, TableSchema
from database_system.sql_compiler.planner import (
    CreateTable, Delete, Filter, Insert, PlanNode, Project, SeqScan,
    ShowDatabases, ShowTables, Sort,
)
from database_system.utils.errors import ExecError

if TYPE_CHECKING:
    from database_system.engine.catalog_manager import CatalogManager

Result: TypeAlias = str | list[tuple]

_ARITHMETIC = {
    BinaryOperator.ADD: operator.add,
    BinaryOperator.SUBTRACT: operator.sub,
    BinaryOperator.MULTIPLY: operator.mul,
}
_COMPARISON = {
    BinaryOperator.EQUAL: operator.eq,
    BinaryOperator.NOT_EQUAL: operator.ne,
    BinaryOperator.GREATER_THAN: operator.gt,
    BinaryOperator.GREATER_THAN_OR_EQUAL: operator.ge,
    BinaryOperator.LESS_THAN: operator.lt,
    BinaryOperator.LESS_THAN_OR_EQUAL: operator.le,
}


def _column_index(schema: TableSchema) -> dict[str, int]:
    """列名 → 行内下标。求值时靠它把 IdentifierExpr 变成 row[i]。"""
    return {column.name: position for position, column in enumerate(schema.columns)}


def _evaluate(expr: Expr, row: tuple | None, index: dict[str, int]) -> Any:
    """按行求值一个表达式；INSERT 的 VALUES 没有源行，此时 row 为 None。"""
    if isinstance(expr, LiteralExpr):
        return expr.value
    if isinstance(expr, IdentifierExpr):
        if row is None:
            raise ExecError(f"列 '{expr.name}' 在此处不能取值",
                            line=expr.line, column=expr.column)
        return row[index[expr.name]]
    if isinstance(expr, UnaryExpr):
        value = _evaluate(expr.operand, row, index)
        if expr.op is UnaryOperator.NOT:
            return not value
        if expr.op is UnaryOperator.MINUS:
            return -value
        return value
    if isinstance(expr, BinaryExpr):
        return _evaluate_binary(expr, row, index)
    raise ExecError(f"不支持的表达式: {type(expr).__name__}",
                    line=expr.line, column=expr.column)


def _evaluate_binary(expr: BinaryExpr, row: tuple | None,
                     index: dict[str, int]) -> Any:
    op = expr.op
    # AND / OR 短路求值：右边不一定要算
    if op is BinaryOperator.AND:
        return (bool(_evaluate(expr.left, row, index))
                and bool(_evaluate(expr.right, row, index)))
    if op is BinaryOperator.OR:
        return (bool(_evaluate(expr.left, row, index))
                or bool(_evaluate(expr.right, row, index)))

    left = _evaluate(expr.left, row, index)
    right = _evaluate(expr.right, row, index)
    if op is BinaryOperator.DIVIDE:
        if right == 0:
            raise ExecError("除数为零", line=expr.line, column=expr.column)
        return int(left / right)  # INT / INT → INT，向零截断

    handler = _ARITHMETIC.get(op) or _COMPARISON.get(op)
    if handler is None:
        raise ExecError(f"不支持的运算符: {op}", line=expr.line, column=expr.column)
    return handler(left, right)


def _base_table(plan: PlanNode) -> str:
    """顺着 child 往下找到 SeqScan，取出这次查询的表名。"""
    while not isinstance(plan, SeqScan):
        plan = plan.child
    return plan.table


class Executor:
    def __init__(
        self,
        engine: StorageEngine,
        catalog: Catalog,
        catalog_manager: CatalogManager | None = None,
    ):
        self.engine = engine
        self.catalog = catalog
        self.catalog_manager = catalog_manager

    # ---------- 入口 ----------
    def execute(self, plan: PlanNode) -> Result:
        if isinstance(plan, CreateTable):
            return self._create_table(plan)
        if isinstance(plan, Insert):
            return self._insert(plan)
        if isinstance(plan, Delete):
            return self._delete(plan)
        if isinstance(plan, ShowDatabases):
            return [(self.engine.data_dir.name or str(self.engine.data_dir),)]
        if isinstance(plan, ShowTables):
            return [(name,) for name in self.catalog.table_names(include_system=False)]
        return self._select(plan)

    # ---------- 四种计划 ----------
    def _create_table(self, plan: CreateTable) -> str:
        # 先借 Catalog 的规则做纯校验：不过就不碰磁盘，不会留下半个表
        Catalog().create_table(plan.table, plan.schema)
        schema = TableSchema(name=plan.table, columns=list(plan.schema))
        if self.catalog_manager is None:
            self.engine.create_table(schema)
            self.catalog.create_table(plan.table, plan.schema)
        else:
            self.catalog_manager.create_table(schema, self.catalog)
        return "OK"

    def _insert(self, plan: Insert) -> str:
        schema = self._require_table(plan.table)
        index = _column_index(schema)
        inserted = 0
        for values in plan.rows:
            row = tuple(_evaluate(value, None, index) for value in values)
            self.engine.insert_row(plan.table, row)
            inserted += 1
        return f"{inserted} row(s) inserted"

    def _delete(self, plan: Delete) -> str:
        schema = self._require_table(plan.table)
        index = _column_index(schema)
        deleted = self.engine.delete_where(plan.table, self._predicate(plan.child, index))
        return f"{deleted} row(s) deleted"

    def _select(self, plan: PlanNode) -> list[tuple]:
        table = _base_table(plan)
        index = _column_index(self._require_table(table))
        return list(self._run(plan, index))

    # ---------- 算子递归 ----------
    def _run(self, plan: PlanNode, index: dict[str, int]) -> Iterator[tuple]:
        if isinstance(plan, SeqScan):
            yield from self.engine.scan(plan.table)
        elif isinstance(plan, Filter):
            for row in self._run(plan.child, index):
                if _evaluate(plan.predicate, row, index):
                    yield row
        elif isinstance(plan, Project):
            if plan.columns is None:  # SELECT *
                yield from self._run(plan.child, index)
            else:
                wanted = [index[name] for name in plan.columns]
                for row in self._run(plan.child, index):
                    yield tuple(row[position] for position in wanted)
        elif isinstance(plan, Sort):
            rows = list(self._run(plan.child, index))
            for item in reversed(plan.items):
                rows.sort(
                    key=lambda row, name=item.column_name: row[index[name]],
                    reverse=item.descending,
                )
            yield from rows
        else:
            raise ExecError(f"不支持的查询计划: {type(plan).__name__}")

    # ---------- 工具 ----------
    @staticmethod
    def _predicate(child: PlanNode, index: dict[str, int]) -> Callable[[tuple], bool]:
        if isinstance(child, Filter):
            return lambda row: bool(_evaluate(child.predicate, row, index))
        return lambda row: True  # 没有 WHERE → 全表删除

    def _require_table(self, table: str) -> TableSchema:
        schema = self.catalog.find_table(table)
        if schema is None:
            raise ExecError(f"表 '{table}' 不存在")
        return schema
