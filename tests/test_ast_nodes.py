import unittest

from database_system.sql_compiler.ast_nodes import (
    BinaryExpr,
    BinaryOperator,
    ColumnDef,
    CreateTableStmt,
    DeleteStmt,
    IdentifierExpr,
    InsertStmt,
    LiteralExpr,
    LiteralKind,
    SelectStmt,
    TypeKind,
    TypeSpec,
    UnaryExpr,
    UnaryOperator,
)


class ASTNodeTests(unittest.TestCase):
    def test_column_definition_only_accepts_int_or_bounded_varchar(self) -> None:
        int_column = ColumnDef(
        line=1,
        column=22,
        name="id",
        type_spec=TypeSpec(TypeKind.INT),
    )
        varchar_column = ColumnDef(
        line=1,
        column=30,
        name="name",
        type_spec=TypeSpec(TypeKind.VARCHAR, length=32),
    )

        self.assertEqual(int_column.type_spec, TypeSpec(TypeKind.INT))
        self.assertEqual(
            varchar_column.type_spec,
            TypeSpec(TypeKind.VARCHAR, length=32),
        )

        with self.assertRaisesRegex(ValueError, "VARCHAR length"):
            ColumnDef(
                line=1,
                column=1,
                name="bad",
                type_spec=TypeSpec(TypeKind.VARCHAR, length=0),
            )

        with self.assertRaisesRegex(ValueError, "column type"):
            ColumnDef(
                line=1,
                column=1,
                name="bad",
                type_spec=TypeSpec(TypeKind.BOOL),
            )

    def test_type_spec_rejects_invalid_varchar_lengths_directly(self) -> None:
        for length in (None, 0, 256):
            with self.subTest(length=length):
                with self.assertRaisesRegex(ValueError, "VARCHAR length"):
                    TypeSpec(TypeKind.VARCHAR, length=length)


    def test_float_literal_is_representable_without_becoming_a_column_type(self) -> None:
        literal = LiteralExpr(
        line=1,
        column=8,
        value=3.5,
        literal_kind=LiteralKind.FLOAT,
    )

        self.assertEqual(literal.value, 3.5)
        self.assertIs(literal.literal_kind, LiteralKind.FLOAT)
        self.assertIsNone(literal.resolved_type)

    def test_literal_value_must_match_its_literal_kind(self) -> None:
        invalid_literals = [
            ("12", LiteralKind.INTEGER),
            (True, LiteralKind.INTEGER),
            (3, LiteralKind.FLOAT),
            (3.5, LiteralKind.STRING),
        ]

        for value, literal_kind in invalid_literals:
            with self.subTest(value=value, literal_kind=literal_kind):
                with self.assertRaisesRegex(ValueError, "literal value"):
                    LiteralExpr(
                        line=1,
                        column=1,
                        value=value,
                        literal_kind=literal_kind,
                    )


    def test_unary_minus_is_a_separate_normalized_ast_node(self) -> None:
        expression = UnaryExpr(
        line=1,
        column=1,
        op=UnaryOperator.MINUS,
        operand=LiteralExpr(
            line=1,
            column=2,
            value=12,
            literal_kind=LiteralKind.INTEGER,
        ),
    )

        self.assertEqual(expression.op.value, "-")
        self.assertEqual(expression.operand.value, 12)


    def test_expression_type_can_be_filled_by_semantic_analysis(self) -> None:
        expression = IdentifierExpr(line=1, column=7, name="age")

        self.assertIsNone(expression.resolved_type)
        expression.resolved_type = TypeSpec(TypeKind.INT)
        self.assertEqual(expression.resolved_type, TypeSpec(TypeKind.INT))


    def test_select_star_and_explicit_columns_have_one_unambiguous_field(self) -> None:
        select_all = SelectStmt(
        line=1,
        column=1,
        columns=None,
        table="student",
        where=None,
    )
        select_some = SelectStmt(
        line=2,
        column=1,
        columns=["id", "name"],
        table="student",
        where=None,
    )

        self.assertIsNone(select_all.columns)
        self.assertEqual(select_some.columns, ["id", "name"])

        with self.assertRaisesRegex(ValueError, "at least one column"):
            SelectStmt(line=3, column=1, columns=[], table="student", where=None)


    def test_statement_nodes_match_the_four_supported_sql_statements(self) -> None:
        id_expr = IdentifierExpr(line=1, column=36, name="id")
        one = LiteralExpr(
        line=1,
        column=41,
        value=1,
        literal_kind=LiteralKind.INTEGER,
    )
        predicate = BinaryExpr(
        line=1,
        column=39,
        op=BinaryOperator.EQUAL,
        left=id_expr,
        right=one,
    )
        column = ColumnDef(
        line=1,
        column=22,
        name="id",
        type_spec=TypeSpec(TypeKind.INT),
    )

        create = CreateTableStmt(
        line=1,
        column=1,
        table="student",
        columns=[column],
    )
        insert = InsertStmt(
        line=2,
        column=1,
        table="student",
        columns=["id"],
        values=[one],
    )
        select = SelectStmt(
        line=3,
        column=1,
        columns=["id"],
        table="student",
        where=predicate,
    )
        delete = DeleteStmt(
        line=4,
        column=1,
        table="student",
        where=predicate,
    )

        self.assertEqual(create.columns, [column])
        self.assertEqual(insert.columns, ["id"])
        self.assertEqual(insert.values, [one])
        self.assertIs(select.where, predicate)
        self.assertIs(delete.where, predicate)


if __name__ == "__main__":
    unittest.main()
