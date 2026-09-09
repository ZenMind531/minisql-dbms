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
    UnaryExpr,
    UnaryOperator,
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


def text(value):
    return LiteralExpr(
        line=1, column=1, value=value, literal_kind=LiteralKind.STRING,
        resolved_type=TypeSpec(TypeKind.VARCHAR, len(value) or 1),
    )


def constant_true():
    return binary(BinaryOperator.EQUAL, integer(1), integer(1))


def constant_false():
    # WHERE 1 = 2 -- never selects a row, and must never be dropped.
    return binary(BinaryOperator.EQUAL, integer(1), integer(2))


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
    if kind == "UnaryExpr":
        operand = evaluate_predicate(expression["operand"], row)
        unary_operations = {
            "+": operator.pos,
            "-": operator.neg,
            "NOT": lambda a: not bool(a),
        }
        return unary_operations[expression["op"]](operand)
    if kind == "BinaryExpr":
        left = evaluate_predicate(expression["left"], row)
        right = evaluate_predicate(expression["right"], row)
        operations = {
            "+": operator.add,
            "-": operator.sub,
            "*": operator.mul,
            "/": lambda a, b: int(a / b),
            "=": operator.eq,
            "!=": operator.ne,
            ">": operator.gt,
            ">=": operator.ge,
            "<": operator.lt,
            "<=": operator.le,
            "AND": lambda a, b: bool(a) and bool(b),
            "OR": lambda a, b: bool(a) or bool(b),
        }
        return operations[expression["op"]](left, right)
    raise AssertionError(f"Unexpected expression node: {expression!r}")


STUDENT_ROWS = [
    {"age": -100, "name": "student_a"},
    {"age": 0, "name": "student_b"},
    {"age": 17, "name": "student_c"},
    {"age": 18, "name": "student_d"},
    {"age": 19, "name": "student_e"},
    {"age": 100, "name": "student_f"},
]


def run_plan(plan, rows=None):
    """Independent oracle that executes a plan JSON against in-memory rows.

    Used to assert end-to-end semantic equivalence of a plan before and after
    optimization, which a predicate-only comparison cannot do once the
    optimizer is allowed to add or remove nodes.
    """
    rows = STUDENT_ROWS if rows is None else rows
    kind = plan["type"]
    if kind == "SeqScan":
        return [dict(row) for row in rows]
    if kind == "Filter":
        return [row for row in run_plan(plan["child"], rows)
                if bool(evaluate_predicate(plan["predicate"], row))]
    if kind == "Project":
        source = run_plan(plan["child"], rows)
        if plan["columns"] is None:
            return source
        return [{name: row[name] for name in plan["columns"]} for row in source]
    if kind == "Delete":
        # Model DELETE as the set of rows it would remove.
        return run_plan(plan["child"], rows)
    raise AssertionError(f"Unexpected plan node: {plan!r}")


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


class AlwaysFalsePredicateTests(unittest.TestCase):
    """A constant-false WHERE selects nothing; dropping it loses that meaning.

    Removing the Filter turns `WHERE 1 = 2` into a full scan, which returns
    every row for SELECT and deletes every row for DELETE. Until a plan node
    that means "empty result" exists in the frozen contract and is supported by
    D's executor, the only semantics-preserving choice is to keep the Filter.
    """

    def setUp(self):
        self.planner = Planner()
        self.optimizer = Optimizer()

    def optimized_json(self, stmt):
        return plan_to_json(self.optimizer.optimize(self.planner.build(stmt)))

    def assert_selects_no_rows(self, plan_json):
        self.assertEqual(run_plan(plan_json), [])

    def test_constant_false_select_filter_is_not_dropped(self):
        # SELECT name FROM student WHERE 1 = 2;
        optimized = self.optimized_json(select(constant_false()))
        self.assertEqual(optimized["type"], "Project")
        self.assertEqual(optimized["child"]["type"], "Filter")
        self.assert_selects_no_rows(optimized)

    def test_constant_false_select_star_filter_is_not_dropped(self):
        # SELECT * FROM student WHERE 1 = 2; -- the '*' Project may vanish,
        # the Filter may not.
        optimized = self.optimized_json(select(constant_false(), columns=None))
        self.assert_selects_no_rows(optimized)

    def test_constant_false_delete_filter_is_not_dropped(self):
        # DELETE FROM student WHERE 1 = 2; -- must delete nothing.
        optimized = self.optimized_json(delete(constant_false()))
        self.assertEqual(optimized["type"], "Delete")
        self.assertEqual(optimized["child"]["type"], "Filter")
        self.assert_selects_no_rows(optimized)

    def test_constant_false_delete_is_not_turned_into_a_full_table_delete(self):
        optimized = self.optimized_json(delete(constant_false()))
        self.assertNotEqual(optimized["child"], scan_json())

    def test_false_and_condition_still_selects_no_rows(self):
        # WHERE 1 = 2 AND age > 18
        predicate = binary(BinaryOperator.AND, constant_false(), age_over_18())
        self.assert_selects_no_rows(self.optimized_json(select(predicate)))

    def test_false_or_condition_keeps_the_surviving_condition(self):
        # WHERE 1 = 2 OR age > 18 -- equivalent to age > 18, not to "all rows".
        predicate = binary(BinaryOperator.OR, constant_false(), age_over_18())
        optimized = self.optimized_json(select(predicate))
        self.assertEqual(run_plan(optimized),
                         [{"name": "student_e"}, {"name": "student_f"}])

    def test_true_or_condition_selects_every_row(self):
        # WHERE 1 = 1 OR age > 18 -- equivalent to no WHERE at all.
        predicate = binary(BinaryOperator.OR, constant_true(), age_over_18())
        optimized = self.optimized_json(select(predicate))
        self.assertEqual(len(run_plan(optimized)), len(STUDENT_ROWS))

    def test_negated_constant_true_selects_no_rows(self):
        # WHERE NOT (1 = 1)
        predicate = UnaryExpr(
            line=1, column=1, op=UnaryOperator.NOT, operand=constant_true(),
            resolved_type=TypeSpec(TypeKind.BOOL),
        )
        self.assert_selects_no_rows(self.optimized_json(select(predicate)))


class OptimizerEquivalenceTests(unittest.TestCase):
    """Optimization must not change the rows a plan produces."""

    def setUp(self):
        self.planner = Planner()
        self.optimizer = Optimizer()

    def assert_same_rows_before_and_after(self, stmt):
        plan = self.planner.build(stmt)
        before = copy.deepcopy(plan_to_json(plan))
        after = plan_to_json(self.optimizer.optimize(plan))
        self.assertEqual(run_plan(after), run_plan(before))
        return after

    def test_equivalence_holds_for_representative_predicates(self):
        cases = {
            "no where": select(),
            "select star": select(columns=None),
            "simple comparison": select(age_over_18()),
            "constant true": select(constant_true()),
            "constant false": select(constant_false()),
            "folded arithmetic": select(optimizable_predicate()),
            "false and condition": select(
                binary(BinaryOperator.AND, constant_false(), age_over_18())),
            "false or condition": select(
                binary(BinaryOperator.OR, constant_false(), age_over_18())),
            "true or condition": select(
                binary(BinaryOperator.OR, constant_true(), age_over_18())),
            "nested constants": select(
                binary(BinaryOperator.AND,
                       binary(BinaryOperator.AND, constant_true(), constant_true()),
                       age_over_18())),
            "delete constant false": delete(constant_false()),
            "delete folded": delete(optimizable_predicate()),
        }
        for label, stmt in cases.items():
            with self.subTest(case=label):
                self.assert_same_rows_before_and_after(stmt)

    def test_folding_keeps_integer_division_semantics(self):
        # WHERE age > 7 / 2 -- MiniSQL INT division truncates toward zero.
        predicate = binary(
            BinaryOperator.GREATER_THAN, age(),
            binary(BinaryOperator.DIVIDE, integer(7), integer(2)),
        )
        after = self.assert_same_rows_before_and_after(select(predicate))
        self.assertEqual(after["child"]["predicate"]["right"], literal_json(3))

    def test_folding_negative_literals_keeps_the_same_rows(self):
        # WHERE age > 0 - 10
        predicate = binary(
            BinaryOperator.GREATER_THAN, age(),
            binary(BinaryOperator.SUBTRACT, integer(0), integer(10)),
        )
        self.assert_same_rows_before_and_after(select(predicate))

    def test_unary_minus_on_a_literal_is_folded_without_changing_rows(self):
        # WHERE age > -10
        predicate = binary(
            BinaryOperator.GREATER_THAN, age(),
            UnaryExpr(line=1, column=1, op=UnaryOperator.MINUS,
                      operand=integer(10), resolved_type=TypeSpec(TypeKind.INT)),
        )
        self.assert_same_rows_before_and_after(select(predicate))


class FoldingSafetyTests(unittest.TestCase):
    """Constant folding must never raise; unfoldable input stays unfolded.

    Constitution principle II forbids uncaught exceptions. A predicate the
    optimizer cannot evaluate is left alone so the executor reports it as a
    normal runtime diagnostic.
    """

    def setUp(self):
        self.planner = Planner()
        self.optimizer = Optimizer()

    def optimize(self, stmt):
        return plan_to_json(self.optimizer.optimize(self.planner.build(stmt)))

    def test_division_by_zero_is_not_folded_and_does_not_raise(self):
        # WHERE age > 1 / 0
        predicate = binary(
            BinaryOperator.GREATER_THAN, age(),
            binary(BinaryOperator.DIVIDE, integer(1), integer(0)),
        )
        optimized = self.optimize(select(predicate))
        self.assertEqual(
            optimized["child"]["predicate"]["right"],
            binary_json("/", literal_json(1), literal_json(0)),
        )

    def test_division_by_zero_inside_a_constant_filter_does_not_raise(self):
        # WHERE 1 / 0 = 1 -- the whole predicate is constant but unfoldable.
        predicate = binary(
            BinaryOperator.EQUAL,
            binary(BinaryOperator.DIVIDE, integer(1), integer(0)), integer(1),
        )
        optimized = self.optimize(select(predicate))
        self.assertEqual(optimized["child"]["type"], "Filter")

    def test_division_by_zero_in_delete_does_not_raise_or_drop_the_filter(self):
        predicate = binary(
            BinaryOperator.EQUAL,
            binary(BinaryOperator.DIVIDE, integer(1), integer(0)), integer(1),
        )
        optimized = self.optimize(delete(predicate))
        self.assertEqual(optimized["child"]["type"], "Filter")

    def test_string_comparison_folds_to_a_boolean_without_raising(self):
        # WHERE 'a' = 'a' -- constant true, so the Filter may be removed.
        predicate = binary(BinaryOperator.EQUAL, text("a"), text("a"))
        self.assertEqual(self.optimize(select(predicate)),
                         project_json(scan_json()))

    def test_unequal_string_comparison_selects_no_rows(self):
        # WHERE 'a' = 'b' -- constant false, so the Filter must survive.
        predicate = binary(BinaryOperator.EQUAL, text("a"), text("b"))
        self.assertEqual(run_plan(self.optimize(select(predicate))), [])

    def test_string_arithmetic_is_left_untouched(self):
        # 'a' + 'b' is rejected by semantic analysis; if it ever reaches the
        # optimizer it must not crash there.
        predicate = binary(
            BinaryOperator.EQUAL,
            binary(BinaryOperator.ADD, text("a"), text("b")), text("ab"),
        )
        optimized = self.optimize(select(predicate))
        self.assertEqual(optimized["child"]["type"], "Filter")

    def test_mixed_type_comparison_is_left_untouched(self):
        # WHERE 1 = 'a' -- semantically invalid; folding must not invent a value.
        predicate = binary(BinaryOperator.EQUAL, integer(1), text("a"))
        optimized = self.optimize(select(predicate))
        self.assertEqual(optimized["child"]["type"], "Filter")

    def test_float_literals_are_not_folded(self):
        # FLOAT is rejected by semantic analysis and unsupported downstream,
        # so the optimizer must not silently produce a folded value for it.
        float_literal = LiteralExpr(line=1, column=1, value=1.5,
                                    literal_kind=LiteralKind.FLOAT)
        predicate = binary(
            BinaryOperator.GREATER_THAN, age(),
            binary(BinaryOperator.ADD, float_literal,
                   LiteralExpr(line=1, column=1, value=1.5,
                               literal_kind=LiteralKind.FLOAT)),
        )
        optimized = self.optimize(select(predicate))
        self.assertEqual(
            optimized["child"]["predicate"]["right"],
            binary_json("+", literal_json(1.5), literal_json(1.5)),
        )

    def test_optimizer_does_not_mutate_the_input_plan(self):
        plan = self.planner.build(select(optimizable_predicate()))
        before = copy.deepcopy(plan_to_json(plan))
        self.optimizer.optimize(plan)
        self.assertEqual(plan_to_json(plan), before)

    def test_unsupported_plan_node_is_reported_as_a_type_error(self):
        with self.assertRaises(TypeError):
            self.optimizer.optimize(object())


class FoldedBooleanRepresentationTests(unittest.TestCase):
    """A folded truth value must describe itself consistently.

    The frozen AST (owned by A) has no boolean literal: LiteralKind is
    INTEGER/FLOAT/STRING and LiteralExpr explicitly rejects Python bool. So B
    encodes a folded truth value as the INTEGER literal 0 or 1 whose
    resolved_type is BOOL — literal_kind records the source form, resolved_type
    records the semantic type. These tests pin that convention so the two
    fields can never drift apart again.
    """

    def setUp(self):
        self.planner = Planner()
        self.optimizer = Optimizer()

    def folded_predicate(self, predicate):
        plan = self.optimizer.optimize(self.planner.build(delete(predicate)))
        return plan.child.predicate

    def test_folded_false_predicate_is_a_bool_typed_literal(self):
        literal = self.folded_predicate(constant_false())
        self.assertIsInstance(literal, LiteralExpr)
        self.assertEqual(literal.resolved_type, TypeSpec(TypeKind.BOOL))

    def test_folded_false_predicate_uses_the_integer_source_form(self):
        literal = self.folded_predicate(constant_false())
        self.assertIs(literal.literal_kind, LiteralKind.INTEGER)

    def test_folded_false_predicate_is_the_integer_zero_not_a_python_bool(self):
        literal = self.folded_predicate(constant_false())
        self.assertEqual(literal.value, 0)
        self.assertIs(type(literal.value), int)

    def test_folded_true_predicate_is_the_integer_one(self):
        plan = self.optimizer.optimize(self.planner.build(delete(constant_true())))
        # A constant-true DELETE filter is redundant, so it is removed.
        self.assertEqual(plan_to_json(plan)["child"], scan_json())

    def test_folded_arithmetic_stays_an_int_typed_integer_literal(self):
        predicate = binary(
            BinaryOperator.GREATER_THAN, age(),
            binary(BinaryOperator.ADD, integer(10), integer(8)),
        )
        plan = self.optimizer.optimize(self.planner.build(select(predicate)))
        folded = plan.child.predicate.right
        self.assertIs(folded.literal_kind, LiteralKind.INTEGER)
        self.assertEqual(folded.resolved_type, TypeSpec(TypeKind.INT))
        self.assertIs(type(folded.value), int)

    def test_arithmetic_folding_is_never_mistaken_for_a_truth_value(self):
        # WHERE age > 10 + 8 folds to an INT literal; that INT must not be
        # read as a constant predicate and used to drop the Filter.
        predicate = binary(
            BinaryOperator.GREATER_THAN, age(),
            binary(BinaryOperator.ADD, integer(10), integer(8)),
        )
        optimized = plan_to_json(
            self.optimizer.optimize(self.planner.build(select(predicate))))
        self.assertEqual(optimized, project_json(filter_json(predicate_json())))

    def test_folded_boolean_serializes_as_its_integer_encoding(self):
        optimized = plan_to_json(
            self.optimizer.optimize(self.planner.build(delete(constant_false()))))
        self.assertEqual(optimized["child"]["predicate"], literal_json(0))


if __name__ == "__main__":
    unittest.main()
