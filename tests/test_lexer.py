import unittest

from database_system.sql_compiler.lexer import Lexer, Token, TokenType
from database_system.utils.errors import LexError


class LexerBasicTests(unittest.TestCase):
    def test_tokenizes_keywords_identifiers_and_delimiters(self) -> None:
        tokens = Lexer("SeLeCt name FROM student;").tokenize()

        self.assertEqual(
            tokens,
            [
                Token(TokenType.KEYWORD, "SeLeCt", 1, 1),
                Token(TokenType.IDENTIFIER, "name", 1, 8),
                Token(TokenType.KEYWORD, "FROM", 1, 13),
                Token(TokenType.IDENTIFIER, "student", 1, 18),
                Token(TokenType.DELIMITER, ";", 1, 25),
                Token(TokenType.EOF, "", 1, 26),
            ],
        )

    def test_recognizes_every_supported_keyword_case_insensitively(self) -> None:
        source = (
            "select FROM where CREATE table INSERT into VALUES delete "
            "and OR not int varchar"
        )

        tokens = Lexer(source).tokenize()

        self.assertGreater(len(tokens), 0)
        self.assertTrue(all(token.type is TokenType.KEYWORD for token in tokens[:-1]))
        self.assertEqual(tokens[-1].type, TokenType.EOF)
        self.assertEqual(tokens[0].lexeme, "select")
        self.assertEqual(tokens[-2].lexeme, "varchar")

    def test_tracks_positions_across_whitespace_and_newlines(self) -> None:
        tokens = Lexer("CREATE TABLE\n  student (id INT)\r\n;").tokenize()

        self.assertEqual(
            [(token.lexeme, token.line, token.column) for token in tokens],
            [
                ("CREATE", 1, 1),
                ("TABLE", 1, 8),
                ("student", 2, 3),
                ("(", 2, 11),
                ("id", 2, 12),
                ("INT", 2, 15),
                (")", 2, 18),
                (";", 3, 1),
                ("", 3, 2),
            ],
        )

    def test_tokenizes_integer_float_and_escaped_string_constants(self) -> None:
        tokens = Lexer("VALUES (12, 3.5, 'Tom''s book');").tokenize()
        constants = [token for token in tokens if token.type is TokenType.CONST]

        self.assertEqual(
            [(token.lexeme, token.line, token.column) for token in constants],
            [
                ("12", 1, 9),
                ("3.5", 1, 13),
                ("'Tom''s book'", 1, 18),
            ],
        )

    def test_uses_longest_match_for_operators(self) -> None:
        tokens = Lexer("= != > >= < <= + - * /").tokenize()

        self.assertEqual(
            [token.lexeme for token in tokens if token.type is TokenType.OPERATOR],
            ["=", "!=", ">", ">=", "<", "<=", "+", "-", "*", "/"],
        )

    def test_skips_line_and_block_comments_while_tracking_positions(self) -> None:
        tokens = Lexer("-- hidden\r\nSELECT/*block\ncomment*/name;").tokenize()

        self.assertEqual(
            [(token.lexeme, token.line, token.column) for token in tokens],
            [
                ("SELECT", 2, 1),
                ("name", 3, 10),
                (";", 3, 14),
                ("", 3, 15),
            ],
        )


class LexerErrorTests(unittest.TestCase):
    def assert_lex_error(self, source: str, line: int, column: int) -> LexError:
        with self.assertRaises(LexError) as caught:
            Lexer(source).tokenize()
        self.assertEqual((caught.exception.line, caught.exception.column),
                         (line, column))
        return caught.exception

    def test_rejects_illegal_character_at_its_position(self) -> None:
        error = self.assert_lex_error("SELECT\n  @;", 2, 3)
        self.assertIn("@", error.message)

    def test_rejects_number_followed_by_identifier_characters(self) -> None:
        error = self.assert_lex_error("VALUES (12abc);", 1, 9)
        self.assertIn("12abc", error.message)

    def test_rejects_decimal_without_digits_on_both_sides(self) -> None:
        for source, column in [("VALUES (.5);", 9), ("VALUES (1.);", 9)]:
            with self.subTest(source=source):
                self.assert_lex_error(source, 1, column)

    def test_unterminated_string_reports_opening_quote(self) -> None:
        error = self.assert_lex_error("VALUES ('abc", 1, 9)
        self.assertIn("string", error.message.lower())

    def test_string_cannot_cross_a_physical_line(self) -> None:
        self.assert_lex_error("VALUES ('abc\nxyz');", 1, 9)

    def test_unterminated_block_comment_reports_comment_start(self) -> None:
        error = self.assert_lex_error("SELECT 1;\n  /* missing", 2, 3)
        self.assertIn("comment", error.message.lower())


if __name__ == "__main__":
    unittest.main()
