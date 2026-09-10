"""T011: semantic contracts, tested directly on ASTs without a parser.

Run with ``python -m unittest discover -s tests -p test_semantic.py -v``
or ``python -m pytest tests/test_semantic.py -v``.
These tests were introduced RED before T016; do not skip or xfail them.
"""

import unittest

from database_system.sql_compiler.ast_nodes import (
    BinaryExpr, BinaryOperator, ColumnDef, CreateTableStmt, DeleteStmt,
    IdentifierExpr, InsertStmt, LiteralExpr, LiteralKind, SelectStmt,
    TypeKind, TypeSpec, UnaryExpr, UnaryOperator,
)
from database_system.sql_compiler.catalog import Catalog
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


class SemanticTests(unittest.TestCase):
    def setUp(self):
        self.catalog = Catalog()
        self.columns = [column("id", TypeKind.INT),
                        column("name", TypeKind.VARCHAR, 6)]
        self.catalog.create_table("student", self.columns)
        self.analyzer = SemanticAnalyzer(self.catalog)

    def select(self, where=None, columns=None, table="student"):
        return SelectStmt(line=1, column=1, table=table,
                          columns=columns, where=where)

    def insert(self, values, target_columns=None):
        return InsertStmt(line=1, column=1, table="student",
                          columns=target_columns, values=values)

    def assert_semantic_error(self, stmt, location=None):
        with self.assertRaises(SemanticError) as caught:
            self.analyzer.analyze(stmt)
        error = caught.exception
        self.assertEqual(error.type, "SemanticError")
        self.assertIsInstance(error.message, str)
        self.assertTrue(error.message.strip())
        self.assertIsInstance(error.line, int)
        self.assertIsInstance(error.column, int)
        self.assertGreaterEqual(error.line, 1)
        self.assertGreaterEqual(error.column, 1)
        if location is not None:
            self.assertEqual((error.line, error.column), location)

    def assert_kind(self, expr, kind):
        self.assertIsInstance(expr.resolved_type, TypeSpec)
        self.assertIs(expr.resolved_type.kind, kind)

    def test_select_missing_table(self):
        self.assert_semantic_error(self.select(table="missing"))

    def test_select_missing_projection_column(self):
        self.assert_semantic_error(self.select(columns=["missing"]))

    def test_select_missing_where_column_reports_expression_position(self):
        expr = binary(BinaryOperator.EQUAL, identifier("missing"), literal(1))
        self.assert_semantic_error(self.select(where=expr), location=(2, 10))

    def test_int_plus_varchar_is_rejected(self):
        for left, right in [(identifier("id"), literal("abc")),
                            (literal("abc"), identifier("id"))]:
            with self.subTest(left=left, right=right):
                bad_sum = binary(BinaryOperator.ADD, left, right)
                predicate = binary(BinaryOperator.EQUAL, bad_sum, literal(1))
                self.assert_semantic_error(self.select(where=predicate))

    def test_insert_value_count_must_match_schema(self):
        for values in [[literal(1)], [literal(1), literal("Bob"), literal(2)]]:
            with self.subTest(count=len(values)):
                self.assert_semantic_error(self.insert(values))

    def test_insert_value_count_must_match_explicit_columns(self):
        for values in [[literal(1)], [literal(1), literal("Bob"), literal(2)]]:
            with self.subTest(count=len(values)):
                self.assert_semantic_error(self.insert(values, ["id", "name"]))

    def test_insert_rejects_both_type_mismatch_directions(self):
        for values in [[literal("one"), literal("Bob")],
                       [literal(1), literal(2)]]:
            with self.subTest(values=values):
                self.assert_semantic_error(self.insert(values))

    def test_insert_rejects_unknown_or_duplicate_target_columns(self):
        for names in [["id", "missing"], ["id", "id"]]:
            with self.subTest(names=names):
                self.assert_semantic_error(self.insert([literal(1), literal(2)], names))

    def test_insert_matches_explicit_column_order(self):
        stmt = self.insert([literal("Bob"), literal(1)], ["name", "id"])
        result = self.analyzer.analyze(stmt)
        self.assertIsInstance(result, InsertStmt)
        self.assert_kind(result.values[0], TypeKind.VARCHAR)
        self.assert_kind(result.values[1], TypeKind.INT)
        self.assert_semantic_error(
            self.insert([literal(1), literal("Bob")], ["name", "id"]))

    def test_create_existing_table_is_rejected(self):
        stmt = CreateTableStmt(line=1, column=1, table="student", columns=self.columns)
        self.assert_semantic_error(stmt)

    def test_create_duplicate_column_names_is_rejected(self):
        stmt = CreateTableStmt(line=1, column=1, table="new_table", columns=[
            column("id", TypeKind.INT), column("id", TypeKind.VARCHAR, 6)])
        self.assert_semantic_error(stmt)

    def test_create_valid_table(self):
        stmt = CreateTableStmt(line=1, column=1, table="new_table", columns=[
            column("id", TypeKind.INT), column("name", TypeKind.VARCHAR, 255)])
        result = self.analyzer.analyze(stmt)
        self.assertIsInstance(result, CreateTableStmt)
        self.assertEqual(result.table, "new_table")
        self.assertEqual(result.columns, stmt.columns)

    def test_varchar_accepts_empty_short_and_exact_byte_limit(self):
        # VARCHAR(6): two Chinese characters occupy exactly six UTF-8 bytes.
        for value in ["", "Bob", "abcdef", "中文"]:
            with self.subTest(value=value):
                result = self.analyzer.analyze(self.insert([literal(1), literal(value)]))
                self.assertIsInstance(result, InsertStmt)
                self.assert_kind(result.values[0], TypeKind.INT)
                self.assert_kind(result.values[1], TypeKind.VARCHAR)
                self.assertEqual(result.values[1].value, value)

    def test_varchar_rejects_values_over_utf8_byte_limit(self):
        for value in ["abcdefg", "中文a", "中文字"]:
            with self.subTest(value=value):
                self.assert_semantic_error(self.insert([literal(1), literal(value)]))

    def test_valid_select_star_and_named_columns(self):
        for columns in [None, ["id", "name"]]:
            with self.subTest(columns=columns):
                result = self.analyzer.analyze(self.select(columns=columns))
                self.assertIsInstance(result, SelectStmt)
                self.assertEqual(result.table, "student")
                if columns is not None:
                    self.assertEqual(result.columns, columns)

    def test_integer_arithmetic_resolves_to_int(self):
        for op in [BinaryOperator.ADD, BinaryOperator.SUBTRACT,
                   BinaryOperator.MULTIPLY, BinaryOperator.DIVIDE]:
            with self.subTest(op=op):
                expr = binary(op, literal(8), literal(2))
                result = self.analyzer.analyze(self.insert([expr, literal("Bob")]))
                self.assert_kind(result.values[0], TypeKind.INT)
                self.assert_kind(result.values[0].left, TypeKind.INT)
                self.assert_kind(result.values[0].right, TypeKind.INT)

    def test_unary_integer_signs_resolve_to_int(self):
        for op in [UnaryOperator.PLUS, UnaryOperator.MINUS]:
            with self.subTest(op=op):
                expr = UnaryExpr(line=2, column=19, op=op, operand=literal(2))
                result = self.analyzer.analyze(self.insert([expr, literal("Bob")]))
                self.assert_kind(result.values[0], TypeKind.INT)
                self.assert_kind(result.values[0].operand, TypeKind.INT)

    def test_integer_comparisons_resolve_to_bool_and_bind_column_type(self):
        for op in [BinaryOperator.EQUAL, BinaryOperator.NOT_EQUAL,
                   BinaryOperator.GREATER_THAN, BinaryOperator.GREATER_THAN_OR_EQUAL,
                   BinaryOperator.LESS_THAN, BinaryOperator.LESS_THAN_OR_EQUAL]:
            with self.subTest(op=op):
                expr = binary(op, identifier("id"), literal(2))
                result = self.analyzer.analyze(self.select(where=expr))
                self.assert_kind(result.where, TypeKind.BOOL)
                self.assertEqual(result.where.left.resolved_type, TypeSpec(TypeKind.INT))
                self.assert_kind(result.where.right, TypeKind.INT)

    def test_string_equality_and_inequality_resolve_to_bool(self):
        for op in [BinaryOperator.EQUAL, BinaryOperator.NOT_EQUAL]:
            with self.subTest(op=op):
                expr = binary(op, identifier("name"), literal("Bob"))
                result = self.analyzer.analyze(self.select(where=expr))
                self.assert_kind(result.where, TypeKind.BOOL)
                self.assertEqual(result.where.left.resolved_type, TypeSpec(TypeKind.VARCHAR, 6))
                self.assert_kind(result.where.right, TypeKind.VARCHAR)

    def test_and_or_not_resolve_to_bool(self):
        for op in [BinaryOperator.AND, BinaryOperator.OR]:
            with self.subTest(op=op):
                left = binary(BinaryOperator.GREATER_THAN, identifier("id"), literal(1))
                right = binary(BinaryOperator.EQUAL, identifier("name"), literal("Bob"))
                negated = UnaryExpr(line=2, column=5, op=UnaryOperator.NOT, operand=right)
                result = self.analyzer.analyze(self.select(where=binary(op, left, negated)))
                for expr in [result.where, result.where.left, result.where.right,
                             result.where.right.operand]:
                    self.assert_kind(expr, TypeKind.BOOL)

    def test_mixed_type_comparison_is_rejected(self):
        expr = binary(BinaryOperator.EQUAL, identifier("id"), literal("1"))
        self.assert_semantic_error(self.select(where=expr))

    def test_logical_operators_require_bool_operands(self):
        for op in [BinaryOperator.AND, BinaryOperator.OR]:
            for bad in [literal(1), literal("Bob")]:
                for bad_on_left in [True, False]:
                    with self.subTest(op=op, bad=bad, bad_on_left=bad_on_left):
                        valid = binary(BinaryOperator.EQUAL, literal(1), literal(1))
                        left, right = (bad, valid) if bad_on_left else (valid, bad)
                        self.assert_semantic_error(self.select(where=binary(op, left, right)))
        expr = UnaryExpr(line=2, column=5, op=UnaryOperator.NOT, operand=literal(1))
        self.assert_semantic_error(self.select(where=expr))

    def test_select_and_delete_where_require_bool(self):
        for value in [1, "Bob"]:
            with self.subTest(value=value):
                self.assert_semantic_error(self.select(where=literal(value)))
                self.assert_semantic_error(DeleteStmt(
                    line=1, column=1, table="student", where=literal(value)))

    def test_float_is_rejected_even_when_ast_can_represent_it(self):
        value = LiteralExpr(line=2, column=20, value=1.5, literal_kind=LiteralKind.FLOAT)
        self.assert_semantic_error(self.insert([value, literal("Bob")]))

    def test_bindings_include_projection_and_where_columns_and_reset(self):
        stmt = self.select(columns=["name"], where=binary(
            BinaryOperator.EQUAL, identifier("id"), literal(1)))
        self.assertIs(self.analyzer.analyze(stmt), stmt)
        self.assertEqual(self.analyzer.column_bindings, {
            "id": self.columns[0], "name": self.columns[1]})
        self.analyzer.analyze(self.select(columns=["id"]))
        self.assertEqual(set(self.analyzer.column_bindings), {"id"})

    def test_create_analysis_does_not_register_table(self):
        stmt = CreateTableStmt(line=3, column=1, table="new", columns=self.columns)
        self.analyzer.analyze(stmt)
        self.assertIsNone(self.catalog.find_table("new"))
        self.analyzer.analyze(stmt)

    def test_insert_and_delete_missing_tables(self):
        insert = self.insert([literal(1), literal("Bob")])
        insert.table = "missing"
        self.assert_semantic_error(insert, location=(1, 1))
        self.assert_semantic_error(DeleteStmt(
            line=3, column=4, table="missing", where=None), location=(3, 4))

    def test_valid_delete_and_missing_delete_column(self):
        stmt = DeleteStmt(line=1, column=1, table="student", where=binary(
            BinaryOperator.EQUAL, identifier("id"), literal(1)))
        self.assertIs(self.analyzer.analyze(stmt), stmt)
        self.assert_kind(stmt.where, TypeKind.BOOL)
        stmt.where.left.name = "missing"
        self.assert_semantic_error(stmt, location=(2, 10))

    def test_insert_rejects_column_references_without_source_row(self):
        self.assert_semantic_error(self.insert([identifier("id"), literal("Bob")]))

    def test_insert_cannot_omit_columns_without_defaults(self):
        self.assert_semantic_error(self.insert([literal(1)], ["id"]))

    def test_long_string_reports_semantic_error_not_type_constructor_error(self):
        self.assert_semantic_error(self.insert([literal(1), literal("a" * 256)]))

    def test_bool_equality_is_valid_but_bool_arithmetic_is_not(self):
        for op, valid in [(BinaryOperator.EQUAL, True), (BinaryOperator.ADD, False)]:
            with self.subTest(op=op):
                left = binary(BinaryOperator.EQUAL, literal(1), literal(1))
                right = binary(BinaryOperator.EQUAL, literal(2), literal(2))
                stmt = self.select(where=binary(op, left, right))
                if valid:
                    self.assert_kind(self.analyzer.analyze(stmt).where, TypeKind.BOOL)
                else:
                    self.assert_semantic_error(stmt)


if __name__ == "__main__":
    unittest.main()
