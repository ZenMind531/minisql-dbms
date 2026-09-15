import pytest

from database_system.gui.sql_builder import (
    build_browse_table,
    build_create_table,
    build_delete_row,
    build_drop_table,
    build_insert,
    literal_sql,
)


def test_build_create_and_browse_sql() -> None:
    assert build_create_table("student", [("id", "INT"), ("name", "VARCHAR(20)")]) == (
        "CREATE TABLE student(id INT, name VARCHAR(20));"
    )
    assert build_browse_table("student") == "SELECT * FROM student LIMIT 200;"


def test_build_insert_and_delete_escape_strings() -> None:
    assert build_insert("student", ["id", "name"], [1, "O'Brien"]) == (
        "INSERT INTO student(id, name) VALUES (1, 'O''Brien');"
    )
    assert build_delete_row("student", ["id", "name"], [1, "O'Brien"]) == (
        "DELETE FROM student WHERE id = 1 AND name = 'O''Brien';"
    )
    assert literal_sql(True) == "TRUE"


def test_drop_rejects_invalid_identifier() -> None:
    with pytest.raises(ValueError, match="identifier"):
        build_drop_table("student; DROP TABLE course")
