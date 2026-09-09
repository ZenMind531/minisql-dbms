"""T026 持久化验证辅助脚本：在独立进程中写入数据后退出。

用法：python _persist_helper.py <data文件路径>
模拟“数据库进程 1”：写页 → 落盘 → 正常退出。
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database_system.storage.file_manager import FileManager
from database_system.storage.page import Page


def main():
    path = sys.argv[1]
    fm = FileManager(path)
    for pid in (fm.allocate_page(), fm.allocate_page()):
        page = Page(page_id=pid)
        page.insert_row(b"row-" + str(pid).encode())
        fm.write_page(pid, page)
    fm.close()
    print("written")


if __name__ == "__main__":
    main()
