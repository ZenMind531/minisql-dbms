"""T028 端到端测试：演示脚本输出比对 + 重启持久化（US3 验收）。

前两条测试像验收现场一样，真的开一个子进程跑 CLI——等价于
``bash start.sh --file tests/sql/demo_e2e.sql --data ./tmp/minidb``，
这是全项目唯一覆盖 ``cli/main.py`` 与 ``MiniDB.close()`` 落盘时机的测试。
第三条用 MiniDB 直接驱动，因为 120 行数据是现场生成的，塞进命令行不现实。
"""

import subprocess
import sys
from pathlib import Path

from database_system.engine.minidb import MiniDB
from database_system.utils.constants import PAGE_SIZE

REPO_ROOT = Path(__file__).resolve().parent.parent
DEMO_SQL = REPO_ROOT / "tests" / "sql" / "demo_e2e.sql"

# 与 quickstart.md「基础脚本预期输出」一节逐字一致：改这里必须同步改那里
DEMO_OUTPUT = [
    "OK",
    "1 row(s) inserted",
    "1 row(s) inserted",
    "1 row(s) inserted",
    "(1, 'Alice')",
    "1 row(s) deleted",
    "(2, 'Bob', 17)",
    "(3, 'Tom', 22)",
]


def _run_cli(data_dir: Path, sql_file: Path) -> subprocess.CompletedProcess:
    """真开一个进程跑 CLI，模拟验收现场敲的那条命令。"""
    return subprocess.run(
        [
            sys.executable, "-m", "database_system.cli.main",
            "--file", str(sql_file),
            "--data", str(data_dir),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def test_demo_script_prints_expected_output(tmp_path: Path) -> None:
    """demo_e2e.sql 经真实 CLI 跑出来的输出，逐行比对 quickstart 的预期。"""
    result = _run_cli(tmp_path, DEMO_SQL)

    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == DEMO_OUTPUT


def test_demo_data_survives_a_restart(tmp_path: Path) -> None:
    """关掉进程再开一个新的，数据必须还在——SC-006 里最容易翻车的一步。

    这里刻意不复用同一个 MiniDB 实例：新进程要自己从 __catalog__.dat
    重建 Catalog，再顺着它找到 student.dat，全程不靠任何内存残留。
    """
    assert _run_cli(tmp_path, DEMO_SQL).returncode == 0

    restart_sql = tmp_path / "restart.sql"
    restart_sql.write_text("SELECT * FROM student;\n", encoding="utf-8")
    result = _run_cli(tmp_path, restart_sql)

    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == ["(2, 'Bob', 17)", "(3, 'Tom', 22)"]


def test_hundred_rows_survive_query_delete_and_restart(tmp_path: Path) -> None:
    """SC-006：建表 → 插入 ≥100 行 → 条件查询 → 删除 → 重启再查，一次通过。

    120 行不是随手挑的规模：一条记录 4 + 32 + 4 = 40 字节，加 4 字节槽位是
    44 字节，而一页只有 4064 字节可用空间，装得下 92 行——所以这张表必然
    跨页，正好把「多页写入 + 跨页删除 + 重启恢复」这条最易出错的路径走全。
    """
    total = 120
    script = ["CREATE TABLE big(id INT, name VARCHAR(32), age INT);"]
    script += [
        f"INSERT INTO big(id,name,age) VALUES ({i},'user{i}',{i});"
        for i in range(1, total + 1)
    ]

    db = MiniDB(str(tmp_path))
    try:
        assert db.execute("\n".join(script)).splitlines() == (
            ["OK"] + ["1 row(s) inserted"] * total
        )
        # 自证跨页：一页放不下 120 行，数据文件必须已经长到两页以上
        assert (tmp_path / "big.dat").stat().st_size >= 2 * PAGE_SIZE

        selected = db.execute("SELECT * FROM big WHERE age > 100;").splitlines()
        assert len(selected) == 20
        assert selected[0] == "(101, 'user101', 101)"
        assert selected[-1] == "(120, 'user120', 120)"

        assert db.execute("DELETE FROM big WHERE age <= 20;") == "20 row(s) deleted"
        assert len(db.execute("SELECT * FROM big;").splitlines()) == 100
    finally:
        db.close()

    reopened = MiniDB(str(tmp_path))
    try:
        rows = reopened.execute("SELECT * FROM big;").splitlines()
        assert len(rows) == 100
        assert rows[0] == "(21, 'user21', 21)"
        assert rows[-1] == "(120, 'user120', 120)"
    finally:
        reopened.close()
