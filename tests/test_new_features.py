"""Tests for DROP TABLE, UPDATE, and LIMIT features (semantic analysis and planning).

Run with:
  python -m unittest discover -s tests -p test_new_features.py -v
  python -m pytest tests/test_new_features.py -v
"""

import unittest

from database_system.sql_compiler.ast_nodes import (
    Assignment, BinaryExpr, BinaryOperator, ColumnDef, DropTableStmt,
    IdentifierExpr, LimitClause, LiteralExpr, LiteralKind, OrderByItem,
    SelectStmt, TypeKind, TypeSpec, UpdateStmt,
)
from database_system.sql_compiler.catalog import Catalog
from database_system.sql_compiler.planner import Planner, plan_to_json
from database_system.sql_compiler.semantic import SemanticAnalyzer
from database_system.utils.errors import SemanticError


def literal(value):
    kind = LiteralKind.STRING if isinstance(value, str) else LiteralKind.INTEGER
    return LiteralExpr(line=2, column=20, value=value, literal_kind=kind)


def identifier(name):
    return IdentifierExpr(line=2, column=10, name=name)


def binary(op, left, right):
    return BinaryExpr(line=2, column=15, op=op, left=left, right=right)


def column(name, kind, length=None):
    return ColumnDef(line=1, column=20, name=name,
                     type_spec=TypeSpec(kind, length=length))


def assignment(col_name, value):
    return Assignment(line=2, column=5, column_name=col_name, value=value)


class DropTableSemanticTests(unittest.TestCase):
    def setUp(self):
        self.catalog = Catalog()
        self.columns = [column("id", TypeKind.INT),
                        column("name", TypeKind.VARCHAR, 50)]
        self.catalog.create_table("student", self.columns)
        self.analyzer = SemanticAnalyzer(self.catalog)

    def test_drop_existing_table_succeeds(self):
        stmt = DropTableStmt(line=1, column=1, table="student")
        result = self.analyzer.analyze(stmt)
        self.assertIsInstance(result, DropTableStmt)
        self.assertEqual(result.table, "student")

    def test_drop_nonexistent_table_fails(self):
        stmt = DropTableStmt(line=1, column=1, table="nonexistent")
        with self.assertRaises(SemanticError) as caught:
            self.analyzer.analyze(stmt)
        self.assertIn("does not exist", caught.exception.message)

    def test_drop_catalog_table_is_forbidden(self):
        stmt = DropTableStmt(line=1, column=1, table="__catalog__")
        with self.assertRaises(SemanticError) as caught:
            self.analyzer.analyze(stmt)
        self.assertIn("catalog", caught.exception.message.lower())


class UpdateSemanticTests(unittest.TestCase):
    def setUp(self):
        self.catalog = Catalog()
        self.columns = [column("id", TypeKind.INT),
                        column("name", TypeKind.VARCHAR, 50),
                        column("age", TypeKind.INT)]
        self.catalog.create_table("student", self.columns)
        self.analyzer = SemanticAnalyzer(self.catalog)

    def test_update_with_valid_assignments(self):
        stmt = UpdateStmt(
            line=1, column=1, table="student",
            assignments=[assignment("age", literal(20))],
            where=None
        )
        result = self.analyzer.analyze(stmt)
        self.assertIsInstance(result, UpdateStmt)
        self.assertEqual(len(result.assignments), 1)

    def test_update_nonexistent_table_fails(self):
        stmt = UpdateStmt(
            line=1, column=1, table="nonexistent",
            assignments=[assignment("age", literal(20))],
            where=None
        )
        with self.assertRaises(SemanticError) as caught:
            self.analyzer.analyze(stmt)
        self.assertIn("does not exist", caught.exception.message)

    def test_update_nonexistent_column_fails(self):
        stmt = UpdateStmt(
            line=1, column=1, table="student",
            assignments=[assignment("nonexistent", literal(20))],
            where=None
        )
        with self.assertRaises(SemanticError) as caught:
            self.analyzer.analyze(stmt)
        self.assertIn("does not exist", caught.exception.message)

    def test_update_type_mismatch_fails(self):
        stmt = UpdateStmt(
            line=1, column=1, table="student",
            assignments=[assignment("age", literal("not_a_number"))],
            where=None
        )
        with self.assertRaises(SemanticError) as caught:
            self.analyzer.analyze(stmt)
        self.assertIn("expects", caught.exception.message)

    def test_update_duplicate_column_assignment_fails(self):
        stmt = UpdateStmt(
            line=1, column=1, table="student",
            assignments=[
                assignment("age", literal(20)),
                assignment("age", literal(25))
            ],
            where=None
        )
        with self.assertRaises(SemanticError) as caught:
            self.analyzer.analyze(stmt)
        self.assertIn("duplicate", caught.exception.message.lower())

    def test_update_where_non_bool_fails(self):
        stmt = UpdateStmt(
            line=1, column=1, table="student",
            assignments=[assignment("age", literal(20))],
            where=literal(42)
        )
        with self.assertRaises(SemanticError) as caught:
            self.analyzer.analyze(stmt)
        self.assertIn("BOOL", caught.exception.message)

    def test_update_where_bool_expression_succeeds(self):
        stmt = UpdateStmt(
            line=1, column=1, table="student",
            assignments=[assignment("age", literal(20))],
            where=binary(BinaryOperator.GREATER_THAN, identifier("id"), literal(5))
        )
        result = self.analyzer.analyze(stmt)
        self.assertIsInstance(result, UpdateStmt)
        self.assertIsNotNone(result.where)

    def test_update_varchar_length_check(self):
        # Valid: within length limit
        stmt = UpdateStmt(
            line=1, column=1, table="student",
            assignments=[assignment("name", literal("Bob"))],
            where=None
        )
        result = self.analyzer.analyze(stmt)
        self.assertIsInstance(result, UpdateStmt)

    def test_update_varchar_exceeds_length_fails(self):
        # Exceeds VARCHAR(50) limit
        long_name = "a" * 51
        stmt = UpdateStmt(
            line=1, column=1, table="student",
            assignments=[assignment("name", literal(long_name))],
            where=None
        )
        with self.assertRaises(SemanticError) as caught:
            self.analyzer.analyze(stmt)
        self.assertIn("bytes", caught.exception.message.lower())


class LimitSemanticTests(unittest.TestCase):
    def setUp(self):
        self.catalog = Catalog()
        self.columns = [column("id", TypeKind.INT), column("name", TypeKind.VARCHAR, 50)]
        self.catalog.create_table("student", self.columns)
        self.analyzer = SemanticAnalyzer(self.catalog)

    def test_select_with_limit(self):
        stmt = SelectStmt(
            line=1, column=1, table="student",
            columns=["id", "name"],
            where=None,
            order_by=[],
            limit=LimitClause(line=1, column=20, count=10)
        )
        result = self.analyzer.analyze(stmt)
        self.assertIsInstance(result, SelectStmt)
        self.assertIsNotNone(result.limit)
        self.assertEqual(result.limit.count, 10)

    def test_select_with_limit_zero(self):
        stmt = SelectStmt(
            line=1, column=1, table="student",
            columns=None,
            where=None,
            order_by=[],
            limit=LimitClause(line=1, column=20, count=0)
        )
        result = self.analyzer.analyze(stmt)
        self.assertIsInstance(result, SelectStmt)
        self.assertEqual(result.limit.count, 0)


class PlannerNewFeaturesTests(unittest.TestCase):
    def setUp(self):
        self.planner = Planner()

    def test_drop_table_plan(self):
        stmt = DropTableStmt(line=1, column=1, table="student")
        plan = self.planner.build(stmt)
        plan_json = plan_to_json(plan)
        self.assertEqual(plan_json, {"type": "DropTable", "table": "student"})

    def test_update_without_where_plan(self):
        stmt = UpdateStmt(
            line=1, column=1, table="student",
            assignments=[assignment("age", literal(20))],
            where=None
        )
        plan = self.planner.build(stmt)
        plan_json = plan_to_json(plan)
        self.assertEqual(plan_json["type"], "Update")
        self.assertEqual(plan_json["table"], "student")
        self.assertEqual(len(plan_json["assignments"]), 1)
        self.assertEqual(plan_json["assignments"][0]["column"], "age")
        self.assertNotIn("child", plan_json)

    def test_update_with_where_plan(self):
        stmt = UpdateStmt(
            line=1, column=1, table="student",
            assignments=[assignment("age", literal(20))],
            where=binary(BinaryOperator.GREATER_THAN, identifier("id"), literal(5))
        )
        plan = self.planner.build(stmt)
        plan_json = plan_to_json(plan)
        self.assertEqual(plan_json["type"], "Update")
        self.assertEqual(plan_json["table"], "student")
        self.assertIn("child", plan_json)
        self.assertEqual(plan_json["child"]["type"], "Filter")

    def test_select_with_limit_plan(self):
        stmt = SelectStmt(
            line=1, column=1, table="student",
            columns=["id", "name"],
            where=None,
            order_by=[],
            limit=LimitClause(line=1, column=20, count=10)
        )
        plan = self.planner.build(stmt)
        plan_json = plan_to_json(plan)
        # Top-level should be Limit
        self.assertEqual(plan_json["type"], "Limit")
        self.assertEqual(plan_json["count"], 10)
        # Child should be Project
        self.assertEqual(plan_json["child"]["type"], "Project")

    def test_select_with_order_and_limit_plan(self):
        stmt = SelectStmt(
            line=1, column=1, table="student",
            columns=["id"],
            where=None,
            order_by=[OrderByItem(line=1, column=15, column_name="id", descending=False)],
            limit=LimitClause(line=1, column=25, count=5)
        )
        plan = self.planner.build(stmt)
        plan_json = plan_to_json(plan)
        # Structure: Limit → Project → Sort → SeqScan
        self.assertEqual(plan_json["type"], "Limit")
        self.assertEqual(plan_json["count"], 5)
        self.assertEqual(plan_json["child"]["type"], "Project")
        self.assertEqual(plan_json["child"]["child"]["type"], "Sort")
        self.assertEqual(plan_json["child"]["child"]["child"]["type"], "SeqScan")

    def test_select_with_where_order_limit_plan(self):
        stmt = SelectStmt(
            line=1, column=1, table="student",
            columns=None,
            where=binary(BinaryOperator.GREATER_THAN, identifier("age"), literal(18)),
            order_by=[OrderByItem(line=1, column=15, column_name="age", descending=True)],
            limit=LimitClause(line=1, column=30, count=3)
        )
        plan = self.planner.build(stmt)
        plan_json = plan_to_json(plan)
        # Structure: Limit → Project → Sort → Filter → SeqScan
        self.assertEqual(plan_json["type"], "Limit")
        self.assertEqual(plan_json["child"]["type"], "Project")
        self.assertEqual(plan_json["child"]["child"]["type"], "Sort")
        self.assertEqual(plan_json["child"]["child"]["child"]["type"], "Filter")
        self.assertEqual(plan_json["child"]["child"]["child"]["child"]["type"], "SeqScan")


if __name__ == "__main__":
    unittest.main()
