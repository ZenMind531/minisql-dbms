"""Recursive-descent parser for the SQL subset in ``docs/grammar.md``."""

from __future__ import annotations

from collections.abc import Collection

from database_system.sql_compiler.ast_nodes import (
    BinaryExpr,
    BinaryOperator,
    ColumnDef,
    CreateTableStmt,
    DeleteStmt,
    Expr,
    IdentifierExpr,
    InsertStmt,
    LiteralExpr,
    LiteralKind,
    SelectStmt,
    Stmt,
    TypeKind,
    TypeSpec,
    UnaryExpr,
    UnaryOperator,
)
from database_system.sql_compiler.lexer import Token, TokenType
from database_system.utils.errors import ParseError


COMPARISON_OPERATORS = {
    "=": BinaryOperator.EQUAL,
    "!=": BinaryOperator.NOT_EQUAL,
    ">": BinaryOperator.GREATER_THAN,
    ">=": BinaryOperator.GREATER_THAN_OR_EQUAL,
    "<": BinaryOperator.LESS_THAN,
    "<=": BinaryOperator.LESS_THAN_OR_EQUAL,
}

ADDITIVE_OPERATORS = {
    "+": BinaryOperator.ADD,
    "-": BinaryOperator.SUBTRACT,
}

MULTIPLICATIVE_OPERATORS = {
    "*": BinaryOperator.MULTIPLY,
    "/": BinaryOperator.DIVIDE,
}


class Parser:
    """Turn a complete Token stream into a list of statement AST nodes."""

    # Each nested pair traverses all expression-precedence functions, so keep
    # this comfortably below Python's recursion limit and report ParseError.
    MAX_PARENTHESIS_DEPTH = 64

    def __init__(self, tokens: list[Token]):
        if not tokens:
            raise ValueError("Parser requires a Token stream ending in EOF")
        self.tokens = tokens
        self._index = 0
        self._parenthesis_depth = 0

    def parse(self) -> list[Stmt]:
        statements: list[Stmt] = []
        while not self._at_eof():
            statements.append(self._parse_statement())
            self._consume_lexeme(";", {";"})
        self._consume_type(TokenType.EOF, {"EOF"})
        return statements

    # -------------------------------------------------------------- statements

    def _parse_statement(self) -> Stmt:
        token = self._current()
        if self._is_keyword("CREATE"):
            return self._parse_create_table()
        if self._is_keyword("INSERT"):
            return self._parse_insert()
        if self._is_keyword("SELECT"):
            return self._parse_select()
        if self._is_keyword("DELETE"):
            return self._parse_delete()
        raise self._error(token, {"statement (CREATE, INSERT, SELECT, DELETE)"})

    def _parse_create_table(self) -> CreateTableStmt:
        start = self._consume_keyword("CREATE")
        self._consume_keyword("TABLE")
        table = self._consume_identifier()
        self._consume_lexeme("(", {"("})
        columns = [self._parse_column_definition()]
        while self._match_lexeme(","):
            columns.append(self._parse_column_definition())
        self._consume_lexeme(")", {")"})
        return CreateTableStmt(
            line=start.line,
            column=start.column,
            table=table.lexeme,
            columns=columns,
        )

    def _parse_column_definition(self) -> ColumnDef:
        name = self._consume_identifier()
        type_spec = self._parse_type_specification()
        return ColumnDef(
            line=name.line,
            column=name.column,
            name=name.lexeme,
            type_spec=type_spec,
        )

    def _parse_type_specification(self) -> TypeSpec:
        if self._match_keyword("INT"):
            return TypeSpec(TypeKind.INT)
        if not self._match_keyword("VARCHAR"):
            raise self._error(self._current(), {"INT", "VARCHAR(n)"})

        self._consume_lexeme("(", {"VARCHAR(n)"})
        length_token = self._current()
        if not self._is_integer_literal(length_token):
            raise self._error(length_token, {"VARCHAR integer length 1..255"})
        self._advance()
        length = int(length_token.lexeme)
        if not 1 <= length <= 255:
            raise self._error(length_token, {"VARCHAR length 1..255"})
        self._consume_lexeme(")", {"VARCHAR(n)"})
        return TypeSpec(TypeKind.VARCHAR, length)

    def _parse_insert(self) -> InsertStmt:
        start = self._consume_keyword("INSERT")
        self._consume_keyword("INTO")
        table = self._consume_identifier()
        columns = None
        if self._match_lexeme("("):
            columns = self._parse_identifier_list()
            self._consume_lexeme(")", {")"})
        self._consume_keyword("VALUES")
        self._consume_lexeme("(", {"("})
        values = self._parse_expression_list()
        self._consume_lexeme(")", {")"})
        return InsertStmt(
            line=start.line,
            column=start.column,
            table=table.lexeme,
            columns=columns,
            values=values,
        )

    def _parse_select(self) -> SelectStmt:
        start = self._consume_keyword("SELECT")
        if self._match_lexeme("*"):
            columns = None
        else:
            columns = self._parse_identifier_list()
        self._consume_keyword("FROM")
        table = self._consume_identifier()
        where = self._parse_expression() if self._match_keyword("WHERE") else None
        return SelectStmt(
            line=start.line,
            column=start.column,
            columns=columns,
            table=table.lexeme,
            where=where,
        )

    def _parse_delete(self) -> DeleteStmt:
        start = self._consume_keyword("DELETE")
        self._consume_keyword("FROM")
        table = self._consume_identifier()
        where = self._parse_expression() if self._match_keyword("WHERE") else None
        return DeleteStmt(
            line=start.line,
            column=start.column,
            table=table.lexeme,
            where=where,
        )

    def _parse_identifier_list(self) -> list[str]:
        names = [self._consume_identifier().lexeme]
        while self._match_lexeme(","):
            names.append(self._consume_identifier().lexeme)
        return names

    def _parse_expression_list(self) -> list[Expr]:
        if self._check_lexeme(")"):
            raise self._error(self._current(), {"expression"})
        expressions = [self._parse_expression()]
        while self._match_lexeme(","):
            expressions.append(self._parse_expression())
        return expressions

    # ------------------------------------------------------------- expressions

    def _parse_expression(self) -> Expr:
        return self._parse_or_expression()

    def _parse_or_expression(self) -> Expr:
        expression = self._parse_and_expression()
        while self._match_keyword("OR"):
            right = self._parse_and_expression()
            expression = self._binary(BinaryOperator.OR, expression, right)
        return expression

    def _parse_and_expression(self) -> Expr:
        expression = self._parse_comparison_expression()
        while self._match_keyword("AND"):
            right = self._parse_comparison_expression()
            expression = self._binary(BinaryOperator.AND, expression, right)
        return expression

    def _parse_comparison_expression(self) -> Expr:
        expression = self._parse_not_expression()
        operator = COMPARISON_OPERATORS.get(self._current().lexeme)
        if operator is not None:
            self._advance()
            right = self._parse_not_expression()
            expression = self._binary(operator, expression, right)
        return expression

    def _parse_not_expression(self) -> Expr:
        operators: list[Token] = []
        while self._is_keyword("NOT"):
            operators.append(self._advance())
        expression = self._parse_additive_expression()
        for token in reversed(operators):
            expression = UnaryExpr(
                line=token.line,
                column=token.column,
                op=UnaryOperator.NOT,
                operand=expression,
            )
        return expression

    def _parse_additive_expression(self) -> Expr:
        expression = self._parse_multiplicative_expression()
        while self._current().lexeme in ADDITIVE_OPERATORS:
            operator = ADDITIVE_OPERATORS[self._advance().lexeme]
            right = self._parse_multiplicative_expression()
            expression = self._binary(operator, expression, right)
        return expression

    def _parse_multiplicative_expression(self) -> Expr:
        expression = self._parse_unary_expression()
        while self._current().lexeme in MULTIPLICATIVE_OPERATORS:
            operator = MULTIPLICATIVE_OPERATORS[self._advance().lexeme]
            right = self._parse_unary_expression()
            expression = self._binary(operator, expression, right)
        return expression

    def _parse_unary_expression(self) -> Expr:
        if self._check_lexeme("+") or self._check_lexeme("-"):
            token = self._advance()
            operator = UnaryOperator.PLUS if token.lexeme == "+" else UnaryOperator.MINUS
            return UnaryExpr(
                line=token.line,
                column=token.column,
                op=operator,
                operand=self._parse_primary_expression(),
            )
        return self._parse_primary_expression()

    def _parse_primary_expression(self) -> Expr:
        token = self._current()
        if token.type is TokenType.IDENTIFIER:
            self._advance()
            return IdentifierExpr(
                line=token.line,
                column=token.column,
                name=token.lexeme,
            )
        if token.type is TokenType.CONST:
            self._advance()
            return self._literal(token)
        if self._match_lexeme("("):
            if self._parenthesis_depth >= self.MAX_PARENTHESIS_DEPTH:
                raise self._error(token, {"expression nesting within safe limit"})
            self._parenthesis_depth += 1
            try:
                expression = self._parse_expression()
                self._consume_lexeme(")", {")"})
                return expression
            finally:
                self._parenthesis_depth -= 1
        raise self._error(token, {"expression"})

    @staticmethod
    def _literal(token: Token) -> LiteralExpr:
        lexeme = token.lexeme
        if lexeme.startswith("'"):
            kind = LiteralKind.STRING
            value = lexeme[1:-1].replace("''", "'")
        elif "." in lexeme:
            kind = LiteralKind.FLOAT
            value = float(lexeme)
        else:
            kind = LiteralKind.INTEGER
            value = int(lexeme)
        return LiteralExpr(
            line=token.line,
            column=token.column,
            value=value,
            literal_kind=kind,
        )

    @staticmethod
    def _binary(operator: BinaryOperator, left: Expr, right: Expr) -> BinaryExpr:
        return BinaryExpr(
            line=left.line,
            column=left.column,
            op=operator,
            left=left,
            right=right,
        )

    # --------------------------------------------------------------- token API

    def _current(self) -> Token:
        if self._index >= len(self.tokens):
            last = self.tokens[-1]
            raise ParseError(
                "unexpected end of Token stream; expected EOF",
                line=last.line,
                column=last.column,
            )
        return self.tokens[self._index]

    def _advance(self) -> Token:
        token = self._current()
        self._index += 1
        return token

    def _at_eof(self) -> bool:
        return self._current().type is TokenType.EOF

    def _is_keyword(self, keyword: str) -> bool:
        token = self._current()
        return token.type is TokenType.KEYWORD and token.lexeme.upper() == keyword

    def _match_keyword(self, keyword: str) -> bool:
        if not self._is_keyword(keyword):
            return False
        self._advance()
        return True

    def _consume_keyword(self, keyword: str) -> Token:
        if not self._is_keyword(keyword):
            raise self._error(self._current(), {keyword})
        return self._advance()

    def _check_lexeme(self, lexeme: str) -> bool:
        return self._current().lexeme == lexeme

    def _match_lexeme(self, lexeme: str) -> bool:
        if not self._check_lexeme(lexeme):
            return False
        self._advance()
        return True

    def _consume_lexeme(self, lexeme: str, expected: Collection[str]) -> Token:
        if not self._check_lexeme(lexeme):
            raise self._error(self._current(), expected)
        return self._advance()

    def _consume_identifier(self) -> Token:
        return self._consume_type(TokenType.IDENTIFIER, {"IDENTIFIER"})

    def _consume_type(self, token_type: TokenType, expected: Collection[str]) -> Token:
        if self._current().type is not token_type:
            raise self._error(self._current(), expected)
        return self._advance()

    @staticmethod
    def _is_integer_literal(token: Token) -> bool:
        return token.type is TokenType.CONST and token.lexeme.isdigit()

    @staticmethod
    def _error(token: Token, expected: Collection[str]) -> ParseError:
        actual = "EOF" if token.type is TokenType.EOF else repr(token.lexeme)
        expected_text = ", ".join(sorted(expected))
        return ParseError(
            f"unexpected token {actual}; expected {{{expected_text}}}",
            line=token.line,
            column=token.column,
        )


__all__ = ["Parser"]
