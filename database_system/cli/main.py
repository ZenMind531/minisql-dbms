"""MiniDB 命令行入口：读一行 SQL，交给引擎，打印结果。

CLI 只管展示层：把结构化异常翻译成人话，退出前把脏页落盘。
"""

import sys

from database_system.cli.banner import show_banner, show_farewell
from database_system.engine.minidb import MiniDB
from database_system.utils.errors import MiniSQLError


def main():
    # 只在真终端里播启动动画；管道 / 重定向时保持输出干净
    if sys.stdout.isatty():
        show_banner()
    db = MiniDB()
    try:
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
    finally:
        db.close()  # 先落盘
        if sys.stdout.isatty():
            show_farewell()  # 屏幕上要说"已落盘"，就得真落盘了再说


if __name__ == "__main__":
    main()
