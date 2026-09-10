"""MiniDB 顶层编排：一句 SQL 进，结果文本出（T032）。

完整链路：

    SQL 文本
      → Lexer / Parser              (A) 词法、语法
      → SemanticAnalyzer            (B) 查表查列、回填类型
      → Planner / Optimizer         (B) 建逻辑计划、常量折叠
      → Executor                    (D) 真跑算子
      → StorageEngine               (D) 行 ↔ 页
      → BufferPool / FileManager    (C) 落盘

错误不在这里吞：五类 MiniSQLError 一路抛给调用方（CLI），由展示层决定
怎么打印——引擎不该管"怎么好看"。
"""

from __future__ import annotations

from database_system.engine.executor import Executor, Result
from database_system.engine.storage_engine import StorageEngine
from database_system.sql_compiler.catalog import Catalog
from database_system.sql_compiler.lexer import Lexer
from database_system.sql_compiler.optimizer import Optimizer
from database_system.sql_compiler.parser import Parser
from database_system.sql_compiler.planner import Planner
from database_system.sql_compiler.semantic import SemanticAnalyzer


def _format(result: Result) -> str:
    """非查询语句自带文案；查询结果是行列表，一行印一行。"""
    if isinstance(result, str):
        return result
    return "\n".join(str(row) for row in result)


class MiniDB:
    def __init__(self, data_dir: str = "data/"):
        self.data_dir = data_dir
        # 常驻 Catalog：REPL 里 CREATE TABLE 建的表，后续语句要能看见
        self.catalog = Catalog()
        self.engine = StorageEngine(data_dir)
        self.executor = Executor(self.engine, self.catalog)
        self._planner = Planner()
        self._optimizer = Optimizer()

    def execute(self, sql: str) -> str:
        """一次可以带多条语句，按源码顺序执行，结果逐条拼起来。"""
        statements = Parser(Lexer(sql).tokenize()).parse()
        return "\n".join(self._run_one(stmt) for stmt in statements)

    def _run_one(self, stmt) -> str:
        checked = SemanticAnalyzer(self.catalog).analyze(stmt)
        plan = self._optimizer.optimize(self._planner.build(checked))
        return _format(self.executor.execute(plan))

    def close(self) -> None:
        """退出前把脏页落盘并关闭表文件。"""
        self.engine.close()
