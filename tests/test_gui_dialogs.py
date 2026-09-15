import pytest

from database_system.gui.dialogs import coerce_value


def test_coerce_value_uses_column_type() -> None:
    assert coerce_value("42", "INT") == 42
    assert coerce_value("Alice", "VARCHAR(20)") == "Alice"


def test_coerce_value_rejects_bad_integer() -> None:
    with pytest.raises(ValueError, match="integer"):
        coerce_value("abc", "INT")
