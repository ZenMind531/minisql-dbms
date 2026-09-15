"""MiniDB 命令行入口：读一行 SQL，交给引擎，打印结果。

CLI 只管展示层：把结构化异常翻译成人话，退出前把脏页落盘。
"""

import argparse
import sys
from pathlib import Path
from typing import Sequence

try:
    import readline  # noqa: F401  Linux/macOS 标准库自带；Windows 上没有
except ImportError:  # pragma: no cover - 平台差异
    readline = None

from database_system.cli.banner import show_banner, show_farewell
from database_system.engine.minidb import MiniDB
from database_system.sql_compiler.demo import compile_sql
from database_system.utils.errors import MiniSQLError

# 上下键翻出来的历史存这里，对标 MySQL 的 ~/.mysql_history
HISTORY_FILE = Path.home() / ".minidb_history"
HISTORY_LIMIT = 1000


def _argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="minidb",
        description="MiniSQL 教学数据库：交互执行、SQL 文件执行或编译器演示",
    )
    parser.add_argument(
        "compile_file",
        nargs="?",
        metavar="SQL_FILE",
        help="与 --compile-only 搭配使用的 SQL 文件",
    )
    parser.add_argument("--file", metavar="SQL_FILE", help="执行 SQL 文件后退出")
    parser.add_argument(
        "--data",
        default="data/",
        metavar="DIRECTORY",
        help="数据库文件目录（默认：data/）",
    )
    parser.add_argument(
        "--compile-only",
        action="store_true",
        help="仅显示 Token、AST 和 Logical Plan，不执行 SQL",
    )
    return parser


def _read_sql_file(path: str) -> str:
    try:
        return Path(path).read_text(encoding="utf-8")
    except OSError as error:
        reason = error.strerror or str(error)
        raise ValueError(f"无法读取 SQL 文件 {path}: {reason}") from error


def _load_history() -> None:
    """读回上次会话敲过的语句；第一次运行没有文件，安静跳过。

    历史是锦上添花，读写失败一律咽掉——绝不能因为它让 REPL 起不来。
    """
    if readline is None:
        return
    try:
        readline.read_history_file(HISTORY_FILE)
    except OSError:
        pass


def _save_history() -> None:
    """存下本次会话的语句，只留最近 HISTORY_LIMIT 条，免得文件无限长大。"""
    if readline is None:
        return
    readline.set_history_length(HISTORY_LIMIT)
    try:
        readline.write_history_file(HISTORY_FILE)
    except OSError:
        pass


def _is_complete(source: str) -> bool:
    """攒下的内容是否已经是一条完整语句（回到最外层的分号收尾）。

    只看最外层：字符串字面量和注释里的分号不算数——否则
    ``INSERT INTO t VALUES ('a;b')`` 会在字符串中间就被切走送进解析器。

    扫描遇到未闭合的字符串或块注释会一路走到末尾、不更新"最后有效字符"，
    于是判为没写完，继续读下一行——正是想要的。
    """
    last = ""
    index = 0
    size = len(source)
    while index < size:
        if source.startswith("--", index):  # 行注释：跳到行尾
            end = source.find("\n", index)
            index = size if end < 0 else end + 1
            continue
        if source.startswith("/*", index):  # 块注释：跳到 */
            end = source.find("*/", index + 2)
            index = size if end < 0 else end + 2
            continue
        if source[index] == "'":  # 字符串：跳到收尾引号
            index += 1
            while index < size:
                if source[index] == "'":
                    # '' 是转义出来的引号，还在串里，不能当收尾
                    if index + 1 < size and source[index + 1] == "'":
                        index += 2
                        continue
                    index += 1
                    break
                index += 1
            continue
        if not source[index].isspace():
            last = source[index]
        index += 1
    return last == ";"


def _run_repl(db: MiniDB) -> None:
    # 历史只在真终端下读写：管道喂进来的输入不该混进历史，
    # 而且非 tty 时 readline 本来也不接管输入。
    interactive = sys.stdin.isatty()
    if interactive:
        _load_history()
    # 只在真终端里播启动动画；管道 / 重定向时保持输出干净
    if sys.stdout.isatty():
        show_banner()
    try:
        # 攒着还没写完的语句。SQL 允许跨行书写，必须写到分号才送去解析，
        # 否则 CREATE TABLE t ( 一敲回车就被当成完整语句，报 EOF。
        pending: list[str] = []
        while True:
            try:
                # 还在等这条语句写完时换续行提示符，让人知道没被误解
                text = input("    -> " if pending else "MiniDB> ")
            except (EOFError, KeyboardInterrupt):
                print()  # Ctrl+D / Ctrl+C：换行，别把提示符和 shell 黏在一起
                break
            # 空行不是语句，直接忽略（grammar.md：空输入解析为空语句列表）；
            # 但多行语句中间的空行要留住，它是语句的一部分
            if not pending and not text.strip():
                continue
            pending.append(text)
            source = "\n".join(pending)
            if not _is_complete(source):
                continue  # 还没写到分号，接着读
            pending.clear()
            # 退出统一走 exit; —— 和 SQL 一样必须带分号（关键词大小写不敏感）
            if source.strip().lower() == "exit;":
                break
            try:
                print(db.execute(source))
            except MiniSQLError as error:
                print(error)  # 类型 + 行列号 + 原因；只废这一条，REPL 继续
    finally:
        # 放在 finally 里：Ctrl+C 打断一条长查询时也得把这次敲的存下来
        if interactive:
            _save_history()


def main(argv: Sequence[str] | None = None) -> int:
    parser = _argument_parser()
    try:
        arguments = parser.parse_args(argv)
    except SystemExit as error:
        return int(error.code)

    if arguments.compile_file and not arguments.compile_only:
        parser.print_usage(sys.stderr)
        print("minidb: SQL_FILE 只能与 --compile-only 搭配使用", file=sys.stderr)
        return 2
    if arguments.compile_only and arguments.file:
        parser.print_usage(sys.stderr)
        print("minidb: --compile-only 不能与 --file 同时使用", file=sys.stderr)
        return 2

    source_path = arguments.compile_file if arguments.compile_only else arguments.file
    if arguments.compile_only and source_path is None:
        parser.print_usage(sys.stderr)
        print("minidb: --compile-only 需要 SQL_FILE", file=sys.stderr)
        return 2

    if source_path is not None:
        try:
            source = _read_sql_file(source_path)
        except ValueError as error:
            print(error, file=sys.stderr)
            return 1
        if arguments.compile_only:
            print(compile_sql(source))
            return 0

        db = MiniDB(arguments.data)
        try:
            print(db.execute(source))
            return 0
        except MiniSQLError as error:
            print(error, file=sys.stderr)
            return 1
        finally:
            db.close()

    db = MiniDB(arguments.data)
    try:
        _run_repl(db)
        return 0
    finally:
        db.close()  # 先落盘
        if sys.stdout.isatty():
            show_farewell()  # 屏幕上要说"已落盘"，就得真落盘了再说


if __name__ == "__main__":
    raise SystemExit(main())
