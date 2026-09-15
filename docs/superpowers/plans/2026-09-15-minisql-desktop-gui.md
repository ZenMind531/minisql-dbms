# MiniSQL Desktop GUI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a standard-library Tkinter desktop manager for SQL execution, schema browsing, graphical table/data operations, and logical-plan inspection.

**Architecture:** A Tk view delegates to a controller and one database-owning worker thread. GUI write actions generate SQL and use the same compiler/executor pipeline as the CLI; view code never edits storage directly.

**Tech Stack:** Python 3.11, tkinter/ttk, threading, queue, unittest/pytest.

**Spec:** `docs/superpowers/specs/2026-09-14-minisql-desktop-gui-design.md`

## Global Constraints

- Use Python 3.11 standard library only.
- Preserve `MiniDB.execute()` and all existing CLI behavior.
- Do not modify frozen Token, AST, Plan, or storage contracts.
- Keep unsupported UPDATE editing disabled until Executor support exists.
- Every write action generates SQL and passes through MiniSQL normally.

---

### Task 1: Structured GUI execution service

**Files:**
- Create: `database_system/gui/__init__.py`
- Create: `database_system/gui/models.py`
- Create: `database_system/gui/service.py`
- Test: `tests/test_gui_service.py`

**Interfaces:**
- Produces: `ExecutionResult`, `PlanView`, `DatabaseService.execute(sql)`, `DatabaseService.schema_snapshot()`, `DatabaseService.close()`.
- Consumes: `Lexer`, `Parser`, `SemanticAnalyzer`, `Planner`, `Optimizer`, `Executor`, and `MiniDB` public attributes without changing engine contracts.

- [ ] Write failing tests for query columns/rows, command messages, plan text/JSON, multi-statement failure, schema snapshots, and MiniSQL error fields.
- [ ] Run `python -m pytest tests/test_gui_service.py -v` and confirm failure from missing GUI modules.
- [ ] Implement immutable result models and the minimal service pipeline; infer `SELECT *` columns from Catalog and use fixed names for SHOW results.
- [ ] Run the service tests and existing compiler/engine tests.
- [ ] Commit with `feat(gui): add structured database service`.

### Task 2: SQL generation for graphical operations

**Files:**
- Create: `database_system/gui/sql_builder.py`
- Test: `tests/test_gui_sql_builder.py`

**Interfaces:**
- Produces: `quote_identifier`, `literal_sql`, `build_create_table`, `build_insert`, `build_update`, `build_delete_row`, `build_drop_table`, `build_browse_table`.
- Consumes: table/column names, `TypeSpec`, and Python scalar values.

- [ ] Write failing tests for identifier validation, quote escaping, VARCHAR lengths, complete-row INSERT, full-old-row DELETE predicates, UPDATE assignments, DROP, and browse LIMIT.
- [ ] Run the focused tests and confirm missing functions.
- [ ] Implement deterministic SQL generation; reject identifiers outside the current lexer grammar instead of inventing quoted identifiers.
- [ ] Run focused tests and compiler regression tests.
- [ ] Commit with `feat(gui): generate SQL for graphical operations`.

### Task 3: Serialized database worker and controller

**Files:**
- Create: `database_system/gui/worker.py`
- Create: `database_system/gui/controller.py`
- Test: `tests/test_gui_controller.py`

**Interfaces:**
- Produces: queued execute/open/refresh/close requests, `GuiController` busy state, callbacks, and safe shutdown.
- Consumes: `DatabaseService` and SQL builder functions from Tasks 1-2.

- [ ] Write failing tests using a fake service for serial execution, busy rejection, result delivery, directory switching rollback, and close ordering.
- [ ] Run focused tests and confirm failure.
- [ ] Implement one daemon worker, request/response queues, and a controller that never touches Tk objects from the worker thread.
- [ ] Run controller and service tests.
- [ ] Commit with `feat(gui): add serialized GUI controller`.

### Task 4: Tkinter lightweight DataGrip interface

**Files:**
- Create: `database_system/gui/app.py`
- Create: `database_system/gui/dialogs.py`
- Create: `database_system/gui/__main__.py`
- Create: `start_gui.ps1`
- Test: `tests/test_gui_app.py`

**Interfaces:**
- Produces: `MiniSQLApp`, create-table and row-edit dialogs, `python -m database_system.gui`, and `start_gui.ps1`.
- Consumes: `GuiController`, schema snapshots, execution results, and SQL builder functions.

- [ ] Write headless-safe tests for widget construction with injected controller, action-to-SQL wiring, result-table population, plan tabs, error highlighting, and UPDATE-disabled state.
- [ ] Run focused tests and confirm failure.
- [ ] Implement the SQL Studio layout, object-tree context menu, multi-console notebook, data grid actions, confirmations, plan/message tabs, keyboard shortcut, status bar, and shutdown flow.
- [ ] Run GUI tests; manually launch the window and exercise CREATE/INSERT/SELECT/DELETE/DROP/LIMIT plus error display.
- [ ] Commit with `feat(gui): add Tkinter database manager`.

### Task 5: Documentation and full verification

**Files:**
- Modify: `README.md`
- Modify: `docs/PROJECT_CONTEXT.md`
- Test: `tests/test_gui_service.py`, `tests/test_gui_sql_builder.py`, `tests/test_gui_controller.py`, `tests/test_gui_app.py`, full `tests/`.

**Interfaces:**
- Produces: launch instructions and an acceptance demo script.
- Consumes: the completed GUI entry point.

- [ ] Add one-command Windows launch instructions and a short classroom demo sequence.
- [ ] Run all GUI tests, role-A compiler tests, then `python -m pytest tests -q`.
- [ ] Run `git diff --check` and verify no temporary data or GUI state is tracked.
- [ ] Update `docs/PROJECT_CONTEXT.md` with files, behavior, test counts, limitations, and next steps.
- [ ] Commit with `docs: document MiniSQL desktop GUI`.

