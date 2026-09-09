"""Rule-based logical plan optimizer."""
from __future__ import annotations
import copy
import operator
from typing import Any
from database_system.sql_compiler.ast_nodes import BinaryExpr, BinaryOperator, LiteralExpr, LiteralKind, TypeKind, TypeSpec, UnaryExpr, UnaryOperator, Expr
from database_system.sql_compiler.planner import PlanNode, SeqScan, Filter, Project, Delete, CreateTable, Insert

class Optimizer:
    def optimize(self, plan: PlanNode) -> PlanNode:
        return self._plan(copy.deepcopy(plan))

    def _plan(self, p):
        if isinstance(p, Filter):
            child = self._plan(p.child); expr = self._expr(p.predicate)
            if isinstance(expr, LiteralExpr) and expr.literal_kind is LiteralKind.INTEGER:
                return child if expr.value else SeqScan(child.table) if isinstance(child, SeqScan) else child
            return self._plan(Filter(expr, child)) if expr is not p.predicate else Filter(expr, child)
        if isinstance(p, Project):
            child = self._plan(p.child)
            return child if p.columns is None else Project(list(p.columns), child)
        if isinstance(p, Delete): return Delete(p.table, self._plan(p.child))
        return p

    def _expr(self, e: Expr) -> Expr:
        if isinstance(e, UnaryExpr):
            e.operand = self._expr(e.operand)
            if isinstance(e.operand, LiteralExpr) and e.operand.literal_kind is LiteralKind.INTEGER and e.op in (UnaryOperator.PLUS, UnaryOperator.MINUS):
                return LiteralExpr(line=e.line,column=e.column,value=e.operand.value if e.op is UnaryOperator.PLUS else -e.operand.value,literal_kind=LiteralKind.INTEGER,resolved_type=TypeSpec(TypeKind.INT))
            return e
        if not isinstance(e, BinaryExpr): return e
        e.left, e.right = self._expr(e.left), self._expr(e.right)
        if isinstance(e.left, LiteralExpr) and isinstance(e.right, LiteralExpr):
            vals = {BinaryOperator.ADD: operator.add, BinaryOperator.SUBTRACT: operator.sub, BinaryOperator.MULTIPLY: operator.mul, BinaryOperator.DIVIDE: operator.truediv, BinaryOperator.EQUAL: operator.eq, BinaryOperator.NOT_EQUAL: operator.ne, BinaryOperator.GREATER_THAN: operator.gt, BinaryOperator.GREATER_THAN_OR_EQUAL: operator.ge, BinaryOperator.LESS_THAN: operator.lt, BinaryOperator.LESS_THAN_OR_EQUAL: operator.le}
            if e.op in vals:
                v=vals[e.op](e.left.value,e.right.value)
                if e.op in (BinaryOperator.ADD,BinaryOperator.SUBTRACT,BinaryOperator.MULTIPLY,BinaryOperator.DIVIDE): return LiteralExpr(line=e.line,column=e.column,value=int(v),literal_kind=LiteralKind.INTEGER,resolved_type=TypeSpec(TypeKind.INT))
                return LiteralExpr(line=e.line,column=e.column,value=int(v),literal_kind=LiteralKind.INTEGER,resolved_type=TypeSpec(TypeKind.BOOL))
        if e.op in (BinaryOperator.AND,BinaryOperator.OR):
            const = e.left if isinstance(e.left, LiteralExpr) else e.right if isinstance(e.right, LiteralExpr) else None
            other = e.right if const is e.left else e.left
            if const is not None:
                truth = bool(const.value)
                if e.op is BinaryOperator.AND: return other if truth else const
                return const if truth else other
        return e

__all__=["Optimizer"]
