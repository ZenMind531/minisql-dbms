"""MiniDB 命令行入口：读一行，回一行。"""


def main():
    while True:
        text = input("MiniDB> ")
        # 退出统一走 exit; —— 和 SQL 一样必须带分号（关键词大小写不敏感）
        if text.strip().lower() == "exit;":
            break
        print("收到:", text)


if __name__ == "__main__":
    main()
