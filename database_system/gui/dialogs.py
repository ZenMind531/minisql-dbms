from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from database_system.gui.models import ColumnInfo
from database_system.gui.theme import DARK_PALETTE


def coerce_value(text: str, type_text: str):
    if type_text == "INT":
        try:
            return int(text)
        except ValueError as exc:
            raise ValueError(f"{text!r} is not a valid integer") from exc
    return text


class CreateTableDialog(tk.Toplevel):
    def __init__(self, parent: tk.Misc) -> None:
        super().__init__(parent)
        self.title("新建表")
        self.configure(background=DARK_PALETTE["window"])
        self.resizable(False, False)
        self.result: tuple[str, list[tuple[str, str]]] | None = None
        self.table_name = ttk.Entry(self, width=32)
        ttk.Label(self, text="表名").grid(row=0, column=0, padx=10, pady=10, sticky="w")
        self.table_name.grid(row=0, column=1, columnspan=2, padx=10, pady=10)
        self.rows = ttk.Frame(self)
        self.rows.grid(row=1, column=0, columnspan=3, padx=10)
        self._entries: list[tuple[ttk.Entry, ttk.Combobox, ttk.Entry]] = []
        self._add_column()
        ttk.Button(self, text="添加字段", command=self._add_column).grid(row=2, column=0, padx=10, pady=10)
        ttk.Button(self, text="创建", command=self._accept,
                   style="Accent.TButton").grid(row=2, column=1, padx=10, pady=10)
        ttk.Button(self, text="取消", command=self.destroy).grid(row=2, column=2, padx=10, pady=10)
        self.transient(parent)
        self.grab_set()
        self.table_name.focus_set()

    def _add_column(self) -> None:
        row = len(self._entries)
        name = ttk.Entry(self.rows, width=20)
        kind = ttk.Combobox(self.rows, values=("INT", "VARCHAR"), state="readonly", width=10)
        length = ttk.Entry(self.rows, width=8)
        kind.set("INT")
        name.grid(row=row, column=0, padx=3, pady=3)
        kind.grid(row=row, column=1, padx=3, pady=3)
        length.grid(row=row, column=2, padx=3, pady=3)
        self._entries.append((name, kind, length))

    def _accept(self) -> None:
        columns: list[tuple[str, str]] = []
        try:
            for name, kind, length in self._entries:
                column_name = name.get().strip()
                if not column_name:
                    raise ValueError("字段名不能为空")
                type_text = kind.get()
                if type_text == "VARCHAR":
                    size = int(length.get())
                    if not 1 <= size <= 255:
                        raise ValueError("VARCHAR 长度必须在 1 到 255 之间")
                    type_text = f"VARCHAR({size})"
                columns.append((column_name, type_text))
            table = self.table_name.get().strip()
            if not table:
                raise ValueError("表名不能为空")
        except ValueError as exc:
            messagebox.showerror("输入错误", str(exc), parent=self)
            return
        self.result = (table, columns)
        self.destroy()


class RowDialog(tk.Toplevel):
    def __init__(self, parent: tk.Misc, columns: tuple[ColumnInfo, ...],
                 initial_values: tuple[object, ...] | None = None,
                 title: str = "新增行", action_text: str = "插入") -> None:
        super().__init__(parent)
        self.title(title)
        self.configure(background=DARK_PALETTE["window"])
        self.resizable(False, False)
        self.result: list[object] | None = None
        self._entries: list[tuple[ColumnInfo, ttk.Entry]] = []
        for row, column in enumerate(columns):
            ttk.Label(self, text=f"{column.name}  {column.type_text}").grid(
                row=row, column=0, padx=10, pady=6, sticky="w")
            entry = ttk.Entry(self, width=34)
            entry.grid(row=row, column=1, padx=10, pady=6)
            if initial_values is not None:
                entry.insert(0, str(initial_values[row]))
            self._entries.append((column, entry))
        buttons = ttk.Frame(self)
        buttons.grid(row=len(columns), column=0, columnspan=2, pady=10)
        ttk.Button(buttons, text=action_text, command=self._accept,
                   style="Accent.TButton").pack(side="left", padx=5)
        ttk.Button(buttons, text="取消", command=self.destroy).pack(side="left", padx=5)
        self.transient(parent)
        self.grab_set()

    def _accept(self) -> None:
        try:
            self.result = [coerce_value(entry.get(), column.type_text)
                           for column, entry in self._entries]
        except ValueError as exc:
            messagebox.showerror("输入错误", str(exc), parent=self)
            return
        self.destroy()
