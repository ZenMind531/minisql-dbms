import tkinter as tk

import pytest

from database_system.gui.dialogs import RowDialog, coerce_value
from database_system.gui.models import ColumnInfo


def test_coerce_value_uses_column_type() -> None:
    assert coerce_value("42", "INT") == 42
    assert coerce_value("Alice", "VARCHAR(20)") == "Alice"


def test_coerce_value_rejects_bad_integer() -> None:
    with pytest.raises(ValueError, match="integer"):
        coerce_value("abc", "INT")


def test_row_dialog_prefills_values_for_update() -> None:
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("Tk display is unavailable")
    root.withdraw()
    dialog = None
    try:
        columns = (ColumnInfo("id", "INT"), ColumnInfo("name", "VARCHAR(20)"))
        dialog = RowDialog(root, columns, initial_values=(7, "Alice"), title="修改行",
                           action_text="保存修改")

        assert dialog.title() == "修改行"
        assert [entry.get() for _, entry in dialog._entries] == ["7", "Alice"]
    finally:
        if dialog is not None:
            dialog.destroy()
        root.destroy()
