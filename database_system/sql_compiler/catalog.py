"""In-memory table metadata for the compiler.

Names are matched exactly, preserving identifier spelling and case. Column
list order is schema order (and therefore the implicit INSERT value order).
Inputs and lookup results are copied so mutable AST nodes cannot bypass
validation by modifying registered metadata. Missing lookups return None.
"""

from copy import deepcopy
from dataclasses import dataclass

from database_system.sql_compiler.ast_nodes import ColumnDef, TypeKind, TypeSpec
from database_system.utils.errors import SemanticError


@dataclass(slots=True)
class TableSchema:
    name: str
    columns: list[ColumnDef]
    # The memory-only catalog does not allocate storage pages.
    first_page: int | None = None


class Catalog:
    def __init__(self) -> None:
        self._tables: dict[str, TableSchema] = {}

    def create_table(self, name: str, columns: list[ColumnDef]) -> None:
        """Validate a complete schema before registering it atomically.

        The API supplies no table-name source position, so table-level errors
        use 1:1. Column-level errors retain the offending ColumnDef position.
        """
        if name in self._tables:
            raise SemanticError(f"Table '{name}' already exists")
        if not columns:
            raise SemanticError(f"Table '{name}' requires at least one column")

        names: set[str] = set()
        for column in columns:
            if column.name in names:
                raise SemanticError(
                    f"Duplicate column '{column.name}' in table '{name}'",
                    line=column.line, column=column.column,
                )
            names.add(column.name)
            type_spec = column.type_spec
            if type_spec.kind is TypeKind.INT:
                if type_spec.length is not None:
                    raise SemanticError(
                        f"INT column '{column.name}' must not have a length",
                        line=column.line, column=column.column,
                    )
            elif type_spec.kind is TypeKind.VARCHAR:
                if type(type_spec.length) is not int or not 1 <= type_spec.length <= 255:
                    raise SemanticError(
                        f"VARCHAR length for column '{column.name}' must be an integer between 1 and 255",
                        line=column.line, column=column.column,
                    )
            else:
                raise SemanticError(
                    f"Column '{column.name}' type must be INT or VARCHAR",
                    line=column.line, column=column.column,
                )

        self._tables[name] = TableSchema(name=name, columns=deepcopy(columns))

    def find_table(self, name: str) -> TableSchema | None:
        """Return a schema snapshot, or None if the table does not exist."""
        schema = self._tables.get(name)
        return deepcopy(schema) if schema is not None else None

    def find_column(self, table: str, column: str) -> ColumnDef | None:
        """Return a column snapshot, or None for a missing table or column."""
        schema = self._tables.get(table)
        if schema is not None:
            for definition in schema.columns:
                if definition.name == column:
                    return deepcopy(definition)
        return None

    def get_type(self, table: str, column: str) -> TypeSpec | None:
        """Return the column's type, including its declared VARCHAR length."""
        definition = self.find_column(table, column)
        return definition.type_spec if definition is not None else None


__all__ = ["Catalog", "TableSchema"]
