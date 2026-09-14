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
from database_system.utils.errors import ExecError, SemanticError, StorageError


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


# ---------- 执行器边界 ----------
# 下面三条曾经都会穿透 MiniSQLError：两条崩掉整个 REPL，一条静默丢数据。
# 语义层只管类型、不管取值范围与行宽，引擎层是最后一道防线。


def test_unimplemented_plan_reports_exec_error_instead_of_crashing(
    tmp_path: Path,
) -> None:
    """前端解析得出来、执行器还没有分支的节点，必须干净报错。

    过去这类节点掉进 execute() 的默认分支 _select()，_base_table() 访问
    plan.child 时抛 AttributeError —— 不是 MiniSQLError，CLI 不接，
    整个 REPL 带 traceback 退出。

    UPDATE 正是下一个这样的节点：语义层已经放行，执行器还没实现。
    DROP TABLE 也当过一阵子哨兵，现在它自己已经实现了。
    """
    db = MiniDB(str(tmp_path))
    try:
        db.execute("CREATE TABLE student(id INT);")
        db.execute("INSERT INTO student VALUES (1);")

        with pytest.raises(ExecError, match="Update"):
            db.execute("UPDATE student SET id = 2;")

        assert db.execute("SELECT * FROM student;") == "(1,)"  # 数据没被动
    finally:
        db.close()


def test_insert_int_out_of_range_raises_storage_error(tmp_path: Path) -> None:
    """INT 是 32 位有符号数；越界值过去会抛 struct.error 崩掉 REPL。"""
    db = MiniDB(str(tmp_path))
    try:
        db.execute("CREATE TABLE student(id INT);")

        with pytest.raises(StorageError, match="超出 INT 范围"):
            db.execute("INSERT INTO student VALUES (4000000000);")

        assert db.execute("SELECT * FROM student;") == ""
    finally:
        db.close()


def test_insert_row_wider_than_a_page_raises_storage_error(tmp_path: Path) -> None:
    """一行塞不满一个空页时必须报错；过去是谎报成功、静默丢数据。"""
    columns = ", ".join(f"c{i} VARCHAR(255)" for i in range(1, 17))
    values = ", ".join("'a'" for _ in range(16))
    db = MiniDB(str(tmp_path))
    try:
        db.execute(f"CREATE TABLE wide({columns});")

        with pytest.raises(StorageError, match="单页"):
            db.execute(f"INSERT INTO wide VALUES ({values});")

        assert db.execute("SELECT * FROM wide;") == ""
    finally:
        db.close()


# ---------- DROP TABLE ----------
# 前端（AST / 语义 / 计划节点）和存储层（remove_table）都齐了，缺的一直是
# 执行器这一环——DROP 掉进兜底分支报"不支持的查询计划"，表纹丝不动。


def test_drop_table_removes_file_and_metadata(tmp_path: Path) -> None:
    """DROP 要真的删干净：磁盘文件、内存元数据，一样都不能留。

    光删文件不摘内存，"幽灵表"就来了——SHOW TABLES 还列得出来，
    SELECT 语义层照样放行，一路走到扫描才炸。
    """
    db = MiniDB(str(tmp_path))
    try:
        db.execute("CREATE TABLE student(id INT);")
        db.execute("INSERT INTO student VALUES (1);")
        assert (tmp_path / "student.dat").is_file()

        assert db.execute("DROP TABLE student;") == "OK"

        assert not (tmp_path / "student.dat").exists()
        assert db.execute("SHOW TABLES;") == ""
        with pytest.raises(SemanticError, match="does not exist"):
            db.execute("SELECT * FROM student;")
    finally:
        db.close()


def test_dropped_table_stays_dropped_after_restart(tmp_path: Path) -> None:
    """目录登记删干净了，重启后表不会"复活"。

    这条盯的是删除顺序。若先删 .dat 再删 __catalog__ 里的登记行，中途失败
    就留下"目录说有、文件没有"的状态，下次 CatalogManager.load() 直接报错，
    整个数据库打不开。所以不可逆的删文件必须排在最后。
    """
    db = MiniDB(str(tmp_path))
    try:
        db.execute("CREATE TABLE student(id INT);")
        db.execute("CREATE TABLE keeper(id INT);")
        assert db.execute("DROP TABLE student;") == "OK"
    finally:
        db.close()

    reopened = MiniDB(str(tmp_path))
    try:
        assert reopened.execute("SHOW TABLES;") == "('keeper',)"
        with pytest.raises(SemanticError, match="does not exist"):
            reopened.execute("SELECT * FROM student;")
        assert reopened.execute("SELECT * FROM keeper;") == ""
    finally:
        reopened.close()

    assert not (tmp_path / "student.dat").exists()


def test_recreating_a_dropped_table_starts_empty(tmp_path: Path) -> None:
    """DROP 之后同名表能重建，且是张空表——内存摘干净了才做得到。"""
    db = MiniDB(str(tmp_path))
    try:
        db.execute("CREATE TABLE t(id INT, name VARCHAR(8));")
        db.execute("INSERT INTO t VALUES (1, 'Alice');")
        db.execute("DROP TABLE t;")

        assert db.execute("CREATE TABLE t(id INT, name VARCHAR(8));") == "OK"

        assert db.execute("SELECT * FROM t;") == ""  # 旧数据没跟着复活
    finally:
        db.close()


# ---------- LIMIT ----------
# LIMIT 落在计划树最外层（Limit → Project → Sort → Filter → SeqScan），
# 也就是最后才截断——这正是"先排序、再取前 N"能对的原因。


def _five_rows(tmp_path: Path) -> MiniDB:
    """建一张 t(id, name)，塞进 1..5 五行，返回打开的库。"""
    db = MiniDB(str(tmp_path))
    db.execute("CREATE TABLE t(id INT, name VARCHAR(8));")
    for number in range(1, 6):
        db.execute(f"INSERT INTO t VALUES ({number}, 'n{number}');")
    return db


def test_limit_takes_the_first_n_rows(tmp_path: Path) -> None:
    db = _five_rows(tmp_path)
    try:
        assert db.execute("SELECT * FROM t LIMIT 2;") == "(1, 'n1')\n(2, 'n2')"
    finally:
        db.close()


def test_limit_zero_returns_nothing(tmp_path: Path) -> None:
    """LIMIT 0 是"一行都不要"，不是"不限"——最容易写反的那个边界。"""
    db = _five_rows(tmp_path)
    try:
        assert db.execute("SELECT * FROM t LIMIT 0;") == ""
    finally:
        db.close()


def test_limit_beyond_the_table_returns_everything(tmp_path: Path) -> None:
    """要 100 行但只有 5 行：给 5 行就是了，不该报错。"""
    db = _five_rows(tmp_path)
    try:
        assert len(db.execute("SELECT * FROM t LIMIT 100;").splitlines()) == 5
    finally:
        db.close()


def test_limit_applies_after_order_by(tmp_path: Path) -> None:
    """先排序再截断。

    截断要是错发生在 Sort 之前，这里会拿到 1,2 而不是 5,4——顺序反了，
    行数却一样，光看行数发现不了。
    """
    db = _five_rows(tmp_path)
    try:
        assert db.execute(
            "SELECT * FROM t ORDER BY id DESC LIMIT 2;"
        ) == "(5, 'n5')\n(4, 'n4')"
    finally:
        db.close()


def test_limit_applies_after_where(tmp_path: Path) -> None:
    """先过滤再截断：id > 3 只剩 4、5 两行，LIMIT 1 该拿到 4。"""
    db = _five_rows(tmp_path)
    try:
        assert db.execute("SELECT * FROM t WHERE id > 3 LIMIT 1;") == "(4, 'n4')"
    finally:
        db.close()


# ---------- INSERT 列名落位 ----------


def test_insert_maps_values_by_column_name_not_source_order(tmp_path: Path) -> None:
    """列名决定落位，VALUES 的书写顺序不算数。

    过去 planner 丢弃 stmt.columns，执行器按源码顺序组行，于是
    INSERT INTO t(b, a) VALUES (1, 2) 静默存成 (1, 2)：两列都是 INT，
    类型检查毫无察觉，数据反着进库还没人吭声。
    """
    db = MiniDB(str(tmp_path))
    try:
        db.execute("CREATE TABLE t(a INT, b INT);")

        db.execute("INSERT INTO t(b, a) VALUES (1, 2);")

        assert db.execute("SELECT * FROM t;") == "(2, 1)"
    finally:
        db.close()


def test_insert_reordered_columns_works_across_types(tmp_path: Path) -> None:
    """三列全打乱且跨 INT/VARCHAR —— 落位靠列名，不靠位置。"""
    db = MiniDB(str(tmp_path))
    try:
        db.execute("CREATE TABLE student(id INT, name VARCHAR(32), age INT);")

        db.execute("INSERT INTO student(name, age, id) VALUES ('Alice', 20, 1);")

        assert db.execute("SELECT * FROM student;") == "(1, 'Alice', 20)"
    finally:
        db.close()
