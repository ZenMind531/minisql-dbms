"""Logical plan construction and human/JSON representations.

The planner translates an already parsed (and normally semantically checked)
statement into a small relational operator tree.  It deliberately performs no
catalog access or validation; that is SemanticAnalyzer's responsibility.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, TypeAlias

from database_system.sql_compiler.ast_nodes import (
    BinaryExpr, CreateTableStmt, DeleteStmt, Expr, IdentifierExpr, InsertStmt,
    LiteralExpr, OrderByItem, SelectStmt, ShowDatabasesStmt, ShowTablesStmt,
    Stmt, UnaryExpr,
)


@dataclass(slots=True)
class SeqScan:
    table: str


@dataclass(slots=True)
class Filter:
    predicate: Expr
    child: "PlanNode"


@dataclass(slots=True)
class Project:
    columns: list[str] | None
    child: "PlanNode"


@dataclass(slots=True)
class Sort:
    items: list[OrderByItem]
    child: "PlanNode"


@dataclass(slots=True)
class ShowDatabases:
    pass


@dataclass(slots=True)
class ShowTables:
    pass


@dataclass(slots=True)
class Delete:
    table: str
    child: "PlanNode"


@dataclass(slots=True)
class CreateTable:
    table: str
    schema: list[Any]


@dataclass(slots=True)
class Insert:
    table: str
    rows: list[Any]


PlanNode: TypeAlias = (
    SeqScan | Filter | Project | Sort | Delete | CreateTable | Insert
    | ShowDatabases | ShowTables
)


class Planner:
    """Build logical plans for the four supported statement types."""

    def build(self, stmt: Stmt) -> PlanNode:
        if isinstance(stmt, CreateTableStmt):
            # Keep ColumnDef objects in the plan for the executor, while
            # plan_to_json provides a stable metadata-only representation.
            return CreateTable(stmt.table, list(stmt.columns))
        if isinstance(stmt, InsertStmt):
            # One INSERT statement represents one row in the grammar.
            return Insert(stmt.table, [list(stmt.values)])
        if isinstance(stmt, SelectStmt):
            child: PlanNode = SeqScan(stmt.table)
            if stmt.where is not None:
                child = Filter(stmt.where, child)
            if stmt.order_by:
                child = Sort(list(stmt.order_by), child)
            return Project(stmt.columns, child)
        if isinstance(stmt, DeleteStmt):
            child: PlanNode = SeqScan(stmt.table)
            if stmt.where is not None:
                child = Filter(stmt.where, child)
            return Delete(stmt.table, child)
        if isinstance(stmt, ShowDatabasesStmt):
            return ShowDatabases()
        if isinstance(stmt, ShowTablesStmt):
            return ShowTables()
        raise TypeError(f"unsupported statement type: {type(stmt).__name__}")


def _expression_json(expr: Expr) -> dict[str, Any]:
    if isinstance(expr, LiteralExpr):
        return {"type": "Literal", "value": expr.value}
    if isinstance(expr, IdentifierExpr):
        return {"type": "Identifier", "name": expr.name}
    if isinstance(expr, UnaryExpr):
        return {
            "type": "UnaryExpr",
            "op": expr.op.value,
            "operand": _expression_json(expr.operand),
        }
    if isinstance(expr, BinaryExpr):
        return {
            "type": "BinaryExpr",
            "op": expr.op.value,
            "left": _expression_json(expr.left),
            "right": _expression_json(expr.right),
        }
    raise TypeError(f"unsupported expression type: {type(expr).__name__}")


def _schema_json(schema: list[Any]) -> list[dict[str, Any]]:
    result = []
    for column in schema:
        result.append({
            "name": column.name,
            "type": column.type_spec.kind.value,
            "length": column.type_spec.length,
        })
    return result


def _value_json(value: Any) -> Any:
    if isinstance(value, Expr):
        return _expression_json(value)
    if isinstance(value, list):
        return [_value_json(item) for item in value]
    if isinstance(value, tuple):
        return [_value_json(item) for item in value]
    return value


def plan_to_json(plan: PlanNode) -> dict[str, Any]:
    """Convert a plan to deterministic JSON-compatible dictionaries."""
    if isinstance(plan, SeqScan):
        return {"type": "SeqScan", "table": plan.table}
    if isinstance(plan, Filter):
        return {
            "type": "Filter",
            "predicate": _expression_json(plan.predicate),
            "child": plan_to_json(plan.child),
        }
    if isinstance(plan, Project):
        return {
            "type": "Project",
            "columns": None if plan.columns is None else list(plan.columns),
            "child": plan_to_json(plan.child),
        }
    if isinstance(plan, Sort):
        return {
            "type": "Sort",
            "items": [
                {"column": item.column_name,
                 "direction": "DESC" if item.descending else "ASC"}
                for item in plan.items
            ],
            "child": plan_to_json(plan.child),
        }
    if isinstance(plan, ShowDatabases):
        return {"type": "ShowDatabases"}
    if isinstance(plan, ShowTables):
        return {"type": "ShowTables"}
    if isinstance(plan, Delete):
        return {
            "type": "Delete",
            "table": plan.table,
            "child": plan_to_json(plan.child),
        }
    if isinstance(plan, CreateTable):
        return {"type": "CreateTable", "table": plan.table,
                "schema": _schema_json(plan.schema)}
    if isinstance(plan, Insert):
        return {"type": "Insert", "table": plan.table,
                "rows": _value_json(plan.rows)}
    raise TypeError(f"unsupported plan type: {type(plan).__name__}")


def _literal_text(value: Any) -> str:
    if isinstance(value, str):
        return "'" + value.replace("'", "''") + "'"
    return str(value)


def _expression_text(expr: Expr) -> str:
    if isinstance(expr, LiteralExpr):
        return _literal_text(expr.value)
    if isinstance(expr, IdentifierExpr):
        return expr.name
    if isinstance(expr, UnaryExpr):
        if expr.op.value == "NOT":
            return f"NOT {_expression_text(expr.operand)}"
        return f"{expr.op.value}{_expression_text(expr.operand)}"
    if isinstance(expr, BinaryExpr):
        return f"{_expression_text(expr.left)} {expr.op.value} {_expression_text(expr.right)}"
    raise TypeError(f"unsupported expression type: {type(expr).__name__}")


def _node_label(plan: PlanNode) -> str:
    if isinstance(plan, SeqScan):
        return f"SeqScan({plan.table})"
    if isinstance(plan, Filter):
        return f"Filter({_expression_text(plan.predicate)})"
    if isinstance(plan, Project):
        columns = "*" if plan.columns is None else ", ".join(plan.columns)
        return f"Project({columns})"
    if isinstance(plan, Sort):
        items = ", ".join(
            f"{item.column_name} {'DESC' if item.descending else 'ASC'}"
            for item in plan.items
        )
        return f"Sort({items})"
    if isinstance(plan, ShowDatabases):
        return "ShowDatabases"
    if isinstance(plan, ShowTables):
        return "ShowTables"
    if isinstance(plan, Delete):
        return f"Delete({plan.table})"
    if isinstance(plan, CreateTable):
        schema = ", ".join(
            f"{c.name} {c.type_spec.kind.value}"
            + (f"({c.type_spec.length})" if c.type_spec.length is not None else "")
            for c in plan.schema
        )
        return f"CreateTable({plan.table}, schema=[{schema}])"
    if isinstance(plan, Insert):
        return f"Insert({plan.table}, rows={len(plan.rows)})"
    raise TypeError(f"unsupported plan type: {type(plan).__name__}")


def _child(plan: PlanNode) -> PlanNode | None:
    if isinstance(plan, (Filter, Project, Sort, Delete)):
        return plan.child
    return None


def plan_to_tree(plan: PlanNode) -> str:
    """Render a plan as an indented tree for CLI output."""
    lines = [_node_label(plan)]

    def append_children(node: PlanNode, prefix: str) -> None:
        child = _child(node)
        if child is None:
            return
        lines.append(prefix + "└── " + _node_label(child))
        append_grandchildren(child, prefix + "    ")

    def append_grandchildren(node: PlanNode, prefix: str) -> None:
        child = _child(node)
        if child is None:
            return
        lines.append(prefix + "└── " + _node_label(child))
        append_grandchildren(child, prefix + "    ")

    append_children(plan, "")
    return "\n".join(lines)


__all__ = [
    "CreateTable", "Delete", "Filter", "Insert", "PlanNode", "Planner",
    "Project", "SeqScan", "ShowDatabases", "ShowTables", "Sort",
    "plan_to_json", "plan_to_tree",
]
