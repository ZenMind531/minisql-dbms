import json
import unittest
from pathlib import Path

from database_system.sql_compiler.demo import compile_sql
from database_system.sql_compiler.lexer import Lexer
from database_system.sql_compiler.parser import Parser
from database_system.utils.errors import LexError, ParseError


CASES_PATH = Path(__file__).with_name("sql") / "compiler_cases.json"


class CompilerSqlCaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.cases = json.loads(CASES_PATH.read_text(encoding="utf-8"))

    def test_case_set_contains_at_least_thirty_named_cases(self) -> None:
        self.assertGreaterEqual(len(self.cases), 30)
        self.assertEqual(len({case["name"] for case in self.cases}), len(self.cases))

    def test_cases_exercise_every_required_compiler_outcome(self) -> None:
        self.assertEqual(
            {case["outcome"] for case in self.cases},
            {"valid", "lex_error", "parse_error", "semantic_error"},
        )

    def test_each_sql_case_reaches_its_declared_outcome(self) -> None:
        for case in self.cases:
            with self.subTest(case=case["name"]):
                source = case["sql"]
                if case["outcome"] == "lex_error":
                    with self.assertRaises(LexError):
                        Lexer(source).tokenize()
                elif case["outcome"] == "parse_error":
                    with self.assertRaises(ParseError):
                        Parser(Lexer(source).tokenize()).parse()
                elif case["outcome"] == "semantic_error":
                    self.assertIn("SemanticError", compile_sql(source))
                else:
                    statements = Parser(Lexer(source).tokenize()).parse()
                    self.assertGreaterEqual(len(statements), 1)


if __name__ == "__main__":
    unittest.main()
