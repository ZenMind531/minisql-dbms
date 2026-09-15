from pathlib import Path

from database_system.gui.service import DatabaseService


def test_execute_query_returns_columns_rows_and_plans(tmp_path: Path) -> None:
    service = DatabaseService(tmp_path)
    try:
        service.execute("CREATE TABLE student(id INT, name VARCHAR(20));")
        service.execute("INSERT INTO student VALUES (1, 'Alice');")

        batch = service.execute("SELECT name FROM student WHERE 1 = 1 AND id > 0;")

        result = batch.results[0]
        assert result.success is True
        assert result.columns == ("name",)
        assert result.rows == (("Alice",),)
        assert "Filter" in result.original_plan
        assert "id > 0" in result.optimized_plan
        assert result.optimized_plan_json["type"] == "Project"
    finally:
        service.close()


def test_schema_snapshot_hides_system_catalog(tmp_path: Path) -> None:
    service = DatabaseService(tmp_path)
    try:
        service.execute("CREATE TABLE student(id INT, name VARCHAR(20));")
        snapshot = service.schema_snapshot()
        assert [table.name for table in snapshot] == ["student"]
        assert [(column.name, column.type_text) for column in snapshot[0].columns] == [
            ("id", "INT"),
            ("name", "VARCHAR(20)"),
        ]
    finally:
        service.close()


def test_error_is_returned_without_crashing_service(tmp_path: Path) -> None:
    service = DatabaseService(tmp_path)
    try:
        batch = service.execute("SELECT * FROM missing;")
        assert batch.results == ()
        assert batch.error is not None
        assert batch.error.error_type == "SemanticError"
        assert batch.error.line == 1
        assert "does not exist" in batch.error.message
    finally:
        service.close()
