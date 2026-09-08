"""Lexical analysis for the supported MiniSQL grammar."""

from dataclasses import dataclass
from enum import StrEnum


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
    }
)

DELIMITERS = frozenset({"(", ")", ",", ";"})


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
            elif self._is_identifier_start(character):
                tokens.append(self._scan_word())
            elif character in DELIMITERS:
                tokens.append(
                    Token(TokenType.DELIMITER, character, self._line, self._column)
                )
                self._advance()
            else:
                raise NotImplementedError(
                    f"tokenization for {character!r} is not implemented yet"
                )

        tokens.append(Token(TokenType.EOF, "", self._line, self._column))
        return tokens

    def _at_end(self) -> bool:
        return self._index >= len(self.source)

    def _current(self) -> str:
        return self.source[self._index]

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

    @staticmethod
    def _is_identifier_start(character: str) -> bool:
        return character == "_" or "A" <= character <= "Z" or "a" <= character <= "z"

    @staticmethod
    def _is_identifier_part(character: str) -> bool:
        return Lexer._is_identifier_start(character) or "0" <= character <= "9"


__all__ = ["Lexer", "Token", "TokenType"]
