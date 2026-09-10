"""T026：持久化验证 —— 进程1写入 → 退出 → 进程2(重启)读回一致。"""

import subprocess
import sys
from pathlib import Path

from database_system.storage.file_manager import FileManager

ROOT = Path(__file__).resolve().parent.parent
HELPER = Path(__file__).resolve().parent / "_persist_helper.py"


def test_restart_persistence(tmp_path):
    path = str(tmp_path / "student.dat")

    # 进程 1：写入数据后退出（真正杀进程，验证落盘）
    r = subprocess.run(
        [sys.executable, str(HELPER), path],
        capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stderr

    # 进程 2：相当于重启数据库，从磁盘重新打开，数据必须在
    fm = FileManager(path)
    assert fm.page_count() == 3                 # 页0文件头 + 页1、页2
    assert list(fm.read_page(1).rows()) == [(0, b"row-1")]
    assert list(fm.read_page(2).rows()) == [(0, b"row-2")]
