from __future__ import annotations

from pathlib import Path
from time import perf_counter

from database_system.engine.minidb import MiniDB
from database_system.gui.models import (
    ColumnInfo, ErrorInfo, ExecutionBatch, ExecutionResult, TableInfo,
)
from database_system.sql_compiler.ast_nodes import SelectStmt, ShowDatabasesStmt, ShowTablesStmt
from database_system.sql_compiler.lexer import Lexer
from database_system.sql_compiler.parser import Parser
from database_system.sql_compiler.planner import plan_to_json, plan_to_tree
from database_system.sql_compiler.semantic import SemanticAnalyzer
from database_system.utils.errors import MiniSQLError


class DatabaseService:
    """Structured adapter around MiniDB for GUI consumers."""

    def __init__(self, data_dir: str | Path = "data/") -> None:
        self.data_dir = Path(data_dir)
        self.db = MiniDB(str(self.data_dir))

    def execute(self, sql: str) -> ExecutionBatch:
        completed: list[ExecutionResult] = []
        try:
            statements = Parser(Lexer(sql).tokenize()).parse()
            for statement in statements:
                started = perf_counter()
                checked = SemanticAnalyzer(self.db.catalog).analyze(statement)
                original = self.db._planner.build(checked)
                optimized = self.db._optimizer.optimize(original)
                raw = self.db.executor.execute(optimized)
                columns = self._columns(statement)
                rows = tuple(raw) if isinstance(raw, list) else ()
                completed.append(ExecutionResult(
                    statement_type=type(statement).__name__,
                    columns=columns,
                    rows=rows,
                    message=raw if isinstance(raw, str) else f"{len(rows)} row(s)",
                    original_plan=plan_to_tree(original),
                    optimized_plan=plan_to_tree(optimized),
                    original_plan_json=plan_to_json(original),
                    optimized_plan_json=plan_to_json(optimized),
                    elapsed_ms=(perf_counter() - started) * 1000,
                ))
        except MiniSQLError as exc:
            return ExecutionBatch(
                results=tuple(completed),
                error=ErrorInfo(exc.type, exc.message, exc.line, exc.column),
            )
        except Exception as exc:
            return ExecutionBatch(
                results=tuple(completed),
                error=ErrorInfo(type(exc).__name__, str(exc)),
            )
        return ExecutionBatch(tuple(completed))

    def schema_snapshot(self) -> tuple[TableInfo, ...]:
        tables: list[TableInfo] = []
        for name in self.db.catalog.table_names(include_system=False):
            schema = self.db.catalog.find_table(name)
            if schema is None:
                continue
            columns = tuple(
                ColumnInfo(column.name, self._type_text(column.type_spec))
                for column in schema.columns
            )
            tables.append(TableInfo(name, columns))
        return tuple(tables)

    def close(self) -> None:
        self.db.close()

    def _columns(self, statement) -> tuple[str, ...]:
        if isinstance(statement, ShowDatabasesStmt):
            return ("database",)
        if isinstance(statement, ShowTablesStmt):
            return ("table",)
        if not isinstance(statement, SelectStmt):
            return ()
        if statement.columns is not None:
            return tuple(statement.columns)
        schema = self.db.catalog.find_table(statement.table)
        return tuple(column.name for column in schema.columns) if schema else ()

    @staticmethod
    def _type_text(type_spec) -> str:
        name = type_spec.kind.value
        return f"{name}({type_spec.length})" if type_spec.length is not None else name

