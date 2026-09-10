"""T019 tests for the compiler demonstration entry point.

Run: python -m unittest discover -s tests -p test_demo.py -v
Also compatible with: python -m pytest tests/test_demo.py -v

Two entry points are covered:

* ``render_compilation`` — B's backend trace (Semantic → Plan → optimized
  Plan) over tokens and AST supplied by the caller.
* ``compile_sql`` / ``main`` — the real ``--compile-only`` pipeline that
  starts from SQL text. Its Parser stage belongs to A (T014) and does not
  exist yet, so the tests drive that stage through an injected factory and
  separately pin what the pipeline reports while the dependency is missing.
"""

import io
import textwrap
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory

from database_system.sql_compiler.ast_nodes import (
    ColumnDef, CreateTableStmt, SelectStmt, TypeKind, TypeSpec,
)
from database_system.sql_compiler.catalog import Catalog
from database_system.sql_compiler.demo import compile_sql, main, render_compilation
from database_system.utils.errors import LexError, ParseError


def student_catalog():
    catalog = Catalog()
    catalog.create_table("student", [
        ColumnDef(line=1, column=1, name="name",
                  type_spec=TypeSpec(TypeKind.VARCHAR, 8)),
    ])
    return catalog


def select_name():
    return SelectStmt(line=1, column=1, columns=["name"], table="student",
                      where=None)


def create_student():
    return CreateTableStmt(line=1, column=1, table="student", columns=[
        ColumnDef(line=1, column=1, name="name",
                  type_spec=TypeSpec(TypeKind.VARCHAR, 8)),
    ])


class FakeParser:
    """Stands in for A's Parser: returns statements prepared by the test."""

    statements: list = []

    def __init__(self, tokens):
        self.tokens = tokens

    def parse(self):
        return list(type(self).statements)


def parser_returning(*statements):
    return type("PreparedParser", (FakeParser,), {"statements": list(statements)})


def parser_raising(error):
    class RaisingParser(FakeParser):
        def parse(self):
            raise error

    return RaisingParser


class RenderCompilationTests(unittest.TestCase):
    def test_demo_shows_all_backend_stages_for_valid_statement(self):
        output = render_compilation([], [select_name()], student_catalog())
        for label in ["Token 流:", "AST:", "语义检查结果: OK",
                      "原始 Logical Plan:", "优化后的 Logical Plan:"]:
            self.assertIn(label, output)

    def test_demo_reports_semantic_error_and_continues(self):
        stmt = SelectStmt(line=3, column=4, columns=["missing"],
                          table="student", where=None)
        output = render_compilation([], [stmt], Catalog())
        self.assertIn("语义检查失败:", output)
        self.assertIn("table 'student' does not exist", output)

    def test_a_failed_statement_does_not_stop_the_next_one(self):
        bad = SelectStmt(line=1, column=1, columns=["name"], table="missing",
                         where=None)
        output = render_compilation([], [bad, select_name()], student_catalog())
        self.assertIn("语义检查失败:", output)
        self.assertIn("语义检查结果: OK", output)

    def test_semantic_error_message_carries_its_position(self):
        stmt = SelectStmt(line=3, column=4, columns=["name"], table="missing",
                          where=None)
        output = render_compilation([], [stmt], student_catalog())
        self.assertIn("SemanticError at 3:4:", output)

    def test_implementation_bugs_are_not_disguised_as_semantic_errors(self):
        # A plain object has no .line/.column, so analysis fails with an
        # AttributeError. Swallowing it would report a compiler bug as if the
        # user's SQL were at fault, which is exactly what must not happen.
        with self.assertRaises(AttributeError):
            render_compilation([], [object()], student_catalog())


class CompileSqlPipelineTests(unittest.TestCase):
    """SQL text → Lexer → Parser → Semantic → Planner → Optimizer."""

    def test_pipeline_tokenizes_real_sql_text(self):
        output = compile_sql("SELECT name FROM student;", student_catalog(),
                             parser_factory=parser_returning(select_name()))
        self.assertIn("Token 流:", output)
        self.assertIn("KEYWORD: 'SELECT'", output)
        self.assertIn("IDENTIFIER: 'student'", output)

    def test_pipeline_reaches_the_optimized_plan(self):
        output = compile_sql("SELECT name FROM student;", student_catalog(),
                             parser_factory=parser_returning(select_name()))
        self.assertIn("语义检查结果: OK", output)
        self.assertIn("优化后的 Logical Plan:", output)

    def test_pipeline_registers_created_tables_so_later_statements_resolve(self):
        source = "CREATE TABLE student (name VARCHAR(8));\nSELECT name FROM student;"
        output = compile_sql(
            source, parser_factory=parser_returning(create_student(), select_name()))
        self.assertNotIn("语义检查失败:", output)
        self.assertEqual(output.count("语义检查结果: OK"), 2)

    def test_lex_errors_are_reported_as_structured_diagnostics(self):
        class FailingLexer:
            def __init__(self, source):
                self.source = source

            def tokenize(self):
                raise LexError("unexpected character '#'", line=1, column=8)

        output = compile_sql("SELECT # FROM student;", student_catalog(),
                             lexer_factory=FailingLexer)
        self.assertIn("词法分析失败: LexError at 1:8:", output)
        self.assertNotIn("语法分析", output)

    def test_parse_errors_are_reported_as_structured_diagnostics(self):
        error = ParseError("unexpected token 'AND', expected expression",
                           line=2, column=5)
        output = compile_sql("SELECT AND;", student_catalog(),
                             parser_factory=parser_raising(error))
        self.assertIn("语法分析失败: ParseError at 2:5:", output)
        self.assertNotIn("语义检查结果: OK", output)

    def test_implementation_bugs_in_the_frontend_are_not_swallowed(self):
        output_error = RuntimeError("parser exploded")
        with self.assertRaises(RuntimeError):
            compile_sql("SELECT name FROM student;", student_catalog(),
                        parser_factory=parser_raising(output_error))

    def test_missing_parser_is_reported_as_a_pending_dependency(self):
        # A's parser.py (T014) does not exist yet. The pipeline must say so
        # plainly instead of pretending the demo succeeded.
        def no_parser(tokens):
            raise ImportError("parser.py is not implemented yet")

        output = compile_sql("SELECT name FROM student;", student_catalog(),
                             parser_factory=no_parser)
        self.assertIn("语法分析阶段尚未接通", output)
        self.assertIn("T014", output)
        self.assertNotIn("语义检查结果: OK", output)

    def test_tokens_are_still_shown_when_the_parser_is_missing(self):
        def no_parser(tokens):
            raise ImportError("parser.py is not implemented yet")

        output = compile_sql("SELECT name FROM student;", student_catalog(),
                             parser_factory=no_parser)
        self.assertIn("KEYWORD: 'SELECT'", output)

    def test_default_parser_factory_does_not_crash_the_pipeline(self):
        # Whatever the current state of A's parser.py, resolving it must not
        # raise out of compile_sql.
        output = compile_sql("SELECT name FROM student;", student_catalog())
        self.assertIn("Token 流:", output)


class CompileOnlyCommandLineTests(unittest.TestCase):
    def run_main(self, argv):
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            code = main(argv)
        return code, buffer.getvalue()

    def test_compile_only_flag_runs_the_pipeline_over_inline_sql(self):
        code, output = self.run_main(
            ["--compile-only", "--sql", "SELECT name FROM student;"])
        self.assertEqual(code, 0)
        self.assertIn("Token 流:", output)

    def test_compile_only_flag_runs_the_pipeline_over_a_file(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / "demo.sql"
            path.write_text(
                textwrap.dedent("""\
                    CREATE TABLE student (name VARCHAR(8));
                    SELECT name FROM student;
                """),
                encoding="utf-8",
            )
            code, output = self.run_main(["--compile-only", str(path)])
        self.assertEqual(code, 0)
        self.assertIn("Token 流:", output)

    def test_missing_compile_only_flag_is_a_usage_error(self):
        code, _ = self.run_main(["--sql", "SELECT name FROM student;"])
        self.assertEqual(code, 2)

    def test_missing_input_is_a_usage_error(self):
        code, _ = self.run_main(["--compile-only"])
        self.assertEqual(code, 2)

    def test_unreadable_file_is_reported_without_a_traceback(self):
        code, output = self.run_main(["--compile-only", "no_such_file.sql"])
        self.assertEqual(code, 1)
        self.assertIn("no_such_file.sql", output)


if __name__ == "__main__":
    unittest.main()
