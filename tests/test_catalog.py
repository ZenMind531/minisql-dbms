"""In-memory Catalog contracts; no parser or semantic analyzer required."""

import unittest

from database_system.sql_compiler.ast_nodes import ColumnDef, TypeKind, TypeSpec
from database_system.sql_compiler.catalog import Catalog, TableSchema
from database_system.utils.errors import SemanticError


def column(name="id", kind=TypeKind.INT, length=None):
    return ColumnDef(line=2, column=12, name=name,
                     type_spec=TypeSpec(kind, length))


class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.catalog = Catalog()
        self.columns = [column(), column("name", TypeKind.VARCHAR, 32)]

    def test_create_and_find_preserve_name_types_and_column_order(self):
        self.assertIsNone(self.catalog.create_table("student", self.columns))
        schema = self.catalog.find_table("student")
        self.assertIsInstance(schema, TableSchema)
        self.assertEqual(schema.name, "student")
        self.assertEqual(schema.columns, self.columns)
        self.assertIsNone(schema.first_page)
        self.assertEqual(self.catalog.find_column("student", "name"), self.columns[1])
        self.assertEqual(self.catalog.get_type("student", "id"), TypeSpec(TypeKind.INT))
        self.assertEqual(self.catalog.get_type("student", "name"),
                         TypeSpec(TypeKind.VARCHAR, 32))

    def test_missing_table_and_column_return_none(self):
        self.assertIsNone(self.catalog.find_table("missing"))
        self.assertIsNone(self.catalog.find_column("missing", "id"))
        self.assertIsNone(self.catalog.get_type("missing", "id"))
        self.catalog.create_table("student", self.columns)
        self.assertIsNone(self.catalog.find_column("student", "missing"))
        self.assertIsNone(self.catalog.get_type("student", "missing"))

    def test_duplicate_table_does_not_replace_original(self):
        self.catalog.create_table("student", self.columns)
        with self.assertRaises(SemanticError) as caught:
            self.catalog.create_table("student", [column("other")])
        self.assertIn("student", caught.exception.message)
        self.assertEqual(self.catalog.find_table("student").columns, self.columns)

    def test_duplicate_columns_fail_atomically_and_report_position(self):
        duplicate = column("id", TypeKind.VARCHAR, 8)
        duplicate.line, duplicate.column = 3, 24
        with self.assertRaises(SemanticError) as caught:
            self.catalog.create_table("student", [column(), duplicate])
        error = caught.exception
        self.assertEqual(error.type, "SemanticError")
        self.assertEqual((error.line, error.column), (3, 24))
        self.assertIn("id", error.message)
        self.assertIn("SemanticError", str(error))
        self.assertIn("3", str(error))
        self.assertIn("24", str(error))
        self.assertIsNone(self.catalog.find_table("student"))
        self.catalog.create_table("student", self.columns)
        self.assertEqual(self.catalog.find_table("student").columns, self.columns)

    def test_same_column_name_in_different_tables_is_allowed(self):
        self.catalog.create_table("student", [column()])
        self.catalog.create_table("teacher", [column("id", TypeKind.VARCHAR, 10)])
        self.assertEqual(self.catalog.get_type("student", "id"), TypeSpec(TypeKind.INT))
        self.assertEqual(self.catalog.get_type("teacher", "id"), TypeSpec(TypeKind.VARCHAR, 10))

    def test_varchar_accepts_inclusive_length_boundaries(self):
        for length in [1, 255]:
            with self.subTest(length=length):
                name = f"table_{length}"
                self.catalog.create_table(name, [column("text", TypeKind.VARCHAR, length)])
                self.assertEqual(self.catalog.get_type(name, "text"),
                                 TypeSpec(TypeKind.VARCHAR, length))

    def test_varchar_revalidates_mutable_column_definitions(self):
        # ColumnDef is mutable: Catalog must not rely solely on its constructor.
        for length in [None, 0, 256, 1.5, True]:
            with self.subTest(length=length):
                invalid = column("text", TypeKind.VARCHAR, 8)
                # Deliberately corrupt an otherwise valid frozen TypeSpec to
                # test Catalog's defensive validation independently of AST validation.
                object.__setattr__(invalid.type_spec, "length", length)
                with self.assertRaises(SemanticError):
                    self.catalog.create_table("bad", [column(), invalid])
                self.assertIsNone(self.catalog.find_table("bad"))

    def test_bool_is_not_a_supported_column_type(self):
        invalid = column()
        invalid.type_spec = TypeSpec(TypeKind.BOOL)
        with self.assertRaises(SemanticError):
            self.catalog.create_table("bad", [invalid])
        self.assertIsNone(self.catalog.find_table("bad"))

    def test_empty_schema_is_rejected(self):
        with self.assertRaises(SemanticError):
            self.catalog.create_table("empty", [])
        self.assertIsNone(self.catalog.find_table("empty"))

    def test_input_mutation_does_not_change_catalog(self):
        self.catalog.create_table("student", self.columns)
        self.columns[0].name = "changed"
        self.columns[1].type_spec = TypeSpec(TypeKind.INT)
        self.columns.clear()
        self.assertEqual(self.catalog.find_column("student", "id").name, "id")
        self.assertEqual(self.catalog.get_type("student", "name"), TypeSpec(TypeKind.VARCHAR, 32))

    def test_lookup_mutation_does_not_change_catalog(self):
        self.catalog.create_table("student", self.columns)
        self.catalog.find_column("student", "id").name = "changed"
        schema = self.catalog.find_table("student")
        schema.columns[0].name = "changed_again"
        schema.columns.clear()
        self.assertEqual(self.catalog.find_table("student").columns, self.columns)

    def test_catalog_instances_are_independent(self):
        self.catalog.create_table("student", self.columns)
        self.assertIsNone(Catalog().find_table("student"))

    def test_lookup_preserves_identifier_case(self):
        self.catalog.create_table("Student", [column("ID")])
        self.assertIsNotNone(self.catalog.find_column("Student", "ID"))
        self.assertIsNone(self.catalog.find_table("student"))
        self.assertIsNone(self.catalog.find_column("Student", "id"))


if __name__ == "__main__":
    unittest.main()
