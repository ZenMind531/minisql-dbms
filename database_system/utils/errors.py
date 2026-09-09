"""Unified diagnostics for every MiniSQL stage (T006).

Constitution principle II requires that any illegal input produce a
structured ``错误类型 + 行号 + 列号 + 原因`` instead of an uncaught crash.
Every stage therefore raises one of the five classes below, all of which
share :class:`MiniSQLError` and expose the same four attributes:

===========  =========================================================
``type``     class name, e.g. ``"LexError"``
``line``     1-based source line
``column``   1-based source column
``message``  human readable reason
===========  =========================================================

``MiniSQLError`` exists so the CLI can write ``except MiniSQLError`` and
report a diagnostic, while genuine implementation bugs (``TypeError``,
``AttributeError``, ...) still propagate and stay visible.

The compiler contract spells the payload ``reason``; ``message`` is the
canonical attribute and ``reason`` is accepted as an alias in both the
constructor and as a read-only property.
"""

from __future__ import annotations


class MiniSQLError(Exception):
    """Base class for all locatable MiniSQL diagnostics.

    Not raised directly. Subclasses set ``type`` from their own class name,
    so adding a stage never requires touching this constructor.
    """

    def __init__(
        self,
        message: str | None = None,
        line: int = 1,
        column: int = 1,
        *,
        reason: str | None = None,
    ):
        text = self._resolve_text(message, reason)
        self._validate_position(line, column)
        self.type = type(self).__name__
        self.line = line
        self.column = column
        self.message = text
        super().__init__(f"{self.type} at {line}:{column}: {text}")

    @staticmethod
    def _resolve_text(message: str | None, reason: str | None) -> str:
        """Accept ``message`` or the contract's ``reason``, never both."""
        if message is not None and reason is not None:
            if message != reason:
                raise TypeError("message and reason must not disagree")
            return message
        if message is not None:
            return message
        if reason is not None:
            return reason
        raise TypeError("a diagnostic requires a message")

    @staticmethod
    def _validate_position(line: int, column: int) -> None:
        """Positions mirror AST nodes, which are 1-based everywhere."""
        if line < 1 or column < 1:
            raise ValueError("error source positions are 1-based")

    @property
    def reason(self) -> str:
        """Contract-facing alias of :attr:`message`."""
        return self.message


class LexError(MiniSQLError):
    """Illegal character, number, string, or comment found by the Lexer (A)."""


class ParseError(MiniSQLError):
    """Grammar violation found by the Parser (A).

    The message is expected to name the unexpected token and the expected set.
    """


class SemanticError(MiniSQLError):
    """Name binding or type violation found by Catalog/SemanticAnalyzer (B)."""


class StorageError(MiniSQLError):
    """Page, file, or buffer pool failure in the storage layer (C)."""


class ExecError(MiniSQLError):
    """Runtime failure while the Executor evaluates a plan (D)."""


__all__ = [
    "ExecError",
    "LexError",
    "MiniSQLError",
    "ParseError",
    "SemanticError",
    "StorageError",
]
