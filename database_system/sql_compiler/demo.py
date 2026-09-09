"""Formatting helpers for the compiler demonstration pipeline.

The frontend (Lexer/Parser) supplies tokens and AST statements; this module
performs the backend stages and returns a teacher-friendly textual trace.
"""
from __future__ import annotations

from typing import Iterable

from database_system.sql_compiler.semantic import SemanticAnalyzer
from database_system.sql_compiler.planner import Planner, plan_to_tree
from database_system.sql_compiler.optimizer import Optimizer


def render_compilation(tokens: Iterable[object], statements: Iterable[object], catalog) -> str:
    """Render Token, AST, semantic result, and before/after plans.

    Semantic failures are reported and do not abort later statements, allowing
    a demo script to show both successful and erroneous SQL in one run.
    """
    token_lines = [f"{getattr(t, 'type', '')}: {getattr(t, 'lexeme', '')!r} @ {getattr(t, 'line', '?')}:{getattr(t, 'column', '?')}" for t in tokens]
    lines = ["Token 流:", *token_lines]
    planner, optimizer = Planner(), Optimizer()
    for index, stmt in enumerate(statements, 1):
        lines.extend([f"\n语句 {index} AST:", repr(stmt)])
        analyzer = SemanticAnalyzer(catalog)
        try:
            checked = analyzer.analyze(stmt)
        except Exception as error:
            lines.append(f"语义检查失败: {error}")
            continue
        lines.append("语义检查结果: OK")
        plan = planner.build(checked)
        lines.extend(["原始 Logical Plan:", plan_to_tree(plan)])
        optimized = optimizer.optimize(plan)
        lines.extend(["优化后的 Logical Plan:", plan_to_tree(optimized)])
    return "\n".join(lines)


__all__ = ["render_compilation"]
