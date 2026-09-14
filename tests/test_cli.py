"""CLI 参数与批处理模式测试。"""

from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from database_system.cli import main as cli_main
from database_system.cli.main import main


class CliTests(unittest.TestCase):
    def run_cli(self, arguments: list[str]) -> tuple[int, str, str]:
        stdout = StringIO()
        stderr = StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = main(arguments)
        return code, stdout.getvalue(), stderr.getvalue()

    def test_help_lists_the_three_supported_modes(self):
        code, output, error = self.run_cli(["--help"])

        self.assertEqual(code, 0)
        self.assertIn("--file", output)
        self.assertIn("--data", output)
        self.assertIn("--compile-only", output)
        self.assertEqual(error, "")

    def test_file_executes_sql_using_the_selected_data_directory(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            script = root / "demo.sql"
            data = root / "db"
            script.write_text(
                "CREATE TABLE student(id INT, name VARCHAR(8));\n"
                "INSERT INTO student VALUES (1, 'Alice');\n"
                "SELECT * FROM student;\n",
                encoding="utf-8",
            )

            code, output, error = self.run_cli(
                ["--file", str(script), "--data", str(data)]
            )

            self.assertEqual(code, 0)
            self.assertIn("OK", output)
            self.assertIn("1 row(s) inserted", output)
            self.assertIn("(1, 'Alice')", output)
            self.assertTrue((data / "student.dat").is_file())
            self.assertEqual(error, "")

    def test_compile_only_reads_a_file_without_creating_the_data_directory(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            script = root / "compile.sql"
            data = root / "unused"
            script.write_text("CREATE TABLE t(id INT);", encoding="utf-8")

            code, output, error = self.run_cli(
                ["--compile-only", str(script), "--data", str(data)]
            )

            self.assertEqual(code, 0)
            self.assertIn("Token", output)
            self.assertIn("CreateTable", output)
            self.assertFalse(data.exists())
            self.assertEqual(error, "")

    def test_missing_file_is_a_clean_cli_error(self):
        code, output, error = self.run_cli(["--file", "missing.sql"])

        self.assertEqual(code, 1)
        self.assertEqual(output, "")
        self.assertIn("无法读取 SQL 文件", error)
        self.assertNotIn("Traceback", error)


class HistoryTests(unittest.TestCase):
    """REPL 的上下键历史（readline）。

    历史文件是锦上添花：读不到、写不进去都必须安静跳过，
    绝不能因为它让 REPL 起不来——CLI 是唯一的用户界面。
    """

    def setUp(self):
        if cli_main.readline is None:
            self.skipTest("当前平台没有 readline（Windows）")
        self.saved_history_file = cli_main.HISTORY_FILE

    def tearDown(self):
        cli_main.HISTORY_FILE = self.saved_history_file
        cli_main.readline.clear_history()

    def test_history_is_written_and_read_back(self):
        with TemporaryDirectory() as directory:
            cli_main.HISTORY_FILE = Path(directory) / ".minidb_history"
            cli_main.readline.clear_history()
            cli_main.readline.add_history("SELECT 1;")

            cli_main._save_history()

            self.assertTrue(cli_main.HISTORY_FILE.is_file())

            cli_main.readline.clear_history()  # 模拟重开一个进程
            cli_main._load_history()

            self.assertEqual(cli_main.readline.get_history_item(1), "SELECT 1;")

    def test_missing_history_file_is_not_an_error(self):
        """第一次运行时根本没有历史文件，不能报错。"""
        with TemporaryDirectory() as directory:
            cli_main.HISTORY_FILE = Path(directory) / "never_written"
            cli_main.readline.clear_history()

            cli_main._load_history()  # 不抛异常即通过

            # 注意是 get_current_history_length()：另一个 get_history_length()
            # 返回的是"历史上限"（且会被 _save_history 设成 1000），不是条数
            self.assertEqual(cli_main.readline.get_current_history_length(), 0)

    def test_unwritable_history_file_is_not_an_error(self):
        """写不进去（只读目录、磁盘满、主目录不可写）也只能咽下去。"""
        with TemporaryDirectory() as directory:
            blocked = Path(directory) / "blocked"
            blocked.mkdir()  # 拿目录占住这个名字，写入必然失败
            cli_main.HISTORY_FILE = blocked
            cli_main.readline.clear_history()
            cli_main.readline.add_history("SELECT 1;")

            cli_main._save_history()  # 不抛异常即通过


if __name__ == "__main__":
    unittest.main()
