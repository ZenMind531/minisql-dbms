"""Shared semantic error used by catalog validation and semantic analysis."""


class SemanticError(Exception):
    """A semantic diagnostic with a 1-based source position."""

    def __init__(self, message: str, line: int = 1, column: int = 1):
        self.type = "SemanticError"
        self.line = line
        self.column = column
        self.message = message
        super().__init__(f"{self.type} at {line}:{column}: {message}")


__all__ = ["SemanticError"]
