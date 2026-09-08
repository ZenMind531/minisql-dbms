"""T012 RED tests for Planner and Optimizer, independent of Parser/Catalog.

Run: python -m unittest discover -s tests -p test_planner.py -v
Also compatible with: python -m pytest tests/test_planner.py -v

The compiler contract specifies plan_to_json but not its field layout.
These tests establish the expected JSON layout for T017/T018:
  SeqScan: {type, table}; Project: {type, columns, child};
  Filter: {type, predicate, child}; Delete: {type, table, child}.
Expression JSON uses Literal {value}, Identifier {name}, and BinaryExpr
{op, left, right}, each with a type discriminator. Source positions and
resolved_type are not execution-plan fields. Project columns=None means '*'.
No production stubs, skips, or xfails: missing modules must fail collection.
"""

import copy
import json
import operator
import unittest

from database_system.sql_compiler.ast_nodes import (
    BinaryExpr,
    BinaryOperator,
    DeleteStmt,
    IdentifierExpr,
    LiteralExpr,
    LiteralKind,
    SelectStmt,
    TypeKind,
    TypeSpec,
)
from database_system.sql_compiler.planner import Planner, plan_to_json
from database_system.sql_compiler.optimizer import Optimizer


def integer(value):
    return LiteralExpr(
        line=1, column=1, value=value, literal_kind=LiteralKind.INTEGER,
        resolved_type=TypeSpec(TypeKind.INT),
    )


def age():
    return IdentifierExpr(
        line=1, column=1, name="age", resolved_type=TypeSpec(TypeKind.INT),
    )


def binary(op, left, right):
    kind = TypeKind.INT if op is BinaryOperator.ADD else TypeKind.BOOL
    return BinaryExpr(
        line=1, column=1, op=op, left=left, right=right,
        resolved_type=TypeSpec(kind),
    )


def age_over_18():
    return binary(BinaryOperator.GREATER_THAN, age(), integer(18))


def constant_true():
    return binary(BinaryOperator.EQUAL, integer(1), integer(1))


def optimizable_predicate():
    # WHERE 1 = 1 AND age > 10 + 8
    return binary(
        BinaryOperator.AND, constant_true(),
        binary(BinaryOperator.GREATER_THAN, age(),
               binary(BinaryOperator.ADD, integer(10), integer(8))),
    )


def select(where=None, columns=("name",)):
    return SelectStmt(
        line=1, column=1, table="student",
        columns=None if columns is None else list(columns), where=where,
    )


def delete(where=None):
    return DeleteStmt(line=1, column=1, table="student", where=where)


def literal_json(value):
    return {"type": "Literal", "value": value}


def binary_json(op, left, right):
    return {"type": "BinaryExpr", "op": op, "left": left, "right": right}


def scan_json():
    return {"type": "SeqScan", "table": "student"}


def predicate_json():
    return binary_json(">", {"type": "Identifier", "name": "age"}, literal_json(18))


def filter_json(predicate):
    return {"type": "Filter", "predicate": predicate, "child": scan_json()}


def project_json(child, columns=("name",)):
    return {"type": "Project", "columns": None if columns is None else list(columns),
            "child": child}


def evaluate_predicate(expression, row):
    """Small independent oracle for the expression subset exercised here.

    This does not use the optimizer or production executor. Unknown nodes
    fail explicitly so unsupported output cannot silently pass equivalence.
    """
    kind = expression["type"]
    if kind == "Literal":
        return expression["value"]
    if kind == "Identifier":
        return row[expression["name"]]
    if kind == "BinaryExpr":
        left = evaluate_predicate(expression["left"], row)
        right = evaluate_predicate(expression["right"], row)
        operations = {
            "+": operator.add,
            "=": operator.eq,
            ">": operator.gt,
            "AND": lambda a, b: bool(a) and bool(b),
            "OR": lambda a, b: bool(a) or bool(b),
        }
        return operations[expression["op"]](left, right)
    raise AssertionError(f"Unexpected expression node: {expression!r}")


class PlannerTests(unittest.TestCase):
    def setUp(self):
        self.planner = Planner()

    def test_select_without_where_is_project_over_scan(self):
        # SELECT name FROM student;
        actual = plan_to_json(self.planner.build(select()))
        self.assertEqual(actual, project_json(scan_json()))

    def test_select_with_where_is_project_over_filter_over_scan(self):
        # SELECT name FROM student WHERE age > 18;
        actual = plan_to_json(self.planner.build(select(age_over_18())))
        self.assertEqual(actual, project_json(filter_json(predicate_json())))

    def test_projection_preserves_requested_column_order(self):
        actual = plan_to_json(self.planner.build(select(columns=("age", "name"))))
        self.assertEqual(actual, project_json(scan_json(), ("age", "name")))

    def test_select_star_is_represented_before_optimization(self):
        actual = plan_to_json(self.planner.build(select(columns=None)))
        self.assertEqual(actual, project_json(scan_json(), columns=None))

    def test_delete_with_where_preserves_target_and_filtered_scan(self):
        actual = plan_to_json(self.planner.build(delete(age_over_18())))
        self.assertEqual(actual, {
            "type": "Delete", "table": "student",
            "child": filter_json(predicate_json()),
        })

    def test_delete_without_where_is_delete_over_scan(self):
        actual = plan_to_json(self.planner.build(delete()))
        self.assertEqual(actual, {
            "type": "Delete", "table": "student", "child": scan_json(),
        })

    def test_unoptimized_plan_preserves_full_predicate(self):
        actual = plan_to_json(self.planner.build(select(optimizable_predicate())))
        original = binary_json(
            "AND", binary_json("=", literal_json(1), literal_json(1)),
            binary_json(">", {"type": "Identifier", "name": "age"},
                        binary_json("+", literal_json(10), literal_json(8))),
        )
        self.assertEqual(actual, project_json(filter_json(original)))

    def test_plan_to_json_is_json_serializable_and_repeatable(self):
        plan = self.planner.build(select(age_over_18()))
        first = plan_to_json(plan)
        self.assertIsInstance(first, dict)
        self.assertEqual(json.loads(json.dumps(first)), first)
        self.assertEqual(plan_to_json(plan), first)


class OptimizerTests(unittest.TestCase):
    def setUp(self):
        self.planner = Planner()
        self.optimizer = Optimizer()

    def optimized_json(self, stmt):
        return plan_to_json(self.optimizer.optimize(self.planner.build(stmt)))

    def test_constant_arithmetic_is_folded_inside_comparison(self):
        predicate = binary(
            BinaryOperator.GREATER_THAN, age(),
            binary(BinaryOperator.ADD, integer(10), integer(8)),
        )
        self.assertEqual(self.optimized_json(select(predicate)),
                         project_json(filter_json(predicate_json())))

    def test_true_and_predicate_is_simplified_on_either_side(self):
        for true_on_left in [True, False]:
            with self.subTest(true_on_left=true_on_left):
                truth, condition = constant_true(), age_over_18()
                left, right = (truth, condition) if true_on_left else (condition, truth)
                stmt = select(binary(BinaryOperator.AND, left, right))
                self.assertEqual(self.optimized_json(stmt),
                                 project_json(filter_json(predicate_json())))

    def test_combined_folding_and_boolean_simplification(self):
        self.assertEqual(self.optimized_json(select(optimizable_predicate())),
                         project_json(filter_json(predicate_json())))

    def test_optimization_preserves_predicate_results_at_and_around_boundary(self):
        plan = self.planner.build(select(optimizable_predicate()))
        # Snapshot first: optimizers may legally modify the input plan in place.
        before = copy.deepcopy(plan_to_json(plan))
        after = plan_to_json(self.optimizer.optimize(plan))
        self.assertEqual(after, project_json(filter_json(predicate_json())))
        rows = [{"age": value, "name": f"student_{value}"}
                for value in [-100, 0, 17, 18, 19, 20, 100]]
        before_values = [evaluate_predicate(before["child"]["predicate"], row)
                         for row in rows]
        after_values = [evaluate_predicate(after["child"]["predicate"], row)
                        for row in rows]
        self.assertEqual(before_values, [False, False, False, False, True, True, True])
        self.assertEqual(after_values, before_values)

    def test_delete_optimization_keeps_delete_target_and_scan(self):
        self.assertEqual(self.optimized_json(delete(optimizable_predicate())), {
            "type": "Delete", "table": "student",
            "child": filter_json(predicate_json()),
        })

    def test_constant_true_filter_is_removed_but_projection_is_kept(self):
        self.assertEqual(self.optimized_json(select(constant_true())),
                         project_json(scan_json()))

    def test_redundant_star_projection_is_removed(self):
        self.assertEqual(self.optimized_json(select(columns=None)), scan_json())

    def test_already_simple_plan_is_preserved(self):
        self.assertEqual(self.optimized_json(select(age_over_18())),
                         project_json(filter_json(predicate_json())))

    def test_nonconstant_and_is_not_incorrectly_dropped(self):
        predicate = binary(
            BinaryOperator.AND, age_over_18(),
            binary(BinaryOperator.EQUAL, age(), integer(20)),
        )
        expected = binary_json(
            "AND", predicate_json(),
            binary_json("=", {"type": "Identifier", "name": "age"}, literal_json(20)),
        )
        self.assertEqual(self.optimized_json(select(predicate)),
                         project_json(filter_json(expected)))

    def test_optimizing_twice_has_the_same_result(self):
        plan = self.planner.build(select(optimizable_predicate()))
        once = self.optimizer.optimize(plan)
        snapshot = copy.deepcopy(plan_to_json(once))
        twice = self.optimizer.optimize(once)
        self.assertEqual(plan_to_json(twice), snapshot)


if __name__ == "__main__":
    unittest.main()
