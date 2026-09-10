"""MiniDB 命令行入口：读一行 SQL，交给引擎，打印结果。

CLI 只管展示层：把结构化异常翻译成人话，退出前把脏页落盘。
"""

import argparse
import sys
from pathlib import Path
from typing import Sequence

from database_system.cli.banner import show_banner, show_farewell
from database_system.engine.minidb import MiniDB
from database_system.sql_compiler.demo import compile_sql
from database_system.utils.errors import MiniSQLError


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


def _run_repl(db: MiniDB) -> None:
    # 只在真终端里播启动动画；管道 / 重定向时保持输出干净
    if sys.stdout.isatty():
        show_banner()
    while True:
        try:
            text = input("MiniDB> ")
        except (EOFError, KeyboardInterrupt):
            print()  # Ctrl+D / Ctrl+C：换行，别把提示符和 shell 黏在一起
            break
        # 退出统一走 exit; —— 和 SQL 一样必须带分号（关键词大小写不敏感）
        if text.strip().lower() == "exit;":
            break
        # 空行不是语句，直接忽略（grammar.md：空输入解析为空语句列表）
        if not text.strip():
            continue
        try:
            print(db.execute(text))
        except MiniSQLError as error:
            print(error)  # 类型 + 行列号 + 原因；只废这一条，REPL 继续


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
