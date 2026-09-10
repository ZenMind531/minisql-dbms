"""Rule-based logical plan optimizer (T018).

Three rules are applied bottom-up, in one pass, to a deep copy of the input
plan:

1. **常量折叠** — an arithmetic or comparison node whose operands are both
   literals is replaced by the literal it evaluates to.
2. **布尔化简** — ``AND`` / ``OR`` with one constant truth-valued operand is
   replaced by whichever side still decides the result.
3. **冗余节点消除** — a constant-*true* ``Filter`` and a ``Project(*)`` node
   are dropped because they cannot change the rows flowing through them.

Two invariants keep the contract's "保证语义等价" promise, and both exist
because breaking them silently returns or deletes the wrong rows:

* **A constant-false Filter is kept, never dropped.** ``WHERE 1 = 2`` selects
  no rows; removing the Filter would turn it into a full table scan, which
  returns every row for SELECT and deletes every row for DELETE. There is no
  "empty result" node in the frozen plan contract and D's executor supports
  none, so keeping the false predicate is the only semantics-preserving
  choice available.
* **Folding never raises.** An expression the optimizer cannot evaluate
  (``1 / 0``, a mixed-type comparison, a FLOAT literal) is left exactly as it
  was, so the executor reports it as a normal runtime diagnostic instead of
  the optimizer crashing the process. Constitution principle II.

Truth values are encoded as the INTEGER literal ``1`` or ``0`` carrying
``resolved_type = BOOL``. The frozen AST has no boolean literal kind
(``LiteralExpr`` explicitly rejects Python ``bool``), so ``literal_kind``
records the source form while ``resolved_type`` records the semantic type.
Only ``resolved_type`` decides whether a literal is a predicate.
"""

from __future__ import annotations

import copy
import operator
from typing import Any, Callable

from database_system.sql_compiler.ast_nodes import (
    BinaryExpr, BinaryOperator, Expr, LiteralExpr, LiteralKind, TypeKind,
    TypeSpec, UnaryExpr, UnaryOperator,
)
from database_system.sql_compiler.planner import (
    CreateTable, Delete, Filter, Insert, PlanNode, Project, SeqScan,
    ShowDatabases, ShowTables, Sort,
)


# Kinds whose Python value the optimizer is allowed to compute with. FLOAT is
# excluded on purpose: MiniSQL has no FLOAT type, so folding one would invent
# a value the rest of the system cannot represent.
FOLDABLE_KINDS = frozenset({LiteralKind.INTEGER, LiteralKind.STRING})

ARITHMETIC_OPERATIONS: dict[BinaryOperator, Callable[[Any, Any], Any]] = {
    BinaryOperator.ADD: operator.add,
    BinaryOperator.SUBTRACT: operator.sub,
    BinaryOperator.MULTIPLY: operator.mul,
    # MiniSQL INT division truncates toward zero, unlike Python's floor //.
    BinaryOperator.DIVIDE: lambda left, right: int(left / right),
}

COMPARISON_OPERATIONS: dict[BinaryOperator, Callable[[Any, Any], bool]] = {
    BinaryOperator.EQUAL: operator.eq,
    BinaryOperator.NOT_EQUAL: operator.ne,
    BinaryOperator.GREATER_THAN: operator.gt,
    BinaryOperator.GREATER_THAN_OR_EQUAL: operator.ge,
    BinaryOperator.LESS_THAN: operator.lt,
    BinaryOperator.LESS_THAN_OR_EQUAL: operator.le,
}

# Raised by folding on input semantic analysis should already have rejected
# (division by zero, 'a' + 'b', 1 = 'a'). Caught, never propagated.
FOLDING_FAILURES = (ArithmeticError, TypeError, ValueError)


def _integer_literal(value: int, template: Expr) -> LiteralExpr:
    """Build an INT-typed literal positioned at the folded expression."""
    return LiteralExpr(
        line=template.line,
        column=template.column,
        value=int(value),
        literal_kind=LiteralKind.INTEGER,
        resolved_type=TypeSpec(TypeKind.INT),
    )


def _boolean_literal(truth: bool, template: Expr) -> LiteralExpr:
    """Build a BOOL-typed literal encoded as the integer 1 or 0."""
    return LiteralExpr(
        line=template.line,
        column=template.column,
        value=1 if truth else 0,
        literal_kind=LiteralKind.INTEGER,
        resolved_type=TypeSpec(TypeKind.BOOL),
    )


def _is_foldable_literal(expr: Expr) -> bool:
    """True when the optimizer may compute with this expression's value."""
    return isinstance(expr, LiteralExpr) and expr.literal_kind in FOLDABLE_KINDS


def _as_truth_value(expr: Expr) -> bool | None:
    """Return the constant truth value of ``expr``, or None if it has none.

    Only a BOOL-typed literal counts. An INT-typed literal such as the folded
    ``18`` in ``age > 10 + 8`` is a number, not a predicate, and must never
    be used to decide whether a Filter can be dropped.
    """
    if not isinstance(expr, LiteralExpr):
        return None
    if expr.resolved_type is None or expr.resolved_type.kind is not TypeKind.BOOL:
        return None
    return bool(expr.value)


class Optimizer:
    """Apply the three optimization rules to a logical plan."""

    def optimize(self, plan: PlanNode) -> PlanNode:
        """Return an optimized copy; the caller's plan is never mutated."""
        return self._optimize_plan(copy.deepcopy(plan))

    # ---------------------------------------------------------------- plans

    def _optimize_plan(self, plan: PlanNode) -> PlanNode:
        if isinstance(plan, Filter):
            return self._optimize_filter(plan)
        if isinstance(plan, Project):
            return self._optimize_project(plan)
        if isinstance(plan, Sort):
            return Sort(list(plan.items), self._optimize_plan(plan.child))
        if isinstance(plan, Delete):
            return Delete(plan.table, self._optimize_plan(plan.child))
        if isinstance(plan, (SeqScan, CreateTable, Insert,
                             ShowDatabases, ShowTables)):
            # Leaf nodes hold no predicate and no child to rewrite.
            return plan
        raise TypeError(f"unsupported plan type: {type(plan).__name__}")

    def _optimize_filter(self, plan: Filter) -> PlanNode:
        child = self._optimize_plan(plan.child)
        predicate = self._fold_expression(plan.predicate)
        truth = _as_truth_value(predicate)

        if truth is True:
            # Always true: every row passes, so the Filter changes nothing.
            return child
        # Always false (truth is False) or row-dependent (truth is None).
        # Both keep the Filter: dropping a false one would let a SELECT scan
        # the whole table and a DELETE empty it.
        return Filter(predicate, child)

    def _optimize_project(self, plan: Project) -> PlanNode:
        child = self._optimize_plan(plan.child)
        if plan.columns is None:
            # Project(*) forwards every column unchanged.
            return child
        return Project(list(plan.columns), child)

    # ---------------------------------------------------------- expressions

    def _fold_expression(self, expr: Expr) -> Expr:
        """Fold an expression bottom-up. Never raises on unfoldable input."""
        if isinstance(expr, UnaryExpr):
            return self._fold_unary(expr)
        if isinstance(expr, BinaryExpr):
            return self._fold_binary(expr)
        # Identifiers and literals are already as folded as they can be.
        return expr

    def _fold_unary(self, expr: UnaryExpr) -> Expr:
        operand = self._fold_expression(expr.operand)
        expr.operand = operand

        if expr.op is UnaryOperator.NOT:
            truth = _as_truth_value(operand)
            if truth is None:
                return expr
            return _boolean_literal(not truth, expr)

        is_integer = (_is_foldable_literal(operand)
                      and operand.literal_kind is LiteralKind.INTEGER)
        if not is_integer:
            return expr
        if expr.op is UnaryOperator.PLUS:
            return _integer_literal(operand.value, expr)
        if expr.op is UnaryOperator.MINUS:
            return _integer_literal(-operand.value, expr)
        return expr

    def _fold_binary(self, expr: BinaryExpr) -> Expr:
        expr.left = self._fold_expression(expr.left)
        expr.right = self._fold_expression(expr.right)

        if expr.op in (BinaryOperator.AND, BinaryOperator.OR):
            return self._simplify_boolean(expr)
        if expr.op in ARITHMETIC_OPERATIONS:
            return self._fold_arithmetic(expr)
        if expr.op in COMPARISON_OPERATIONS:
            return self._fold_comparison(expr)
        return expr

    def _fold_arithmetic(self, expr: BinaryExpr) -> Expr:
        """Fold `+ - * /` when both sides are INTEGER literals."""
        left, right = expr.left, expr.right
        both_integers = (
            _is_foldable_literal(left) and _is_foldable_literal(right)
            and left.literal_kind is LiteralKind.INTEGER
            and right.literal_kind is LiteralKind.INTEGER
        )
        if not both_integers:
            return expr
        try:
            value = ARITHMETIC_OPERATIONS[expr.op](left.value, right.value)
        except FOLDING_FAILURES:
            # e.g. 1 / 0. Leave the expression for the executor to report.
            return expr
        return _integer_literal(value, expr)

    def _fold_comparison(self, expr: BinaryExpr) -> Expr:
        """Fold a comparison when both sides are literals of the same kind."""
        left, right = expr.left, expr.right
        comparable = (
            _is_foldable_literal(left) and _is_foldable_literal(right)
            and left.literal_kind is right.literal_kind
        )
        if not comparable:
            # Mixed INT/VARCHAR comparisons are a semantic error, not the
            # optimizer's to decide.
            return expr
        try:
            truth = COMPARISON_OPERATIONS[expr.op](left.value, right.value)
        except FOLDING_FAILURES:
            return expr
        return _boolean_literal(bool(truth), expr)

    def _simplify_boolean(self, expr: BinaryExpr) -> Expr:
        """Simplify AND/OR when exactly one side has a constant truth value.

        AND: TRUE  AND x -> x        FALSE AND x -> FALSE
        OR : FALSE OR  x -> x        TRUE  OR  x -> TRUE
        """
        left_truth = _as_truth_value(expr.left)
        right_truth = _as_truth_value(expr.right)

        if left_truth is not None:
            constant, other = left_truth, expr.right
        elif right_truth is not None:
            constant, other = right_truth, expr.left
        else:
            return expr

        if expr.op is BinaryOperator.AND:
            # A false operand decides AND; a true one leaves the other side.
            return other if constant else _boolean_literal(False, expr)
        # OR: a true operand decides it; a false one leaves the other side.
        return _boolean_literal(True, expr) if constant else other


__all__ = ["Optimizer"]
