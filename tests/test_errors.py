"""T006 tests for the unified error hierarchy in database_system/utils/errors.py.

Run: python -m unittest discover -s tests -p test_errors.py -v
Also compatible with: python -m pytest tests/test_errors.py -v

The compiler contract (specs/001-minisql-dbms/contracts/compiler-api.md) and
constitution principle II require every diagnostic to carry
``type + line + column + message``. This module pins that shape for all five
error classes so that A's Lexer/Parser and D's storage/executor can rely on it
without re-reading the implementation.
"""

import unittest

from database_system.utils.errors import (
    ExecError,
    LexError,
    MiniSQLError,
    ParseError,
    SemanticError,
    StorageError,
)


ALL_ERROR_CLASSES = [LexError, ParseError, SemanticError, StorageError, ExecError]


class ErrorHierarchyTests(unittest.TestCase):
    def test_every_error_class_is_exported(self):
        # A and D import these by name; a missing export is a broken contract.
        for error_class in ALL_ERROR_CLASSES + [MiniSQLError]:
            with self.subTest(error_class=error_class.__name__):
                self.assertTrue(issubclass(error_class, Exception))

    def test_every_error_shares_the_common_base(self):
        # One base lets the CLI catch all diagnostics without catching bugs.
        for error_class in ALL_ERROR_CLASSES:
            with self.subTest(error_class=error_class.__name__):
                self.assertTrue(issubclass(error_class, MiniSQLError))

    def test_base_is_not_a_bare_exception_catch_all(self):
        # MiniSQLError must not accidentally match TypeError/AttributeError.
        self.assertFalse(issubclass(TypeError, MiniSQLError))
        self.assertFalse(issubclass(AttributeError, MiniSQLError))

    def test_error_classes_are_distinct_from_each_other(self):
        # Catching LexError must not also swallow ParseError, and so on.
        for error_class in ALL_ERROR_CLASSES:
            for other_class in ALL_ERROR_CLASSES:
                if error_class is other_class:
                    continue
                with self.subTest(caught=error_class.__name__,
                                  raised=other_class.__name__):
                    self.assertFalse(issubclass(other_class, error_class))


class ErrorFieldTests(unittest.TestCase):
    def test_every_error_exposes_type_line_column_message(self):
        for error_class in ALL_ERROR_CLASSES:
            with self.subTest(error_class=error_class.__name__):
                error = error_class("something went wrong", line=7, column=13)
                self.assertEqual(error.type, error_class.__name__)
                self.assertEqual(error.line, 7)
                self.assertEqual(error.column, 13)
                self.assertEqual(error.message, "something went wrong")

    def test_position_defaults_to_one_based_origin(self):
        for error_class in ALL_ERROR_CLASSES:
            with self.subTest(error_class=error_class.__name__):
                error = error_class("no position available")
                self.assertEqual((error.line, error.column), (1, 1))

    def test_str_contains_type_position_and_message(self):
        error = LexError("unexpected character '#'", line=2, column=5)
        self.assertEqual(str(error), "LexError at 2:5: unexpected character '#'")

    def test_positions_must_be_one_based(self):
        # 0-based or negative positions are a caller bug, not a diagnostic.
        for line, column in [(0, 1), (1, 0), (-1, 1), (1, -1)]:
            with self.subTest(line=line, column=column):
                with self.assertRaises(ValueError):
                    LexError("bad position", line=line, column=column)

    def test_message_is_accepted_positionally_and_by_keyword(self):
        positional = ParseError("unexpected token", line=3, column=4)
        keyword = ParseError(message="unexpected token", line=3, column=4)
        self.assertEqual(str(positional), str(keyword))

    def test_reason_is_accepted_as_a_contract_alias_for_message(self):
        # compiler-api.md spells the payload "reason"; both names must work
        # and must refer to the same text.
        error = LexError(reason="unterminated string literal", line=4, column=9)
        self.assertEqual(error.message, "unterminated string literal")
        self.assertEqual(error.reason, "unterminated string literal")

    def test_message_and_reason_cannot_disagree(self):
        with self.assertRaises(TypeError):
            LexError("one text", reason="a different text")

    def test_message_is_required(self):
        with self.assertRaises(TypeError):
            LexError()


class SemanticErrorCompatibilityTests(unittest.TestCase):
    """SemanticError predates T006; existing call sites must keep working."""

    def test_existing_positional_call_style_is_unchanged(self):
        error = SemanticError("table 'student' does not exist", line=2, column=8)
        self.assertEqual(error.type, "SemanticError")
        self.assertEqual(error.line, 2)
        self.assertEqual(error.column, 8)
        self.assertEqual(error.message, "table 'student' does not exist")
        self.assertEqual(
            str(error), "SemanticError at 2:8: table 'student' does not exist"
        )

    def test_message_only_call_style_is_unchanged(self):
        # catalog.py raises SemanticError(text) with no position.
        error = SemanticError("Table 'student' already exists")
        self.assertEqual((error.line, error.column), (1, 1))

    def test_semantic_error_is_still_catchable_as_exception(self):
        with self.assertRaises(Exception):
            raise SemanticError("still an Exception")


if __name__ == "__main__":
    unittest.main()
