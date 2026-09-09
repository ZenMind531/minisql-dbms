"""Compiler demonstration entry point (T019, ``--compile-only`` mode).

Full pipeline::

    SQL 文本 → Lexer(A) → Parser(A) → SemanticAnalyzer(B) → Planner(B) → Optimizer(B)

Two entry points, deliberately separated:

``compile_sql(source, ...)``
    Runs the whole pipeline starting from SQL text. This is what
    ``--compile-only`` uses.

``render_compilation(tokens, statements, catalog)``
    Runs only B's backend stages over tokens and AST the caller already has.
    Useful when the frontend is driven separately, and it is the part that
    works today.

**Current dependency (A, T014).** ``parser.py`` does not exist yet. The
pipeline resolves it lazily, and when it is missing it says so and stops after
the Token stage rather than reporting a fake success. Nothing else needs to
change once A lands the Parser.

**Error handling.** Only the structured diagnostics from ``utils.errors``
(``LexError``/``ParseError``/``SemanticError``) are caught and reported with
their position; a failing statement does not stop the ones after it. Every
other exception — ``TypeError``, ``AttributeError``, the Lexer's remaining
``NotImplementedError`` paths — propagates on purpose, because disguising a
compiler bug as a user's SQL error is what makes a live debugging session
impossible.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Callable, Iterable, Sequence

from database_system.sql_compiler.ast_nodes import CreateTableStmt
from database_system.sql_compiler.catalog import Catalog
from database_system.sql_compiler.lexer import Lexer
from database_system.sql_compiler.optimizer import Optimizer
from database_system.sql_compiler.planner import Planner, plan_to_tree
from database_system.sql_compiler.semantic import SemanticAnalyzer
from database_system.utils.errors import LexError, ParseError, SemanticError

USAGE = (
    "用法: python -m database_system.sql_compiler.demo --compile-only "
    "[SQL 文件 | --sql \"SELECT ...;\"]"
)

PARSER_PENDING = (
    "语法分析阶段尚未接通: database_system/sql_compiler/parser.py 尚未实现"
    "（T014，负责人 A）。以上 Token 流由 Lexer 产出；AST、语义检查和 Logical Plan "
    "需要 Parser 就位后才能演示。"
)


def _default_parser_factory(tokens):
    """Resolve A's Parser lazily so this module imports without it."""
    from database_system.sql_compiler.parser import Parser  # noqa: PLC0415

    return Parser(tokens)


def _format_token(token: object) -> str:
    token_type = getattr(token, "type", "")
    name = getattr(token_type, "value", token_type)
    return (f"{name}: {getattr(token, 'lexeme', '')!r} "
            f"@ {getattr(token, 'line', '?')}:{getattr(token, 'column', '?')}")


def _token_section(tokens: Iterable[object]) -> list[str]:
    return ["Token 流:", *[_format_token(token) for token in tokens]]


def render_compilation(tokens: Iterable[object], statements: Iterable[object],
                       catalog: Catalog,
                       register_created_tables: bool = False) -> str:
    """Render Token, AST, semantic result, and before/after plans.

    Semantic failures are reported and do not abort later statements, so one
    demo script can show both successful and erroneous SQL. Any other
    exception propagates; see the module docstring.

    ``register_created_tables`` lets a self-contained demo script keep
    ``CREATE TABLE`` and a later ``SELECT`` in the same file: the created
    schema is registered in the demo's own Catalog. This is a demo
    convenience, not execution — no rows are touched and no disk I/O happens.
    Table persistence belongs to D's CatalogManager.
    """
    lines = _token_section(tokens)
    planner, optimizer = Planner(), Optimizer()

    for index, stmt in enumerate(statements, 1):
        lines.extend([f"\n语句 {index} AST:", repr(stmt)])
        try:
            checked = SemanticAnalyzer(catalog).analyze(stmt)
        except SemanticError as error:
            lines.append(f"语义检查失败: {error}")
            continue

        lines.append("语义检查结果: OK")
        if register_created_tables and isinstance(checked, CreateTableStmt):
            catalog.create_table(checked.table, checked.columns)

        plan = planner.build(checked)
        lines.extend(["原始 Logical Plan:", plan_to_tree(plan)])
        lines.extend(["优化后的 Logical Plan:", plan_to_tree(optimizer.optimize(plan))])

    return "\n".join(lines)


def compile_sql(source: str, catalog: Catalog | None = None, *,
                lexer_factory: Callable[[str], object] | None = None,
                parser_factory: Callable[[Sequence[object]], object] | None = None,
                ) -> str:
    """Compile SQL text and return the full demonstration trace.

    ``catalog`` defaults to an empty Catalog that ``CREATE TABLE`` statements
    in ``source`` populate as the demo proceeds.

    The two factories exist so this pipeline is testable while A's Parser is
    still missing; production callers leave them unset and get the real
    Lexer and Parser.
    """
    catalog = Catalog() if catalog is None else catalog
    build_lexer = Lexer if lexer_factory is None else lexer_factory
    build_parser = _default_parser_factory if parser_factory is None else parser_factory

    try:
        tokens = build_lexer(source).tokenize()
    except LexError as error:
        return f"词法分析失败: {error}"

    try:
        parser = build_parser(tokens)
    except ImportError:
        # A's parser.py is not available yet (T014). Only resolving the
        # Parser is guarded here, so an ImportError raised by parse() itself
        # is not mistaken for a missing module.
        return "\n".join([*_token_section(tokens), "", PARSER_PENDING])

    try:
        statements = parser.parse()
    except ParseError as error:
        return "\n".join([*_token_section(tokens), f"语法分析失败: {error}"])

    return render_compilation(tokens, statements, catalog,
                              register_created_tables=True)


def _read_source(arguments: list[str]) -> tuple[str | None, str | None, int]:
    """Return ``(source, message, exit_code)`` for the parsed arguments."""
    if "--sql" in arguments:
        index = arguments.index("--sql")
        if index + 1 >= len(arguments):
            return None, USAGE, 2
        return arguments[index + 1], None, 0

    positional = [item for item in arguments if not item.startswith("-")]
    if len(positional) != 1:
        return None, USAGE, 2
    try:
        return Path(positional[0]).read_text(encoding="utf-8"), None, 0
    except OSError as error:
        return None, f"无法读取 SQL 文件 {positional[0]}: {error.strerror}", 1


def main(argv: Sequence[str] | None = None) -> int:
    """``--compile-only`` command line entry point."""
    arguments = list(sys.argv[1:] if argv is None else argv)

    if "--compile-only" not in arguments:
        print(USAGE)
        return 2
    arguments.remove("--compile-only")

    source, message, code = _read_source(arguments)
    if source is None:
        print(message)
        return code

    print(compile_sql(source))
    return 0


__all__ = ["compile_sql", "main", "render_compilation"]


if __name__ == "__main__":
    raise SystemExit(main())
