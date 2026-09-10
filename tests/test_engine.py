import struct
from pathlib import Path

import pytest

from database_system.engine.catalog_manager import CATALOG_SCHEMA, CatalogManager
from database_system.engine.executor import Executor
from database_system.engine.minidb import MiniDB
from database_system.engine.storage_engine import StorageEngine
from database_system.sql_compiler.ast_nodes import ColumnDef, TypeKind, TypeSpec
from database_system.sql_compiler.catalog import Catalog, TableSchema
from database_system.sql_compiler.planner import CreateTable
from database_system.utils.constants import PAGE_SIZE
from database_system.utils.errors import StorageError


def column(name: str, kind: TypeKind, length: int | None = None) -> ColumnDef:
    return ColumnDef(
        line=1,
        column=1,
        name=name,
        type_spec=TypeSpec(kind, length),
    )


def student_schema() -> TableSchema:
    return TableSchema(
        name="student",
        columns=[
            column("id", TypeKind.INT),
            column("name", TypeKind.VARCHAR, 32),
        ],
    )


def test_fresh_manager_bootstraps_queryable_catalog(tmp_path: Path) -> None:
    engine = StorageEngine(str(tmp_path))
    try:
        catalog = CatalogManager(engine).load()

        assert (tmp_path / "__catalog__.dat").is_file()
        assert catalog.find_table("__catalog__") == CATALOG_SCHEMA
        assert list(engine.scan("__catalog__")) == []
    finally:
        engine.close()


def test_register_table_writes_one_catalog_row_per_column(tmp_path: Path) -> None:
    engine = StorageEngine(str(tmp_path))
    try:
        manager = CatalogManager(engine)
        manager.load()
        schema = student_schema()
        engine.create_table(schema)

        manager.register_table(schema)

        assert list(engine.scan("__catalog__")) == [
            ("student", "id", "INT", 0),
            ("student", "name", "VARCHAR(32)", 1),
        ]

        # register_table() must make metadata visible on disk immediately,
        # without relying on StorageEngine.close() to flush dirty pages.
        reopened = StorageEngine(str(tmp_path))
        try:
            reloaded_catalog = CatalogManager(reopened).load()
            assert reloaded_catalog.find_table("student") == schema
        finally:
            reopened.close()
    finally:
        engine.close()


def test_reopening_reconstructs_exact_schema(tmp_path: Path) -> None:
    schema = student_schema()
    engine = StorageEngine(str(tmp_path))
    manager = CatalogManager(engine)
    manager.load()
    engine.create_table(schema)
    manager.register_table(schema)
    engine.insert_row("student", (7, "Alice"))
    engine.close()

    reopened = StorageEngine(str(tmp_path))
    try:
        catalog = CatalogManager(reopened).load()

        assert catalog.find_table("student") == schema
        assert list(reopened.scan("student")) == [(7, "Alice")]
    finally:
        reopened.close()


def test_load_rejects_invalid_catalog_type(tmp_path: Path) -> None:
    engine = StorageEngine(str(tmp_path))
    CatalogManager(engine).load()
    engine.create_table(student_schema())
    engine.insert_row("__catalog__", ("student", "id", "FLOAT", 0))
    engine.close()

    reopened = StorageEngine(str(tmp_path))
    try:
        with pytest.raises(StorageError):
            CatalogManager(reopened).load()
    finally:
        reopened.close()


@pytest.mark.parametrize(
    "orders",
    [(0, 0), (0, 2)],
    ids=["duplicate", "gapped"],
)
def test_load_rejects_non_contiguous_catalog_order(
    tmp_path: Path, orders: tuple[int, int]
) -> None:
    engine = StorageEngine(str(tmp_path))
    CatalogManager(engine).load()
    engine.create_table(student_schema())
    engine.insert_row("__catalog__", ("student", "id", "INT", orders[0]))
    engine.insert_row(
        "__catalog__", ("student", "name", "VARCHAR(32)", orders[1])
    )
    engine.close()

    reopened = StorageEngine(str(tmp_path))
    try:
        with pytest.raises(StorageError):
            CatalogManager(reopened).load()
    finally:
        reopened.close()


def test_load_rejects_duplicate_catalog_column(tmp_path: Path) -> None:
    engine = StorageEngine(str(tmp_path))
    CatalogManager(engine).load()
    engine.create_table(student_schema())
    engine.insert_row("__catalog__", ("student", "id", "INT", 0))
    engine.insert_row("__catalog__", ("student", "id", "INT", 1))
    engine.close()

    reopened = StorageEngine(str(tmp_path))
    try:
        with pytest.raises(StorageError):
            CatalogManager(reopened).load()
    finally:
        reopened.close()


def test_load_rejects_missing_table_file(tmp_path: Path) -> None:
    engine = StorageEngine(str(tmp_path))
    CatalogManager(engine).load()
    engine.insert_row("__catalog__", ("student", "id", "INT", 0))
    engine.close()

    reopened = StorageEngine(str(tmp_path))
    try:
        with pytest.raises(StorageError):
            CatalogManager(reopened).load()
    finally:
        reopened.close()


def test_load_reports_corrupt_catalog_file_as_storage_error(tmp_path: Path) -> None:
    engine = StorageEngine(str(tmp_path))
    CatalogManager(engine).load()
    engine.close()
    (tmp_path / "__catalog__.dat").write_bytes(b"\x00" * 4096)

    reopened = StorageEngine(str(tmp_path))
    try:
        with pytest.raises(StorageError):
            CatalogManager(reopened).load()
    finally:
        reopened.close()


@pytest.mark.parametrize("target", ["catalog", "table"])
def test_load_rejects_truncated_existing_file_without_overwriting(
    tmp_path: Path, target: str
) -> None:
    truncated = b"existing-but-truncated"
    if target == "catalog":
        path = tmp_path / "__catalog__.dat"
        path.write_bytes(truncated)
    else:
        engine = StorageEngine(str(tmp_path))
        manager = CatalogManager(engine)
        manager.load()
        schema = student_schema()
        engine.create_table(schema)
        manager.register_table(schema)
        engine.close()
        path = tmp_path / "student.dat"
        path.write_bytes(truncated)

    reopened = StorageEngine(str(tmp_path))
    try:
        with pytest.raises(StorageError):
            CatalogManager(reopened).load()
    finally:
        reopened.close()

    assert path.read_bytes() == truncated


@pytest.mark.parametrize(
    "schema",
    [
        TableSchema(
            name="表" * 86,
            columns=[column("id", TypeKind.INT)],
        ),
        TableSchema(
            name="student",
            columns=[
                column("id", TypeKind.INT),
                column("列" * 86, TypeKind.VARCHAR, 32),
            ],
        ),
    ],
    ids=["table-name", "later-column-name"],
)
def test_register_rejects_names_over_255_utf8_bytes_before_writing(
    tmp_path: Path, schema: TableSchema
) -> None:
    engine = StorageEngine(str(tmp_path))
    try:
        manager = CatalogManager(engine)
        manager.load()

        with pytest.raises(StorageError):
            manager.register_table(schema)

        assert list(engine.scan("__catalog__")) == []
    finally:
        engine.close()


@pytest.mark.parametrize(
    ("corruption", "cause_type"),
    [
        ("invalid-utf8", UnicodeDecodeError),
        ("invalid-slot-count", struct.error),
        ("missing-declared-page", ValueError),
    ],
)
def test_load_wraps_catalog_scan_and_decode_corruption(
    tmp_path: Path, corruption: str, cause_type: type[Exception]
) -> None:
    engine = StorageEngine(str(tmp_path))
    manager = CatalogManager(engine)
    manager.load()
    if corruption != "missing-declared-page":
        schema = student_schema()
        engine.create_table(schema)
        manager.register_table(schema)
    engine.close()

    catalog_path = tmp_path / "__catalog__.dat"
    with catalog_path.open("r+b") as catalog_file:
        if corruption == "invalid-utf8":
            catalog_file.seek(PAGE_SIZE + 32)
            (row_offset,) = struct.unpack("<H", catalog_file.read(2))
            catalog_file.seek(PAGE_SIZE + row_offset)
            catalog_file.write(b"\xff")
        elif corruption == "invalid-slot-count":
            catalog_file.seek(PAGE_SIZE + 5)
            catalog_file.write(struct.pack("<H", 65535))
        else:
            catalog_file.seek(8)
            catalog_file.write(struct.pack("<I", 2))

    reopened = StorageEngine(str(tmp_path))
    try:
        with pytest.raises(StorageError, match="__catalog__") as caught:
            CatalogManager(reopened).load()
        assert isinstance(caught.value.__cause__, cause_type)
    finally:
        reopened.close()


@pytest.mark.parametrize(
    "read_error",
    [OSError("disk read failed"), StorageError("page read failed")],
    ids=["os-error", "storage-error"],
)
def test_load_adds_catalog_context_to_storage_read_failures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, read_error: Exception
) -> None:
    engine = StorageEngine(str(tmp_path))
    manager = CatalogManager(engine)
    manager.load()

    def broken_scan(table: str):
        assert table == "__catalog__"
        raise read_error
        yield

    monkeypatch.setattr(engine, "scan", broken_scan)
    try:
        with pytest.raises(StorageError, match="__catalog__") as caught:
            manager.load()
        assert caught.value.__cause__ is read_error
    finally:
        engine.close()


def test_minidb_create_survives_close_and_restart(tmp_path: Path) -> None:
    db = MiniDB(str(tmp_path))
    try:
        assert db.execute("CREATE TABLE student (id INT, name VARCHAR(32));") == "OK"
        assert db.execute("INSERT INTO student VALUES (7, 'Alice');") == (
            "1 row(s) inserted"
        )
    finally:
        db.close()

    reopened = MiniDB(str(tmp_path))
    try:
        assert reopened.execute("SELECT id, name FROM student;") == "(7, 'Alice')"
    finally:
        reopened.close()


def test_create_table_rolls_back_only_new_file_when_catalog_write_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = StorageEngine(str(tmp_path))
    manager = CatalogManager(engine)
    catalog = manager.load()
    schema = TableSchema(name="broken", columns=[column("id", TypeKind.INT)])
    catalog_path = tmp_path / "__catalog__.dat"
    catalog_bytes = catalog_path.read_bytes()

    def fail_registration(table_schema: TableSchema) -> None:
        assert table_schema == schema
        raise StorageError("injected catalog failure")

    monkeypatch.setattr(manager, "register_table", fail_registration)
    try:
        with pytest.raises(StorageError, match="injected catalog failure"):
            manager.create_table(schema, catalog)

        assert not (tmp_path / "broken.dat").exists()
        assert catalog_path.read_bytes() == catalog_bytes
        assert catalog.find_table("broken") is None
        assert catalog.find_table("__catalog__") == CATALOG_SCHEMA
    finally:
        engine.close()


def test_create_table_removes_partial_catalog_rows_when_second_insert_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = StorageEngine(str(tmp_path))
    manager = CatalogManager(engine)
    catalog = manager.load()
    stable_schema = TableSchema(
        name="stable", columns=[column("id", TypeKind.INT)]
    )
    manager.create_table(stable_schema, catalog)
    schema = TableSchema(
        name="broken",
        columns=[
            column("id", TypeKind.INT),
            column("name", TypeKind.VARCHAR, 32),
        ],
    )
    real_insert = engine.insert_row
    catalog_inserts = 0

    def fail_second_catalog_insert(table: str, row: tuple) -> None:
        nonlocal catalog_inserts
        if table == "__catalog__":
            catalog_inserts += 1
            if catalog_inserts == 2:
                raise StorageError("injected second catalog insert failure")
        real_insert(table, row)

    monkeypatch.setattr(engine, "insert_row", fail_second_catalog_insert)
    try:
        with pytest.raises(StorageError, match="second catalog insert failure"):
            manager.create_table(schema, catalog)

        assert not (tmp_path / "broken.dat").exists()
        assert list(engine.scan("__catalog__")) == [
            ("stable", "id", "INT", 0)
        ]
        assert catalog.find_table("broken") is None
        assert catalog.find_table("__catalog__") == CATALOG_SCHEMA
    finally:
        engine.close()

    reopened = MiniDB(str(tmp_path))
    try:
        assert reopened.catalog.find_table("broken") is None
        assert reopened.catalog.find_table("stable") == stable_schema
        assert list(reopened.engine.scan("__catalog__")) == [
            ("stable", "id", "INT", 0)
        ]
    finally:
        reopened.close()


def test_create_table_reports_registration_and_cleanup_failures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = StorageEngine(str(tmp_path))
    manager = CatalogManager(engine)
    catalog = manager.load()
    schema = TableSchema(name="broken", columns=[column("id", TypeKind.INT)])
    registration_error = StorageError("registration failed")

    def fail_registration(table_schema: TableSchema) -> None:
        raise registration_error

    def fail_catalog_cleanup(table: str, pred) -> int:
        assert table == "__catalog__"
        assert pred(("broken", "id", "INT", 0))
        assert not pred(("stable", "id", "INT", 0))
        raise StorageError("catalog cleanup failed")

    monkeypatch.setattr(manager, "register_table", fail_registration)
    monkeypatch.setattr(engine, "delete_where", fail_catalog_cleanup)
    try:
        with pytest.raises(StorageError) as caught:
            manager.create_table(schema, catalog)

        assert "registration failed" in caught.value.message
        assert "catalog cleanup failed" in caught.value.message
        assert caught.value.__cause__ is registration_error
        assert not (tmp_path / "broken.dat").exists()
        assert catalog.find_table("broken") is None
    finally:
        engine.close()


def test_storage_create_rejects_an_existing_table_file(tmp_path: Path) -> None:
    engine = StorageEngine(str(tmp_path))
    schema = student_schema()
    try:
        engine.create_table(schema)
        original = (tmp_path / "student.dat").read_bytes()

        with pytest.raises(StorageError, match="student"):
            engine.create_table(schema)

        assert (tmp_path / "student.dat").read_bytes() == original
    finally:
        engine.close()


def test_storage_remove_rejects_system_catalog(tmp_path: Path) -> None:
    engine = StorageEngine(str(tmp_path))
    try:
        CatalogManager(engine).load()

        with pytest.raises(StorageError, match="__catalog__"):
            engine.remove_table("__catalog__")

        assert (tmp_path / "__catalog__.dat").is_file()
    finally:
        engine.close()


def test_executor_two_argument_constructor_remains_supported(tmp_path: Path) -> None:
    engine = StorageEngine(str(tmp_path))
    catalog = Catalog()
    try:
        executor = Executor(engine, catalog)

        assert executor.execute(
            CreateTable("student", student_schema().columns)
        ) == "OK"
        assert (tmp_path / "student.dat").is_file()
        assert catalog.find_table("student") == student_schema()
    finally:
        engine.close()
