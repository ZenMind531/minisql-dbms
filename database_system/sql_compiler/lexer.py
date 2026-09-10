"""Lexical analysis for the supported MiniSQL grammar."""

from dataclasses import dataclass
from enum import StrEnum

from database_system.utils.errors import LexError


KEYWORDS = frozenset(
    {
        "SELECT",
        "FROM",
        "WHERE",
        "CREATE",
        "TABLE",
        "INSERT",
        "INTO",
        "VALUES",
        "DELETE",
        "AND",
        "OR",
        "NOT",
        "INT",
        "VARCHAR",
        "SHOW",
        "DATABASES",
        "TABLES",
        "ORDER",
        "BY",
        "ASC",
        "DESC",
    }
)

DELIMITERS = frozenset({"(", ")", ",", ";"})
ONE_CHARACTER_OPERATORS = frozenset({"=", ">", "<", "+", "-", "*", "/"})
TWO_CHARACTER_OPERATORS = frozenset({"!=", ">=", "<="})


class TokenType(StrEnum):
    KEYWORD = "KEYWORD"
    IDENTIFIER = "IDENTIFIER"
    CONST = "CONST"
    OPERATOR = "OPERATOR"
    DELIMITER = "DELIMITER"
    EOF = "EOF"


@dataclass(frozen=True, slots=True)
class Token:
    type: TokenType
    lexeme: str
    line: int
    column: int


class Lexer:
    def __init__(self, source: str):
        self.source = source
        self._index = 0
        self._line = 1
        self._column = 1

    def tokenize(self) -> list[Token]:
        tokens: list[Token] = []

        while not self._at_end():
            character = self._current()

            if character.isspace():
                self._skip_whitespace()
            elif self._starts_with("--"):
                self._skip_line_comment()
            elif self._starts_with("/*"):
                self._skip_block_comment()
            elif self._is_identifier_start(character):
                tokens.append(self._scan_word())
            elif "0" <= character <= "9":
                tokens.append(self._scan_number())
            elif character == "." and self._peek() is not None and self._peek().isdigit():
                raise LexError(
                    "invalid number: digits are required before the decimal point",
                    line=self._line,
                    column=self._column,
                )
            elif character == "'":
                tokens.append(self._scan_string())
            elif character in DELIMITERS:
                tokens.append(
                    Token(TokenType.DELIMITER, character, self._line, self._column)
                )
                self._advance()
            elif self._starts_with_any(TWO_CHARACTER_OPERATORS):
                tokens.append(self._scan_operator(length=2))
            elif character in ONE_CHARACTER_OPERATORS:
                tokens.append(self._scan_operator(length=1))
            else:
                raise LexError(
                    f"illegal character {character!r}",
                    line=self._line,
                    column=self._column,
                )

        tokens.append(Token(TokenType.EOF, "", self._line, self._column))
        return tokens

    def _at_end(self) -> bool:
        return self._index >= len(self.source)

    def _current(self) -> str:
        return self.source[self._index]

    def _peek(self, distance: int = 1) -> str | None:
        index = self._index + distance
        return self.source[index] if index < len(self.source) else None

    def _starts_with(self, text: str) -> bool:
        return self.source.startswith(text, self._index)

    def _starts_with_any(self, choices: frozenset[str]) -> bool:
        return any(self._starts_with(choice) for choice in choices)

    def _advance(self) -> None:
        character = self._current()

        if character == "\r":
            self._index += 1
            if not self._at_end() and self._current() == "\n":
                self._index += 1
            self._line += 1
            self._column = 1
        elif character == "\n":
            self._index += 1
            self._line += 1
            self._column = 1
        else:
            self._index += 1
            self._column += 1

    def _skip_whitespace(self) -> None:
        while not self._at_end() and self._current().isspace():
            self._advance()

    def _skip_line_comment(self) -> None:
        while not self._at_end() and self._current() not in "\r\n":
            self._advance()

    def _skip_block_comment(self) -> None:
        start_line = self._line
        start_column = self._column
        self._advance()
        self._advance()

        while not self._at_end() and not self._starts_with("*/"):
            self._advance()

        if self._at_end():
            raise LexError(
                "unterminated block comment",
                line=start_line,
                column=start_column,
            )

        self._advance()
        self._advance()

    def _scan_word(self) -> Token:
        start_index = self._index
        start_line = self._line
        start_column = self._column

        while not self._at_end() and self._is_identifier_part(self._current()):
            self._advance()

        lexeme = self.source[start_index : self._index]
        token_type = (
            TokenType.KEYWORD
            if lexeme.upper() in KEYWORDS
            else TokenType.IDENTIFIER
        )
        return Token(token_type, lexeme, start_line, start_column)

    def _scan_number(self) -> Token:
        start_index = self._index
        start_line = self._line
        start_column = self._column

        while not self._at_end() and "0" <= self._current() <= "9":
            self._advance()

        if not self._at_end() and self._current() == ".":
            if self._peek() is None or not self._peek().isdigit():
                self._advance()
                lexeme = self.source[start_index : self._index]
                raise LexError(
                    f"invalid number {lexeme!r}: digits are required after the decimal point",
                    line=start_line,
                    column=start_column,
                )
            self._advance()
            while not self._at_end() and "0" <= self._current() <= "9":
                self._advance()

        if not self._at_end() and self._is_identifier_start(self._current()):
            while not self._at_end() and self._is_identifier_part(self._current()):
                self._advance()
            lexeme = self.source[start_index : self._index]
            raise LexError(
                f"invalid number {lexeme!r}: a number cannot be followed by an identifier",
                line=start_line,
                column=start_column,
            )

        lexeme = self.source[start_index : self._index]
        return Token(TokenType.CONST, lexeme, start_line, start_column)

    def _scan_string(self) -> Token:
        start_index = self._index
        start_line = self._line
        start_column = self._column
        self._advance()

        while not self._at_end():
            if self._current() in "\r\n":
                raise LexError(
                    "unterminated string literal before end of line",
                    line=start_line,
                    column=start_column,
                )
            if self._current() != "'":
                self._advance()
                continue
            if self._peek() == "'":
                self._advance()
                self._advance()
                continue

            self._advance()
            lexeme = self.source[start_index : self._index]
            return Token(TokenType.CONST, lexeme, start_line, start_column)

        raise LexError(
            "unterminated string literal",
            line=start_line,
            column=start_column,
        )

    def _scan_operator(self, *, length: int) -> Token:
        start_index = self._index
        start_line = self._line
        start_column = self._column
        for _ in range(length):
            self._advance()
        lexeme = self.source[start_index : self._index]
        return Token(TokenType.OPERATOR, lexeme, start_line, start_column)

    @staticmethod
    def _is_identifier_start(character: str) -> bool:
        return character == "_" or "A" <= character <= "Z" or "a" <= character <= "z"

    @staticmethod
    def _is_identifier_part(character: str) -> bool:
        return Lexer._is_identifier_start(character) or "0" <= character <= "9"


__all__ = ["Lexer", "Token", "TokenType"]
