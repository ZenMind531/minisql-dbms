"""Abstract syntax tree nodes for the supported MiniSQL grammar."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TypeAlias


class TypeKind(StrEnum):
    """Types understood by semantic analysis and table schemas."""

    INT = "INT"
    VARCHAR = "VARCHAR"
    BOOL = "BOOL"


class LiteralKind(StrEnum):
    """Kinds emitted by the parser for literal source forms.

    FLOAT is representable in the AST so parsing succeeds, but the current
    semantic rules reject it because MiniSQL has no supported FLOAT type.
    """

    INTEGER = "INTEGER"
    FLOAT = "FLOAT"
    STRING = "STRING"


class UnaryOperator(StrEnum):
    PLUS = "+"
    MINUS = "-"
    NOT = "NOT"


class BinaryOperator(StrEnum):
    ADD = "+"
    SUBTRACT = "-"
    MULTIPLY = "*"
    DIVIDE = "/"
    EQUAL = "="
    NOT_EQUAL = "!="
    GREATER_THAN = ">"
    GREATER_THAN_OR_EQUAL = ">="
    LESS_THAN = "<"
    LESS_THAN_OR_EQUAL = "<="
    AND = "AND"
    OR = "OR"


@dataclass(frozen=True, slots=True)
class TypeSpec:
    kind: TypeKind
    length: int | None = None

    def __post_init__(self) -> None:
        if self.kind is not TypeKind.VARCHAR and self.length is not None:
            raise ValueError(f"{self.kind.value} type must not have a length")
        if self.length is not None and self.length < 0:
            raise ValueError("VARCHAR length must not be negative")


@dataclass(slots=True, kw_only=True)
class ASTNode:
    line: int
    column: int

    def __post_init__(self) -> None:
        if self.line < 1 or self.column < 1:
            raise ValueError("AST source positions are 1-based")


@dataclass(slots=True, kw_only=True)
class Expr(ASTNode):
    resolved_type: TypeSpec | None = None


@dataclass(slots=True, kw_only=True)
class IdentifierExpr(Expr):
    name: str


@dataclass(slots=True, kw_only=True)
class LiteralExpr(Expr):
    value: int | float | str
    literal_kind: LiteralKind


@dataclass(slots=True, kw_only=True)
class UnaryExpr(Expr):
    op: UnaryOperator
    operand: Expr


@dataclass(slots=True, kw_only=True)
class BinaryExpr(Expr):
    op: BinaryOperator
    left: Expr
    right: Expr


@dataclass(slots=True, kw_only=True)
class ColumnDef(ASTNode):
    name: str
    type_spec: TypeSpec

    def __post_init__(self) -> None:
        ASTNode.__post_init__(self)
        if self.type_spec.kind not in (TypeKind.INT, TypeKind.VARCHAR):
            raise ValueError("column type must be INT or VARCHAR")
        if self.type_spec.kind is TypeKind.VARCHAR and not (
            self.type_spec.length is not None
            and 1 <= self.type_spec.length <= 255
        ):
            raise ValueError("VARCHAR length must be between 1 and 255")


@dataclass(slots=True, kw_only=True)
class CreateTableStmt(ASTNode):
    table: str
    columns: list[ColumnDef]

    def __post_init__(self) -> None:
        ASTNode.__post_init__(self)
        if not self.columns:
            raise ValueError("CREATE TABLE requires at least one column")


@dataclass(slots=True, kw_only=True)
class InsertStmt(ASTNode):
    table: str
    target_columns: list[str] | None
    values: list[Expr]

    def __post_init__(self) -> None:
        ASTNode.__post_init__(self)
        if self.target_columns is not None and not self.target_columns:
            raise ValueError("INSERT target column list must not be empty")
        if not self.values:
            raise ValueError("INSERT requires at least one value")


@dataclass(slots=True, kw_only=True)
class SelectStmt(ASTNode):
    columns: list[str] | None
    table: str
    where: Expr | None

    def __post_init__(self) -> None:
        ASTNode.__post_init__(self)
        if self.columns is not None and not self.columns:
            raise ValueError("SELECT requires at least one column or '*'")


@dataclass(slots=True, kw_only=True)
class DeleteStmt(ASTNode):
    table: str
    where: Expr | None


Stmt: TypeAlias = CreateTableStmt | InsertStmt | SelectStmt | DeleteStmt


__all__ = [
    "ASTNode",
    "BinaryExpr",
    "BinaryOperator",
    "ColumnDef",
    "CreateTableStmt",
    "DeleteStmt",
    "Expr",
    "IdentifierExpr",
    "InsertStmt",
    "LiteralExpr",
    "LiteralKind",
    "SelectStmt",
    "Stmt",
    "TypeKind",
    "TypeSpec",
    "UnaryExpr",
    "UnaryOperator",
]
