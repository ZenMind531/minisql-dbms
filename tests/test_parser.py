import unittest

from database_system.sql_compiler.ast_nodes import (
    BinaryExpr,
    BinaryOperator,
    CreateTableStmt,
    DeleteStmt,
    IdentifierExpr,
    InsertStmt,
    LiteralExpr,
    LiteralKind,
    SelectStmt,
    TypeKind,
    UnaryExpr,
    UnaryOperator,
)
from database_system.sql_compiler.lexer import Lexer
from database_system.sql_compiler.parser import Parser
from database_system.utils.errors import ParseError


def parse(source: str):
    return Parser(Lexer(source).tokenize()).parse()


class ParserStatementTests(unittest.TestCase):
    def test_empty_and_comment_only_input_return_no_statements(self) -> None:
        self.assertEqual(parse(""), [])
        self.assertEqual(parse("-- nothing here"), [])

    def test_parses_create_table_and_varchar_length(self) -> None:
        statement = parse(
            "CREATE TABLE student(id INT, name VARCHAR(32));"
        )[0]

        self.assertIsInstance(statement, CreateTableStmt)
        self.assertEqual((statement.table, statement.line, statement.column),
                         ("student", 1, 1))
        self.assertEqual([column.name for column in statement.columns],
                         ["id", "name"])
        self.assertEqual(statement.columns[0].type_spec.kind, TypeKind.INT)
        self.assertEqual(statement.columns[1].type_spec.kind, TypeKind.VARCHAR)
        self.assertEqual(statement.columns[1].type_spec.length, 32)

    def test_parses_insert_with_and_without_target_columns(self) -> None:
        first, second = parse(
            "INSERT INTO student(id, name) VALUES (1, 'Tom''s');"
            "INSERT INTO student VALUES (2, 'Bob');"
        )

        self.assertIsInstance(first, InsertStmt)
        self.assertEqual(first.columns, ["id", "name"])
        self.assertEqual(first.values[0].value, 1)
        self.assertEqual(first.values[1].value, "Tom's")
        self.assertIsNone(second.columns)

    def test_parses_select_star_named_columns_and_delete(self) -> None:
        star, named, delete = parse(
            "SELECT * FROM student;"
            "SELECT id, name FROM student WHERE id = 1;"
            "DELETE FROM student;"
        )

        self.assertIsInstance(star, SelectStmt)
        self.assertIsNone(star.columns)
        self.assertEqual(named.columns, ["id", "name"])
        self.assertIsInstance(named.where, BinaryExpr)
        self.assertIsInstance(delete, DeleteStmt)
        self.assertIsNone(delete.where)

    def test_preserves_statement_order_in_multi_statement_input(self) -> None:
        statements = parse(
            "CREATE TABLE t(id INT); INSERT INTO t VALUES (1);"
            "SELECT * FROM t; DELETE FROM t WHERE id = 1;"
        )
        self.assertEqual(
            [type(statement) for statement in statements],
            [CreateTableStmt, InsertStmt, SelectStmt, DeleteStmt],
        )


class ParserExpressionTests(unittest.TestCase):
    def test_not_comparison_and_or_precedence(self) -> None:
        expression = parse(
            "SELECT * FROM t WHERE NOT a = 1 AND b = 2 OR c = 3;"
        )[0].where

        self.assertEqual(expression.op, BinaryOperator.OR)
        self.assertEqual(expression.left.op, BinaryOperator.AND)
        self.assertEqual(expression.left.left.op, BinaryOperator.EQUAL)
        self.assertIsInstance(expression.left.left.left, UnaryExpr)
        self.assertEqual(expression.left.left.left.op, UnaryOperator.NOT)

    def test_arithmetic_precedence_and_left_associativity(self) -> None:
        expression = parse("SELECT * FROM t WHERE a = 10 - 4 - 2 * 3;")[0].where
        arithmetic = expression.right

        self.assertEqual(arithmetic.op, BinaryOperator.SUBTRACT)
        self.assertEqual(arithmetic.left.op, BinaryOperator.SUBTRACT)
        self.assertEqual(arithmetic.right.op, BinaryOperator.MULTIPLY)

    def test_parentheses_override_default_precedence(self) -> None:
        expression = parse(
            "SELECT * FROM t WHERE (a = 1 OR b = 2) AND c = 3;"
        )[0].where

        self.assertEqual(expression.op, BinaryOperator.AND)
        self.assertEqual(expression.left.op, BinaryOperator.OR)

    def test_literals_and_unary_signs_have_expected_ast_values(self) -> None:
        statement = parse("INSERT INTO t VALUES (-12, +3.5, 'a''b');")[0]

        self.assertIsInstance(statement.values[0], UnaryExpr)
        self.assertEqual(statement.values[0].op, UnaryOperator.MINUS)
        self.assertEqual(statement.values[0].operand.literal_kind,
                         LiteralKind.INTEGER)
        self.assertEqual(statement.values[1].operand.literal_kind,
                         LiteralKind.FLOAT)
        self.assertEqual(statement.values[2].value, "a'b")


class ParserErrorTests(unittest.TestCase):
    def assert_parse_error(self, source: str, expected_text: str) -> ParseError:
        with self.assertRaises(ParseError) as caught:
            parse(source)
        self.assertGreaterEqual(caught.exception.line, 1)
        self.assertGreaterEqual(caught.exception.column, 1)
        self.assertIn("unexpected", caught.exception.message.lower())
        self.assertIn(expected_text, caught.exception.message)
        return caught.exception

    def test_requires_semicolon_after_every_statement(self) -> None:
        error = self.assert_parse_error("SELECT * FROM student", ";")
        self.assertIn("EOF", error.message)

    def test_reports_missing_expression_after_and(self) -> None:
        error = self.assert_parse_error(
            "SELECT * FROM student WHERE id = 1 AND;", "expression"
        )
        self.assertIn("token ';'", error.message)

    def test_rejects_empty_and_consecutive_statements(self) -> None:
        self.assert_parse_error(";", "statement")
        self.assert_parse_error("SELECT * FROM t;;", "statement")

    def test_rejects_chained_comparisons(self) -> None:
        self.assert_parse_error("SELECT * FROM t WHERE a = b = 1;", ";")

    def test_varchar_requires_integer_length_in_range(self) -> None:
        invalid = [
            "CREATE TABLE t(v VARCHAR);",
            "CREATE TABLE t(v VARCHAR());",
            "CREATE TABLE t(v VARCHAR(0));",
            "CREATE TABLE t(v VARCHAR(256));",
            "CREATE TABLE t(v VARCHAR(1.5));",
            "CREATE TABLE t(v VARCHAR(-1));",
        ]
        for source in invalid:
            with self.subTest(source=source):
                self.assert_parse_error(source, "VARCHAR")

    def test_varchar_accepts_inclusive_boundaries(self) -> None:
        first, second = parse(
            "CREATE TABLE low(v VARCHAR(1));"
            "CREATE TABLE high(v VARCHAR(255));"
        )
        self.assertEqual(first.columns[0].type_spec.length, 1)
        self.assertEqual(second.columns[0].type_spec.length, 255)

    def test_excessive_parentheses_raise_parse_error_not_recursion_error(self) -> None:
        source = "SELECT * FROM t WHERE " + "(" * 1100 + "a = 1" + ")" * 1100 + ";"
        self.assert_parse_error(source, "nesting")


if __name__ == "__main__":
    unittest.main()
