"""Persist and restore table schemas through the ``__catalog__`` table."""

from __future__ import annotations

import re
import struct

from database_system.engine.storage_engine import StorageEngine
from database_system.sql_compiler.ast_nodes import ColumnDef, TypeKind, TypeSpec
from database_system.sql_compiler.catalog import Catalog, TableSchema
from database_system.utils.errors import StorageError

CATALOG_TABLE = "__catalog__"
CATALOG_SCHEMA = TableSchema(
    name=CATALOG_TABLE,
    columns=[
        ColumnDef(
            line=1,
            column=1,
            name="table_name",
            type_spec=TypeSpec(TypeKind.VARCHAR, 255),
        ),
        ColumnDef(
            line=1,
            column=1,
            name="col_name",
            type_spec=TypeSpec(TypeKind.VARCHAR, 255),
        ),
        ColumnDef(
            line=1,
            column=1,
            name="col_type",
            type_spec=TypeSpec(TypeKind.VARCHAR, 16),
        ),
        ColumnDef(
            line=1,
            column=1,
            name="col_order",
            type_spec=TypeSpec(TypeKind.INT),
        ),
    ],
)

_VARCHAR_TYPE = re.compile(r"VARCHAR\(([1-9][0-9]{0,2})\)")


def _validate_name(name: str, description: str) -> None:
    try:
        encoded = name.encode("utf-8")
    except UnicodeEncodeError as error:
        raise StorageError(f"{description}不能编码为 UTF-8") from error
    if len(encoded) > 255:
        raise StorageError(f"{description}的 UTF-8 长度不能超过 255 字节")


def _encode_type(type_spec: TypeSpec) -> str:
    if type_spec.kind is TypeKind.INT:
        return "INT"
    if type_spec.kind is TypeKind.VARCHAR:
        return f"VARCHAR({type_spec.length})"
    raise StorageError(f"目录不支持列类型 '{type_spec.kind}'")


def _parse_type(text: str) -> TypeSpec:
    if text == "INT":
        return TypeSpec(TypeKind.INT)
    match = _VARCHAR_TYPE.fullmatch(text)
    if match is not None:
        length = int(match.group(1))
        if length <= 255:
            return TypeSpec(TypeKind.VARCHAR, length)
    raise StorageError(f"目录中的列类型无效: '{text}'")


class CatalogManager:
    """Own the on-disk schema catalog built on top of ``StorageEngine``."""

    def __init__(self, engine: StorageEngine):
        self.engine = engine

    def load(self) -> Catalog:
        """Bootstrap or scan ``__catalog__`` and rebuild in-memory schemas."""
        catalog_path = self.engine.data_dir / f"{CATALOG_TABLE}.dat"
        if catalog_path.exists():
            self.engine.attach_table(CATALOG_SCHEMA)
        else:
            self.engine.create_table(CATALOG_SCHEMA)

        catalog = Catalog()
        catalog.create_table(CATALOG_SCHEMA.name, CATALOG_SCHEMA.columns)

        try:
            rows = list(self.engine.scan(CATALOG_TABLE))
        except (
            struct.error,
            UnicodeDecodeError,
            ValueError,
            OSError,
            StorageError,
        ) as error:
            raise StorageError(
                f"读取系统目录 '{CATALOG_TABLE}' 失败: {error}"
            ) from error

        grouped: dict[str, list[tuple[str, str, int]]] = {}
        for table_name, column_name, type_text, column_order in rows:
            grouped.setdefault(table_name, []).append(
                (column_name, type_text, column_order)
            )

        for table_name, rows in grouped.items():
            ordered = sorted(rows, key=lambda row: row[2])
            if [row[2] for row in ordered] != list(range(len(ordered))):
                raise StorageError(
                    f"表 '{table_name}' 的目录列序必须从 0 开始且连续"
                )
            column_names = [row[0] for row in ordered]
            if len(set(column_names)) != len(column_names):
                raise StorageError(f"表 '{table_name}' 的目录包含重复列名")
            columns = [
                ColumnDef(
                    line=1,
                    column=1,
                    name=column_name,
                    type_spec=_parse_type(type_text),
                )
                for column_name, type_text, _ in ordered
            ]
            schema = TableSchema(name=table_name, columns=columns)
            self.engine.attach_table(schema)
            catalog.create_table(schema.name, schema.columns)

        return catalog

    def register_table(self, schema: TableSchema) -> None:
        """Append one durable catalog row for every schema column."""
        _validate_name(schema.name, "表名")
        for column in schema.columns:
            _validate_name(column.name, f"表 '{schema.name}' 的列名")

        for position, column in enumerate(schema.columns):
            self.engine.insert_row(
                CATALOG_TABLE,
                (schema.name, column.name, _encode_type(column.type_spec), position),
            )
        self.engine.flush()


__all__ = ["CATALOG_SCHEMA", "CatalogManager"]
