from pathlib import Path

import pytest

from database_system.engine.minidb import MiniDB
from database_system.sql_compiler.ast_nodes import (
    OrderByItem, SelectStmt, ShowDatabasesStmt, ShowTablesStmt,
)
from database_system.sql_compiler.lexer import Lexer, TokenType
from database_system.sql_compiler.parser import Parser
from database_system.utils.errors import SemanticError


def parse_one(sql):
    return Parser(Lexer(sql).tokenize()).parse()[0]


def test_new_words_are_case_insensitive_keywords():
    tokens = Lexer("show databases tables order by asc desc").tokenize()
    assert [token.type for token in tokens[:-1]] == [TokenType.KEYWORD] * 7


def test_parser_supports_show_statements():
    databases = parse_one("SHOW DATABASES;")
    tables = parse_one("show tables;")
    assert isinstance(databases, ShowDatabasesStmt)
    assert isinstance(tables, ShowTablesStmt)
    assert (databases.line, databases.column) == (1, 1)


def test_parser_supports_multiple_order_items_and_directions():
    stmt = parse_one(
        "SELECT name FROM student ORDER BY age DESC, name ASC, id;"
    )
    assert isinstance(stmt, SelectStmt)
    assert stmt.order_by == [
        OrderByItem(line=1, column=35, column_name="age", descending=True),
        OrderByItem(line=1, column=45, column_name="name", descending=False),
        OrderByItem(line=1, column=55, column_name="id", descending=False),
    ]


def test_order_by_rejects_missing_column(tmp_path: Path):
    db = MiniDB(str(tmp_path))
    try:
        db.execute("CREATE TABLE student(id INT, name VARCHAR(8));")
        with pytest.raises(SemanticError):
            db.execute("SELECT name FROM student ORDER BY age;")
    finally:
        db.close()


def test_order_by_executes_before_projection_and_supports_mixed_directions(
    tmp_path: Path,
):
    db = MiniDB(str(tmp_path))
    try:
        output = db.execute(
            "CREATE TABLE student(id INT, name VARCHAR(8), age INT);"
            "INSERT INTO student VALUES (1, 'Bob', 20);"
            "INSERT INTO student VALUES (2, 'Alice', 20);"
            "INSERT INTO student VALUES (3, 'Tom', 22);"
            "SELECT name FROM student ORDER BY age DESC, name ASC;"
        )
        assert output.splitlines()[-3:] == [
            "('Tom',)", "('Alice',)", "('Bob',)",
        ]
    finally:
        db.close()


def test_show_returns_current_database_and_sorted_user_tables(tmp_path: Path):
    data_dir = tmp_path / "school"
    db = MiniDB(str(data_dir))
    try:
        assert db.execute("SHOW DATABASES;") == "('school',)"
        db.execute("CREATE TABLE zebra(id INT); CREATE TABLE alpha(id INT);")
        assert db.execute("SHOW TABLES;").splitlines() == [
            "('alpha',)", "('zebra',)",
        ]
    finally:
        db.close()
