import unittest

from database_system.sql_compiler.lexer import Lexer, Token, TokenType


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


if __name__ == "__main__":
    unittest.main()
