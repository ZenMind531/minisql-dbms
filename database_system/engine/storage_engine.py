"""StorageEngine：行 ↔ 页的翻译层（T029）。

上层（Executor）只说 Python tuple，下层（C 的 BufferPool/Page）只认 bytes。
翻译只在这一层发生：

    tuple  ──encode_row──▶  bytes  ──Page.insert_row──▶  页面
    tuple  ◀──decode_row──  bytes  ◀──Page.rows───────  页面

行格式（research.md 决策 3，定长）：
    INT        → struct '<i'，4 字节
    VARCHAR(n) → UTF-8 编码后补 \\x00 至 n 字节

定长意味着每行宽度相同，页内定位 O(1)，编解码就是拼接与切片。
"""

from __future__ import annotations

import struct
from pathlib import Path
from typing import Callable, Iterator

from database_system.sql_compiler.ast_nodes import ColumnDef, TypeKind
from database_system.sql_compiler.catalog import TableSchema
from database_system.storage.buffer import BufferPool
from database_system.storage.file_manager import FileManager
from database_system.utils.constants import PAGE_SIZE
from database_system.utils.errors import StorageError

INT_FORMAT = "<i"
INT_SIZE = 4
FIRST_DATA_PAGE = 1  # 页 0 是文件头页，用户数据从页 1 开始


def _width(column: ColumnDef) -> int:
    """一列占多少字节：INT 固定 4，VARCHAR 就是声明长度。"""
    if column.type_spec.kind is TypeKind.INT:
        return INT_SIZE
    return column.type_spec.length


def encode_row(row: tuple, columns: list[ColumnDef]) -> bytes:
    """tuple → 定长字节串。调用前语义层已保证类型与长度合法。"""
    chunks = []
    for value, column in zip(row, columns):
        if column.type_spec.kind is TypeKind.INT:
            chunks.append(struct.pack(INT_FORMAT, value))
        else:
            chunks.append(value.encode("utf-8").ljust(_width(column), b"\x00"))
    return b"".join(chunks)


def decode_row(data: bytes, columns: list[ColumnDef]) -> tuple:
    """定长字节串 → tuple。VARCHAR 去掉右侧补位的零字节。"""
    values = []
    pos = 0
    for column in columns:
        width = _width(column)
        chunk = data[pos:pos + width]
        pos += width
        if column.type_spec.kind is TypeKind.INT:
            values.append(struct.unpack(INT_FORMAT, chunk)[0])
        else:
            values.append(chunk.rstrip(b"\x00").decode("utf-8"))
    return tuple(values)


class StorageEngine:
    """每张表一个 .dat 文件配一个 BufferPool；这一层只管行 ↔ 页。"""

    def __init__(self, data_dir: str, buffer_capacity: int = 64, policy: str = "LRU"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._buffer_capacity = buffer_capacity
        self._policy = policy
        self._open_tables: dict[str, tuple[FileManager, BufferPool]] = {}
        self._schemas: dict[str, TableSchema] = {}

    # ---------- 表 ----------
    def create_table(self, schema: TableSchema) -> None:
        """只创建并初始化 .dat 文件；目录登记由 CatalogManager 负责。"""
        self._schemas[schema.name] = schema
        self._open(schema.name)

    def attach_table(self, schema: TableSchema) -> None:
        """Attach an existing table file to its recovered schema."""
        path = self.data_dir / f"{schema.name}.dat"
        if not path.is_file():
            raise StorageError(f"表 '{schema.name}' 的数据文件不存在")
        try:
            size = path.stat().st_size
        except OSError as error:
            raise StorageError(
                f"无法检查表 '{schema.name}' 的数据文件: {error}"
            ) from error
        if size < PAGE_SIZE:
            raise StorageError(f"表 '{schema.name}' 的数据文件不完整")
        try:
            self._open(schema.name)
        except (OSError, ValueError) as error:
            raise StorageError(
                f"无法打开表 '{schema.name}' 的数据文件: {error}"
            ) from error
        self._schemas[schema.name] = schema

    def _open(self, table: str) -> tuple[FileManager, BufferPool]:
        handle = self._open_tables.get(table)
        if handle is None:
            manager = FileManager(str(self.data_dir / f"{table}.dat"))
            handle = (manager, BufferPool(manager, self._buffer_capacity, self._policy))
            self._open_tables[table] = handle
        return handle

    def _schema(self, table: str) -> TableSchema:
        schema = self._schemas.get(table)
        if schema is None:
            raise StorageError(f"表 '{table}' 尚未打开")
        return schema

    # ---------- 行 ----------
    def insert_row(self, table: str, row: tuple) -> None:
        schema = self._schema(table)
        data = encode_row(row, schema.columns)
        manager, pool = self._open(table)
        for page_id in range(FIRST_DATA_PAGE, manager.page_count()):
            page = pool.get_page(page_id)
            if page.insert_row(data) is not None:
                pool.unpin_page(page_id, dirty=True)
                return
            pool.unpin_page(page_id)  # 这页放不下，换下一页
        page_id = manager.allocate_page()  # 所有页都满，开新页
        page = pool.get_page(page_id)
        page.insert_row(data)
        pool.unpin_page(page_id, dirty=True)

    def scan(self, table: str) -> Iterator[tuple]:
        schema = self._schema(table)
        manager, pool = self._open(table)
        for page_id in range(FIRST_DATA_PAGE, manager.page_count()):
            page = pool.get_page(page_id)
            # 先整页解完再 unpin：避免生成器停在半路时页一直被 pin 住
            rows = [decode_row(data, schema.columns) for _, data in page.rows()]
            pool.unpin_page(page_id)
            yield from rows

    def delete_where(self, table: str, pred: Callable[[tuple], bool]) -> int:
        schema = self._schema(table)
        manager, pool = self._open(table)
        deleted = 0
        for page_id in range(FIRST_DATA_PAGE, manager.page_count()):
            page = pool.get_page(page_id)
            victims = [slot for slot, data in page.rows()
                       if pred(decode_row(data, schema.columns))]
            for slot in victims:
                page.delete_row(slot)
            pool.unpin_page(page_id, dirty=bool(victims))
            deleted += len(victims)
        return deleted

    def flush(self) -> None:
        for _, pool in self._open_tables.values():
            pool.flush_all()

    def close(self) -> None:
        """Flush buffered pages and close every table file."""
        for manager, pool in self._open_tables.values():
            pool.flush_all()
            manager.close()
        self._open_tables.clear()
