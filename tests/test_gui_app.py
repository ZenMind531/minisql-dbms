import tkinter as tk

import pytest

from database_system.gui.app import MiniSQLApp


def test_gui_marks_update_as_unavailable_until_executor_supports_it() -> None:
    assert MiniSQLApp.UPDATE_SUPPORTED is False


def test_gui_window_builds_with_injected_controller() -> None:
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("Tk display is unavailable")

    class Controller:
        busy = False

        def refresh_schema(self):
            return True

        def poll_response(self):
            return None

        def close(self):
            pass

    try:
        app = MiniSQLApp(root, controller=Controller())
        root.update_idletasks()
        assert root.title() == "MiniSQL Studio"
        assert len(app.console_tabs.tabs()) == 1
        assert len(app.result_tabs.tabs()) == 5
    finally:
        root.destroy()
