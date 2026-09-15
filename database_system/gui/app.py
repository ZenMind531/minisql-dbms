from __future__ import annotations

import json
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from database_system.gui.controller import GuiController
from database_system.gui.dialogs import CreateTableDialog, RowDialog
from database_system.gui.models import ExecutionBatch, TableInfo
from database_system.gui.sql_builder import (
    build_browse_table, build_create_table, build_delete_row, build_drop_table,
    build_insert,
)


class MiniSQLApp:
    UPDATE_SUPPORTED = False

    def __init__(self, root: tk.Tk, data_dir: str | Path = "data/",
                 controller: GuiController | None = None) -> None:
        self.root = root
        self.controller = controller or GuiController(data_dir)
        self.tables: dict[str, TableInfo] = {}
        self.current_table: str | None = None
        self.current_columns: tuple[str, ...] = ()
        self._build()
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.root.after(80, self._poll)
        self.controller.refresh_schema()

    def _build(self) -> None:
        self.root.title("MiniSQL Studio")
        self.root.geometry("1180x760")
        toolbar = ttk.Frame(self.root, padding=6)
        toolbar.pack(fill="x")
        ttk.Button(toolbar, text="打开数据目录", command=self.open_directory).pack(side="left", padx=3)
        ttk.Button(toolbar, text="新建表", command=self.create_table).pack(side="left", padx=3)
        ttk.Button(toolbar, text="刷新", command=self.refresh_schema).pack(side="left", padx=3)
        self.run_button = ttk.Button(toolbar, text="▶ 执行 SQL", command=self.execute_sql)
        self.run_button.pack(side="left", padx=12)
        ttk.Button(toolbar, text="新建控制台", command=self.add_console).pack(side="left", padx=3)
        self.status = tk.StringVar(value="就绪")
        ttk.Label(toolbar, textvariable=self.status).pack(side="right", padx=8)

        main = ttk.Panedwindow(self.root, orient="horizontal")
        main.pack(fill="both", expand=True, padx=6, pady=(0, 6))
        left = ttk.Frame(main, padding=4)
        right = ttk.Panedwindow(main, orient="vertical")
        main.add(left, weight=1)
        main.add(right, weight=4)

        ttk.Label(left, text="对象浏览器").pack(anchor="w", pady=(0, 4))
        self.schema_tree = ttk.Treeview(left, show="tree")
        self.schema_tree.pack(fill="both", expand=True)
        self.schema_tree.bind("<Double-1>", lambda _e: self.open_selected_table())
        self.schema_tree.bind("<Button-3>", self._show_context_menu)
        self.context_menu = tk.Menu(self.root, tearoff=False)
        self.context_menu.add_command(label="打开数据", command=self.open_selected_table)
        self.context_menu.add_command(label="删除表", command=self.drop_selected_table)

        self.console_tabs = ttk.Notebook(right)
        self.result_tabs = ttk.Notebook(right)
        right.add(self.console_tabs, weight=2)
        right.add(self.result_tabs, weight=3)
        self.add_console()

        data_frame = ttk.Frame(self.result_tabs)
        data_toolbar = ttk.Frame(data_frame, padding=4)
        data_toolbar.pack(fill="x")
        ttk.Button(data_toolbar, text="新增行", command=self.insert_row).pack(side="left", padx=3)
        update_state = "normal" if self.UPDATE_SUPPORTED else "disabled"
        update_text = "修改行" if self.UPDATE_SUPPORTED else "修改行（执行器未支持）"
        self.update_button = ttk.Button(data_toolbar, text=update_text, state=update_state)
        self.update_button.pack(side="left", padx=3)
        ttk.Button(data_toolbar, text="删除选中行", command=self.delete_row).pack(side="left", padx=3)
        ttk.Button(data_toolbar, text="刷新数据", command=self.refresh_data).pack(side="left", padx=3)
        self.data_grid = ttk.Treeview(data_frame, show="headings", selectmode="browse")
        yscroll = ttk.Scrollbar(data_frame, orient="vertical", command=self.data_grid.yview)
        self.data_grid.configure(yscrollcommand=yscroll.set)
        self.data_grid.pack(side="left", fill="both", expand=True)
        yscroll.pack(side="right", fill="y")
        self.result_tabs.add(data_frame, text="数据")
        self.original_plan = self._text_tab("原始计划")
        self.optimized_plan = self._text_tab("优化后计划")
        self.plan_json = self._text_tab("JSON")
        self.messages = self._text_tab("消息")
        self.root.bind("<Control-Return>", lambda _e: self.execute_sql())

    def _text_tab(self, title: str) -> tk.Text:
        text = tk.Text(self.result_tabs, wrap="none", font=("Consolas", 10))
        self.result_tabs.add(text, text=title)
        return text

    def add_console(self) -> None:
        frame = ttk.Frame(self.console_tabs)
        editor = tk.Text(frame, wrap="none", undo=True, font=("Consolas", 11))
        editor.pack(fill="both", expand=True)
        self.console_tabs.add(frame, text=f"SQL {len(self.console_tabs.tabs()) + 1}")
        self.console_tabs.select(frame)
        editor.focus_set()

    def _editor(self) -> tk.Text:
        selected = self.console_tabs.nametowidget(self.console_tabs.select())
        return next(child for child in selected.winfo_children() if isinstance(child, tk.Text))

    def execute_sql(self, sql: str | None = None) -> None:
        statement = sql if sql is not None else self._editor().get("1.0", "end").strip()
        if not statement:
            return
        if self.controller.execute(statement):
            self.status.set("正在执行…")
            self.run_button.configure(state="disabled")

    def refresh_schema(self) -> None:
        if self.controller.refresh_schema():
            self.status.set("正在刷新对象…")

    def open_directory(self) -> None:
        path = filedialog.askdirectory(parent=self.root)
        if path and self.controller.open_directory(path):
            self.status.set("正在切换数据目录…")

    def create_table(self) -> None:
        dialog = CreateTableDialog(self.root)
        self.root.wait_window(dialog)
        if dialog.result:
            table, columns = dialog.result
            try:
                sql = build_create_table(table, columns)
            except ValueError as exc:
                messagebox.showerror("输入错误", str(exc), parent=self.root)
                return
            self._log_generated(sql)
            self.execute_sql(sql)

    def _selected_table(self) -> str | None:
        item = self.schema_tree.focus()
        while item:
            tags = self.schema_tree.item(item, "tags")
            if "table" in tags:
                return self.schema_tree.item(item, "text")
            item = self.schema_tree.parent(item)
        return None

    def open_selected_table(self) -> None:
        table = self._selected_table()
        if table:
            self.current_table = table
            self.execute_sql(build_browse_table(table))

    def drop_selected_table(self) -> None:
        table = self._selected_table()
        if not table:
            return
        sql = build_drop_table(table)
        if messagebox.askyesno("确认删除表", f"将执行：\n\n{sql}\n\n此操作不可撤销。", parent=self.root):
            self._log_generated(sql)
            self.execute_sql(sql)

    def insert_row(self) -> None:
        table = self.current_table or self._selected_table()
        info = self.tables.get(table or "")
        if not info:
            messagebox.showinfo("请选择表", "请先在对象浏览器中打开一张表。", parent=self.root)
            return
        dialog = RowDialog(self.root, info.columns)
        self.root.wait_window(dialog)
        if dialog.result is not None:
            sql = build_insert(info.name, [c.name for c in info.columns], dialog.result)
            self._log_generated(sql)
            self.execute_sql(sql)

    def delete_row(self) -> None:
        selected = self.data_grid.selection()
        if not selected or not self.current_table:
            messagebox.showinfo("请选择行", "请先选择要删除的数据行。", parent=self.root)
            return
        values = self.data_grid.item(selected[0], "values")
        info = self.tables[self.current_table]
        converted = [int(value) if column.type_text == "INT" else value
                     for column, value in zip(info.columns, values)]
        sql = build_delete_row(info.name, [c.name for c in info.columns], converted)
        warning = "当前系统没有主键，内容完全相同的多行可能一起被删除。"
        if messagebox.askyesno("确认删除行", f"{warning}\n\n将执行：\n{sql}", parent=self.root):
            self._log_generated(sql)
            self.execute_sql(sql)

    def refresh_data(self) -> None:
        if self.current_table:
            self.execute_sql(build_browse_table(self.current_table))

    def _poll(self) -> None:
        response = self.controller.poll_response()
        if response is not None:
            self.run_button.configure(state="normal")
            if response.error:
                self._show_internal_error(response.error)
            elif response.kind in ("schema", "open"):
                self._show_schema(response.payload)
                self.status.set("就绪")
            else:
                self._show_batch(response.payload)
                self.controller.refresh_schema()
        self.root.after(80, self._poll)

    def _show_schema(self, tables: tuple[TableInfo, ...]) -> None:
        self.tables = {table.name: table for table in tables}
        self.schema_tree.delete(*self.schema_tree.get_children())
        root = self.schema_tree.insert("", "end", text="数据库", open=True)
        for table in tables:
            node = self.schema_tree.insert(root, "end", text=table.name, tags=("table",), open=True)
            for column in table.columns:
                self.schema_tree.insert(node, "end", text=f"{column.name}  {column.type_text}")

    def _show_batch(self, batch: ExecutionBatch) -> None:
        if batch.results:
            result = batch.results[-1]
            self._show_rows(result.columns, result.rows)
            self._set_text(self.original_plan, result.original_plan)
            self._set_text(self.optimized_plan, result.optimized_plan)
            self._set_text(self.plan_json, json.dumps(result.optimized_plan_json, ensure_ascii=False, indent=2))
            self._append_message(f"{result.statement_type}: {result.message} ({result.elapsed_ms:.2f} ms)")
            self.status.set(result.message)
        if batch.error:
            error = batch.error
            self._append_message(f"{error.error_type} at {error.line}:{error.column}: {error.message}")
            self.result_tabs.select(self.messages)
            if error.line and error.column:
                editor = self._editor()
                index = f"{error.line}.{error.column - 1}"
                editor.tag_remove("sql_error", "1.0", "end")
                editor.tag_configure("sql_error", background="#ffd6d6")
                editor.tag_add("sql_error", index, f"{index}+1c")
                editor.see(index)

    def _show_rows(self, columns, rows) -> None:
        self.current_columns = tuple(columns)
        self.data_grid.delete(*self.data_grid.get_children())
        self.data_grid.configure(columns=columns)
        for column in columns:
            self.data_grid.heading(column, text=column)
            self.data_grid.column(column, width=140, anchor="w")
        for row in rows:
            self.data_grid.insert("", "end", values=row)
        if columns:
            self.result_tabs.select(0)

    def _show_context_menu(self, event) -> None:
        item = self.schema_tree.identify_row(event.y)
        if item:
            self.schema_tree.focus(item)
            self.schema_tree.selection_set(item)
            self.context_menu.tk_popup(event.x_root, event.y_root)

    def _log_generated(self, sql: str) -> None:
        self._append_message(f"GUI 生成 SQL: {sql}")

    def _append_message(self, message: str) -> None:
        self.messages.insert("end", message + "\n")
        self.messages.see("end")

    @staticmethod
    def _set_text(widget: tk.Text, value: str) -> None:
        widget.delete("1.0", "end")
        widget.insert("1.0", value)

    def _show_internal_error(self, error: Exception) -> None:
        self._append_message(f"{type(error).__name__}: {error}")
        self.result_tabs.select(self.messages)
        self.status.set("操作失败")

    def close(self) -> None:
        self.status.set("正在关闭…")
        self.root.update_idletasks()
        self.controller.close()
        self.root.destroy()


def main() -> None:
    root = tk.Tk()
    MiniSQLApp(root)
    root.mainloop()
