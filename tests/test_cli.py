"""CLI 参数与批处理模式测试。"""

from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

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


if __name__ == "__main__":
    unittest.main()
