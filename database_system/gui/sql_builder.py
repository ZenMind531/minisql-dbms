from __future__ import annotations

import re
from typing import Any, Iterable, Sequence

_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")


def quote_identifier(value: str) -> str:
    if not _IDENTIFIER.fullmatch(value):
        raise ValueError(f"invalid SQL identifier: {value!r}")
    return value


def literal_sql(value: Any) -> str:
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, int):
        return str(value)
    return "'" + str(value).replace("'", "''") + "'"


def build_create_table(table: str, columns: Iterable[tuple[str, str]]) -> str:
    definitions = [f"{quote_identifier(name)} {type_text}" for name, type_text in columns]
    if not definitions:
        raise ValueError("CREATE TABLE requires at least one column")
    return f"CREATE TABLE {quote_identifier(table)}({', '.join(definitions)});"


def build_browse_table(table: str, limit: int = 200) -> str:
    if limit < 1:
        raise ValueError("browse limit must be positive")
    return f"SELECT * FROM {quote_identifier(table)} LIMIT {limit};"


def build_insert(table: str, columns: Sequence[str], values: Sequence[Any]) -> str:
    if len(columns) != len(values):
        raise ValueError("column/value count mismatch")
    names = ", ".join(quote_identifier(name) for name in columns)
    literals = ", ".join(literal_sql(value) for value in values)
    return f"INSERT INTO {quote_identifier(table)}({names}) VALUES ({literals});"


def build_update(table: str, columns: Sequence[str], values: Sequence[Any],
                 old_values: Sequence[Any]) -> str:
    if not (len(columns) == len(values) == len(old_values)):
        raise ValueError("column/value count mismatch")
    assignments = ", ".join(
        f"{quote_identifier(name)} = {literal_sql(value)}"
        for name, value in zip(columns, values)
    )
    predicate = " AND ".join(
        f"{quote_identifier(name)} = {literal_sql(value)}"
        for name, value in zip(columns, old_values)
    )
    return f"UPDATE {quote_identifier(table)} SET {assignments} WHERE {predicate};"


def build_delete_row(table: str, columns: Sequence[str], values: Sequence[Any]) -> str:
    if len(columns) != len(values):
        raise ValueError("column/value count mismatch")
    predicate = " AND ".join(
        f"{quote_identifier(name)} = {literal_sql(value)}"
        for name, value in zip(columns, values)
    )
    return f"DELETE FROM {quote_identifier(table)} WHERE {predicate};"


def build_drop_table(table: str) -> str:
    return f"DROP TABLE {quote_identifier(table)};"

