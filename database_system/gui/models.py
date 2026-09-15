from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class ColumnInfo:
    name: str
    type_text: str


@dataclass(frozen=True, slots=True)
class TableInfo:
    name: str
    columns: tuple[ColumnInfo, ...]


@dataclass(frozen=True, slots=True)
class ErrorInfo:
    error_type: str
    message: str
    line: int | None = None
    column: int | None = None


@dataclass(frozen=True, slots=True)
class ExecutionResult:
    statement_type: str
    columns: tuple[str, ...] = ()
    rows: tuple[tuple[Any, ...], ...] = ()
    message: str = ""
    original_plan: str = ""
    optimized_plan: str = ""
    original_plan_json: dict[str, Any] = field(default_factory=dict)
    optimized_plan_json: dict[str, Any] = field(default_factory=dict)
    elapsed_ms: float = 0.0
    success: bool = True


@dataclass(frozen=True, slots=True)
class ExecutionBatch:
    results: tuple[ExecutionResult, ...] = ()
    error: ErrorInfo | None = None

