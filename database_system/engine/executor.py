"""Executor：把 Logical Plan 跑成结果（T031）。

各计划节点的出口：

    CreateTable / DropTable   → "OK"
    Insert                    → "N row(s) inserted"
    Update                    → "N row(s) updated"
    Delete                    → "N row(s) deleted"
    ShowDatabases / ShowTables→ list[tuple]
    Project/Filter/Sort/Limit
    /SeqScan                  → list[tuple]（已过滤、排序、截断）

表达式求值集中在 ``_evaluate``：行 + 表达式 → 值。它只认 tuple 和 AST，
不碰页、不碰字节——那些活在 StorageEngine 那一层。
"""

from __future__ import annotations

import operator
from itertools import islice
from typing import TYPE_CHECKING, Any, Callable, Iterator, TypeAlias

from database_system.engine.storage_engine import StorageEngine
from database_system.sql_compiler.ast_nodes import (
    AggregateExpr, AggregateFunction, BinaryExpr, BinaryOperator, Expr,
    IdentifierExpr, LiteralExpr, UnaryExpr, UnaryOperator,
)
from database_system.sql_compiler.catalog import Catalog, TableSchema
from database_system.sql_compiler.planner import (
    Aggregate, CreateTable, Delete, DropTable, Filter, Insert, Limit, PlanNode,
    Project, SeqScan, ShowDatabases, ShowTables, Sort, Update,
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


def _place(values: list, positions: list[int] | None, width: int) -> tuple:
    """把 VALUES 摆到建表顺序上。

    positions 为 None 表示语句没写列名，值就按源码顺序；否则按列名落位。
    语义层已保证列名存在、不重复、且覆盖全部列，所以这里不必再兜底。
    """
    if positions is None:
        return tuple(values)
    row: list[Any] = [None] * width
    for position, value in zip(positions, values):
        row[position] = value
    return tuple(row)


def _evaluate(expr: Expr, row: tuple | None, index: dict[str, int],
              allow_aggregate: bool = False) -> Any:
    """按行求值一个表达式；INSERT 的 VALUES 没有源行，此时 row 为 None。

    allow_aggregate=True 时允许聚合表达式（用于 HAVING 子句）。
    """
    if isinstance(expr, LiteralExpr):
        return expr.value
    if isinstance(expr, IdentifierExpr):
        if row is None:
            raise ExecError(f"列 '{expr.name}' 在此处不能取值",
                            line=expr.line, column=expr.column)
        return row[index[expr.name]]
    if isinstance(expr, UnaryExpr):
        value = _evaluate(expr.operand, row, index, allow_aggregate)
        if expr.op is UnaryOperator.NOT:
            return not value
        if expr.op is UnaryOperator.MINUS:
            return -value
        return value
    if isinstance(expr, BinaryExpr):
        return _evaluate_binary(expr, row, index, allow_aggregate)
    if isinstance(expr, AggregateExpr):
        # 在 HAVING 子句中，聚合表达式已经被计算并存储在结果行中
        # 这里不应该再次遇到 AggregateExpr，而是应该通过 IdentifierExpr 引用
        if allow_aggregate:
            # 如果允许聚合表达式，说明是在 HAVING 求值中，
            # 但此时聚合结果已经在 result_row 中，应该通过列名引用
            raise ExecError(f"内部错误：HAVING 中的聚合表达式应该已被替换为列引用",
                            line=expr.line, column=expr.column)
        raise ExecError(f"聚合函数 {expr.function} 不能在此处使用",
                        line=expr.line, column=expr.column)
    raise ExecError(f"不支持的表达式: {type(expr).__name__}",
                    line=expr.line, column=expr.column)


def _evaluate_binary(expr: BinaryExpr, row: tuple | None,
                     index: dict[str, int], allow_aggregate: bool = False) -> Any:
    op = expr.op
    # AND / OR 短路求值：右边不一定要算
    if op is BinaryOperator.AND:
        return (bool(_evaluate(expr.left, row, index, allow_aggregate))
                and bool(_evaluate(expr.right, row, index, allow_aggregate)))
    if op is BinaryOperator.OR:
        return (bool(_evaluate(expr.left, row, index, allow_aggregate))
                or bool(_evaluate(expr.right, row, index, allow_aggregate)))

    left = _evaluate(expr.left, row, index, allow_aggregate)
    right = _evaluate(expr.right, row, index, allow_aggregate)
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
        if isinstance(plan, Aggregate):
            plan = plan.child
        else:
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
        if isinstance(plan, DropTable):
            return self._drop_table(plan)
        if isinstance(plan, Update):
            return self._update(plan)
        if isinstance(plan, ShowDatabases):
            return [(self.engine.data_dir.name or str(self.engine.data_dir),)]
        if isinstance(plan, ShowTables):
            return [(name,) for name in self.catalog.table_names(include_system=False)]
        if isinstance(plan, (SeqScan, Filter, Project, Sort, Limit, Aggregate)):
            return self._select(plan)
        # 兜底：前端若新增了计划节点而这里还没接，必须干净报错而不是崩掉
        # REPL。不能默认丢给 _select：那里要顺着 child 找 SeqScan，而这类
        # 新节点未必有 child，AttributeError 会穿透 CLI。
        raise ExecError(f"不支持的查询计划: {type(plan).__name__}")

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
        # 语句写了列名就查它们在表里的位置，没写则按建表顺序原样落位
        positions = (
            None if plan.columns is None
            else [index[name] for name in plan.columns]
        )
        inserted = 0
        for values in plan.rows:
            evaluated = [_evaluate(value, None, index) for value in values]
            row = _place(evaluated, positions, len(schema.columns))
            self.engine.insert_row(plan.table, row)
            inserted += 1
        return f"{inserted} row(s) inserted"

    def _delete(self, plan: Delete) -> str:
        schema = self._require_table(plan.table)
        index = _column_index(schema)
        deleted = self.engine.delete_where(plan.table, self._predicate(plan.child, index))
        return f"{deleted} row(s) deleted"

    def _update(self, plan: Update) -> str:
        schema = self._require_table(plan.table)
        index = _column_index(schema)
        # 赋值目标先翻成行内下标，免得每一行都查一次字典
        targets = [(index[item.column_name], item.value)
                   for item in plan.assignments]

        def transform(row: tuple) -> tuple:
            # 右边一律拿原行求值：SET a = b, b = a 要能交换，
            # 边改边取就成了"两次都读到刚改过的那一列"
            values = list(row)
            for position, expression in targets:
                values[position] = _evaluate(expression, row, index)
            return tuple(values)

        updated = self.engine.update_where(
            plan.table, self._predicate(plan.child, index), transform
        )
        return f"{updated} row(s) updated"

    def _drop_table(self, plan: DropTable) -> str:
        # 与 _create_table 对称：没有 CatalogManager 时（两参数构造器）
        # 自己按同样的顺序收尾——先摘内存这个不会失败的动作，再删文件
        if self.catalog_manager is None:
            self.catalog.drop_table(plan.table)
            self.engine.remove_table(plan.table)
        else:
            self.catalog_manager.drop_table(plan.table, self.catalog)
        return "OK"

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
                # 对于聚合查询，Aggregate 节点已经输出了正确的列
                # Project 只需要按顺序输出，不需要再从 index 查找
                if isinstance(plan.child, Aggregate):
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
        elif isinstance(plan, Limit):
            # islice 是惰性的：取够 count 行就不再往下要，不会白扫全表
            yield from islice(self._run(plan.child, index), plan.count)
        elif isinstance(plan, Aggregate):
            yield from self._aggregate(plan, index)
        else:
            raise ExecError(f"不支持的查询计划: {type(plan).__name__}")

    # ---------- 工具 ----------
    def _aggregate(self, plan: Aggregate, index: dict[str, int]) -> Iterator[tuple]:
        """执行聚合操作：GROUP BY + 聚合函数 + HAVING。"""
        # 1. 读取子计划的所有行
        rows = list(self._run(plan.child, index))

        # 2. 按 GROUP BY 列分组
        if plan.group_by:
            # 有 GROUP BY：按指定列分组
            groups: dict[tuple, list[tuple]] = {}
            group_indices = [index[col] for col in plan.group_by]
            for row in rows:
                key = tuple(row[i] for i in group_indices)
                groups.setdefault(key, []).append(row)
        else:
            # 无 GROUP BY：所有行作为一组
            groups = {(): rows}

        # 3. 对每组计算聚合函数
        for group_key, group_rows in groups.items():
            # 计算所有聚合表达式
            agg_values = []
            for col_name, agg_expr in plan.aggregates:
                value = self._compute_aggregate(agg_expr, group_rows, index)
                agg_values.append(value)

            # 构建结果行：GROUP BY 列 + 聚合结果
            result_row = group_key + tuple(agg_values)

            # 4. 应用 HAVING 过滤
            if plan.having is not None:
                # 构建临时索引：GROUP BY 列 + 聚合列
                temp_index = {col: i for i, col in enumerate(plan.group_by)}
                for i, (col_name, _) in enumerate(plan.aggregates):
                    temp_index[col_name] = len(plan.group_by) + i

                # 求值 HAVING，在临时环境中重新计算聚合
                if not self._evaluate_having(plan.having, result_row, temp_index, group_rows, index):
                    continue

            yield result_row

    def _evaluate_having(self, expr: Expr, row: tuple, index: dict[str, int],
                         group_rows: list[tuple], original_index: dict[str, int]) -> bool:
        """求值 HAVING 表达式，遇到聚合表达式时重新计算。"""
        if isinstance(expr, AggregateExpr):
            # 对当前组重新计算聚合
            return self._compute_aggregate(expr, group_rows, original_index)
        if isinstance(expr, IdentifierExpr):
            # 列引用：从结果行中获取
            return row[index[expr.name]]
        if isinstance(expr, LiteralExpr):
            return expr.value
        if isinstance(expr, BinaryExpr):
            op = expr.op
            if op is BinaryOperator.AND:
                return (self._evaluate_having(expr.left, row, index, group_rows, original_index)
                        and self._evaluate_having(expr.right, row, index, group_rows, original_index))
            if op is BinaryOperator.OR:
                return (self._evaluate_having(expr.left, row, index, group_rows, original_index)
                        or self._evaluate_having(expr.right, row, index, group_rows, original_index))

            left = self._evaluate_having(expr.left, row, index, group_rows, original_index)
            right = self._evaluate_having(expr.right, row, index, group_rows, original_index)

            if op is BinaryOperator.DIVIDE:
                if right == 0:
                    raise ExecError("除数为零", line=expr.line, column=expr.column)
                return int(left / right)

            handler = _COMPARISON.get(op)
            if handler:
                return handler(left, right)
            handler = _ARITHMETIC.get(op)
            if handler:
                return handler(left, right)
            raise ExecError(f"不支持的运算符: {op}", line=expr.line, column=expr.column)
        if isinstance(expr, UnaryExpr):
            value = self._evaluate_having(expr.operand, row, index, group_rows, original_index)
            if expr.op is UnaryOperator.NOT:
                return not value
            if expr.op is UnaryOperator.MINUS:
                return -value
            return value
        raise ExecError(f"不支持的表达式: {type(expr).__name__}",
                        line=expr.line, column=expr.column)

    def _compute_aggregate(
        self, agg_expr: AggregateExpr, rows: list[tuple], index: dict[str, int]
    ) -> Any:
        """计算单个聚合函数的值。"""
        func = agg_expr.function

        # COUNT(*)
        if func is AggregateFunction.COUNT and agg_expr.argument is None:
            return len(rows)

        # 其他聚合函数需要提取列值
        values = []
        for row in rows:
            value = _evaluate(agg_expr.argument, row, index)
            values.append(value)

        # COUNT(DISTINCT column)
        if func is AggregateFunction.COUNT:
            if agg_expr.is_distinct:
                return len(set(values))
            return len(values)

        # 空组处理
        if not values:
            return None

        # SUM
        if func is AggregateFunction.SUM:
            return sum(values)

        # AVG (整数除法)
        if func is AggregateFunction.AVG:
            return sum(values) // len(values)

        # MIN
        if func is AggregateFunction.MIN:
            return min(values)

        # MAX
        if func is AggregateFunction.MAX:
            return max(values)

        raise ExecError(f"不支持的聚合函数: {func}")

    # ---------- 工具 ----------
    @staticmethod
    def _predicate(child: PlanNode | None,
                   index: dict[str, int]) -> Callable[[tuple], bool]:
        if isinstance(child, Filter):
            return lambda row: bool(_evaluate(child.predicate, row, index))
        # 没有 WHERE：DELETE 是删全表，UPDATE 是改全表
        return lambda row: True

    def _require_table(self, table: str) -> TableSchema:
        schema = self.catalog.find_table(table)
        if schema is None:
            raise ExecError(f"表 '{table}' 不存在")
        return schema
