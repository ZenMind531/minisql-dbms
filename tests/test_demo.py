import unittest
from database_system.sql_compiler.catalog import Catalog
from database_system.sql_compiler.ast_nodes import SelectStmt
from database_system.sql_compiler.demo import render_compilation

class DemoTests(unittest.TestCase):
    def test_demo_shows_all_backend_stages_for_valid_statement(self):
        tokens = []
        stmt = SelectStmt(line=1, column=1, columns=["name"], table="student", where=None)
        catalog = Catalog()
        from database_system.sql_compiler.ast_nodes import ColumnDef, TypeKind, TypeSpec
        catalog.create_table("student", [ColumnDef(line=1,column=1,name="name",type_spec=TypeSpec(TypeKind.VARCHAR, 8))])
        output = render_compilation(tokens, [stmt], catalog)
        for label in ["Token 流:", "AST:", "语义检查结果: OK", "原始 Logical Plan:", "优化后的 Logical Plan:"]:
            self.assertIn(label, output)

    def test_demo_reports_semantic_error_and_continues(self):
        stmt = SelectStmt(line=3, column=4, columns=["missing"], table="student", where=None)
        output = render_compilation([], [stmt], Catalog())
        self.assertIn("语义检查失败:", output)
        self.assertIn("table 'student' does not exist", output)

if __name__ == "__main__":
    unittest.main()
