import tkinter as tk

import pytest

from database_system.gui.app import MiniSQLApp
from database_system.gui.models import ColumnInfo, TableInfo


class Controller:
    busy = False

    def refresh_schema(self):
        return True

    def poll_response(self):
        return None

    def close(self):
        pass

    def execute(self, sql):
        self.executed = sql
        return True


def build_app():
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("Tk display is unavailable")
    return root, MiniSQLApp(root, controller=Controller())


def test_gui_marks_update_as_available_when_executor_supports_it() -> None:
    assert MiniSQLApp.UPDATE_SUPPORTED is True


def test_gui_window_builds_with_injected_controller() -> None:
    root, app = build_app()
    try:
        root.update_idletasks()
        assert root.title() == "MiniSQL Studio"
        assert len(app.console_tabs.tabs()) == 1
        assert len(app.result_tabs.tabs()) == 5
        assert app.console_tabs.cget("style") == "Closable.TNotebook"
    finally:
        root.destroy()


def test_close_console_allows_last_editor_to_disappear() -> None:
    root, app = build_app()
    try:
        tab_id = app.console_tabs.tabs()[0]

        assert app.close_console(tab_id) is True
        assert app.console_tabs.tabs() == ()
        assert app._editors == {}
    finally:
        root.destroy()


def test_close_console_saves_sql_when_requested(monkeypatch, tmp_path) -> None:
    root, app = build_app()
    sql_file = tmp_path / "query.sql"
    try:
        tab_id = app.console_tabs.tabs()[0]
        app._editors[tab_id].insert("1.0", "SELECT * FROM users;")
        monkeypatch.setattr("database_system.gui.app.messagebox.askyesnocancel", lambda *a, **k: True)
        monkeypatch.setattr("database_system.gui.app.filedialog.asksaveasfilename",
                            lambda *a, **k: str(sql_file))

        assert app.close_console(tab_id) is True
        assert sql_file.read_text(encoding="utf-8") == "SELECT * FROM users;"
        assert app.console_tabs.tabs() == ()
    finally:
        root.destroy()


def test_close_console_cancel_keeps_editor(monkeypatch) -> None:
    root, app = build_app()
    try:
        tab_id = app.console_tabs.tabs()[0]
        app._editors[tab_id].insert("1.0", "SELECT 1;")
        monkeypatch.setattr("database_system.gui.app.messagebox.askyesnocancel", lambda *a, **k: None)

        assert app.close_console(tab_id) is False
        assert app.console_tabs.tabs() == (tab_id,)
    finally:
        root.destroy()


def test_update_row_generates_sql_from_selected_old_and_new_values(monkeypatch) -> None:
    root, app = build_app()
    try:
        columns = (ColumnInfo("id", "INT"), ColumnInfo("name", "VARCHAR(20)"))
        app.current_table = "student"
        app.tables["student"] = TableInfo("student", columns)
        app._show_rows(("id", "name"), ((1, "Alice"),))
        item = app.data_grid.get_children()[0]
        app.data_grid.selection_set(item)

        class FakeDialog:
            result = [2, "Bob"]

            def __init__(self, parent, received_columns, **options):
                assert received_columns == columns
                assert options["initial_values"] == (1, "Alice")

        monkeypatch.setattr("database_system.gui.app.RowDialog", FakeDialog)
        monkeypatch.setattr(root, "wait_window", lambda _dialog: None)
        monkeypatch.setattr("database_system.gui.app.messagebox.askyesno", lambda *a, **k: True)

        app.update_row()

        assert app.controller.executed == (
            "UPDATE student SET id = 2, name = 'Bob' WHERE id = 1 AND name = 'Alice';"
        )
    finally:
        root.destroy()
