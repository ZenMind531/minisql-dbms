"""开场与收场：MiniDB 大字进场，告别语退场。

只在交互式终端播放——管道或重定向时由调用方跳过（见 main.py），
免得把控制字符混进脚本输出里。

两处动画都只往下打新内容，绝不用光标上移去"擦"已经打印的东西：
终端一旦滚动过，光标位置就对不上了，擦除会误伤别的行。
"""

from __future__ import annotations

import time

# 逐行一个颜色：红 → 黄 → 绿 → 青 → 蓝
_COLORS = (31, 33, 32, 36, 34)
_RESET = "\033[0m"

_LOGO = (
    r" __  __ _       _ ____  ____ ",
    r"|  \/  (_)_ __ (_)  _ \| __ )",
    r"| |\/| | | '_ \| | | | |  _ \ ",
    r"| |  | | | | | | | |_| | |_) |",
    r"|_|  |_|_|_| |_|_|____/|____/ ",
)

_TAGLINE = "MiniDB v0.1  ·  语句以 ; 结尾，exit; 退出"


def show_banner(delay: float = 0.07) -> None:
    """把大字一行行点亮，再打一行用法提示。"""
    for color, line in zip(_COLORS, _LOGO):
        print(f"\033[{color}m{line}{_RESET}")
        time.sleep(delay)
    print()
    print(_TAGLINE)
    print()


def show_farewell(message: str = "数据已落盘，再见。",
                  delay: float = 0.05) -> None:
    """退出前逐字打一句告别，用一个绿色的块收尾。

    调用方应保证此时脏页已经 flush——屏幕上说"已落盘"，就得真的落盘。
    """
    print()
    print("\033[32m", end="")
    for character in message:
        print(character, end="", flush=True)
        time.sleep(delay)
    print(f"{_RESET}\n")
