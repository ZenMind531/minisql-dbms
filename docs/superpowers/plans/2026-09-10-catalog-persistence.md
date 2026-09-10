# MiniSQL Catalog Persistence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist schemas in `__catalog__.dat`, restore data after restart, and complete engine/e2e acceptance evidence.

**Architecture:** A new `CatalogManager` bootstraps and scans the special catalog table through `StorageEngine`. `MiniDB` loads its in-memory Catalog through it, while Executor delegates durable CREATE orchestration to it without breaking the existing two-argument constructor.

**Tech Stack:** Python 3.11 standard library, existing page/buffer storage, pytest.

**Spec:** `docs/superpowers/specs/2026-09-10-catalog-persistence-design.md`

## Global Constraints

- Preserve catalog rows as `(table_name, col_name, col_type, col_order)`.
- Encode types only as `INT` or `VARCHAR(n)`, with `1 <= n <= 255`.
- Keep runtime dependencies standard-library-only and errors structured.
- Do not alter Token, AST, grammar, page layout, or buffer policies.
- Use Red-Green-Refactor and update `docs/PROJECT_CONTEXT.md`.

---

### Task 1: Catalog bootstrap, registration, and reload

**Files:**
- Create: `database_system/engine/catalog_manager.py`
- Create: `tests/test_engine.py`
- Modify: `database_system/engine/storage_engine.py`

**Interfaces:**
- Consumes: `StorageEngine.create_table/insert_row/scan/flush`, `Catalog.create_table`.
- Produces: `CatalogManager(engine)`, `load() -> Catalog`, `register_table(schema) -> None`, `CATALOG_SCHEMA`, and `StorageEngine.attach_table(schema)`.

- [ ] **Step 1: Write failing tests**

Add tests proving a fresh manager creates queryable `__catalog__`, registration writes rows `("student", "id", "INT", 0)` and `("student", "name", "VARCHAR(32)", 1)`, and reopening reconstructs the exact schema.

- [ ] **Step 2: Verify RED**

Run `.venv/Scripts/python.exe -m pytest tests/test_engine.py -v`.
Expected: import failure because `catalog_manager.py` does not exist.

- [ ] **Step 3: Implement minimal behavior**

Define fixed columns `table_name VARCHAR(255)`, `col_name VARCHAR(255)`, `col_type VARCHAR(16)`, `col_order INT`. Bootstrap without self-registration. Load by grouping exact table names, sorting zero-based column order, parsing types, validating each data file, registering schemas in Catalog, and attaching them to StorageEngine. Registration inserts one catalog row per column and flushes.

- [ ] **Step 4: Add validation tests and implementation**

Test and reject with `StorageError`: invalid type, duplicate/gapped order, duplicate column, and missing table file. Run each new test first to observe failure, then add the smallest validation.

- [ ] **Step 5: Verify and commit**

Run `.venv/Scripts/python.exe -m pytest tests/test_engine.py -v`, then commit the three Task 1 files as `feat(engine): persist and reload system catalog`.

### Task 2: Durable CREATE and rollback

**Files:**
- Modify: `database_system/engine/catalog_manager.py`
- Modify: `database_system/engine/storage_engine.py`
- Modify: `database_system/engine/executor.py`
- Modify: `database_system/engine/minidb.py`
- Test: `tests/test_engine.py`

**Interfaces:**
- Produces: `CatalogManager.create_table(schema, catalog)`, `StorageEngine.remove_table(table)`, and backward-compatible `Executor(engine, catalog, catalog_manager=None)`.

- [ ] **Step 1: Write and run failing tests**

Test CREATE + INSERT + close + new MiniDB + SELECT, and inject a failing `register_table` to prove only the newly created `broken.dat` is removed while `__catalog__.dat` and in-memory Catalog remain intact.

- [ ] **Step 2: Implement orchestration**

`create_table` performs storage creation, durable catalog registration, then memory registration. On registration failure it removes the exact new table file and re-raises. Storage creation rejects existing paths; removal rejects `__catalog__`. MiniDB loads CatalogManager at startup and Executor uses it when supplied.

- [ ] **Step 3: Verify regressions and commit**

Run `.venv/Scripts/python.exe -m pytest tests/test_engine.py tests/test_catalog.py tests/test_storage.py tests/test_buffer.py tests/test_cli.py -v`. Commit as `feat(engine): make create table durable and recoverable`.

### Task 3: End-to-end acceptance

**Files:**
- Create: `tests/test_e2e.py`
- Create: `tests/sql/demo_e2e.sql`
- Modify: `tests/test_cli.py`

**Interfaces:**
- Consumes: `MiniDB.execute/close` and CLI `main(argv)`.

- [ ] **Step 1: Add seven-statement demo**

Add CREATE, three INSERTs, filtered SELECT returning Alice, DELETE Alice, and final SELECT returning Bob and Tom.

- [ ] **Step 2: Write and run failing tests**

Test exact demo output, querying `__catalog__`, restart recovery, a 100-row insert/query/delete/restart scenario for SC-006, and continued use after a semantic error. Add a CLI test that executes the demo, then runs a second query script against the same data directory.

- [ ] **Step 3: Fix only exposed defects**

Keep fixes inside CatalogManager, MiniDB, Executor, or StorageEngine. Do not add SQL syntax.

- [ ] **Step 4: Verify and commit**

Run `.venv/Scripts/python.exe -m pytest tests/test_engine.py tests/test_e2e.py tests/test_cli.py -v`. Commit as `test(engine): add restart and end-to-end acceptance`.

### Task 4: Current documentation and final verification

**Files:**
- Modify: `docs/PROJECT_CONTEXT.md`
- Modify: `README.md`
- Modify: `specs/001-minisql-dbms/quickstart.md`
- Modify: `specs/001-minisql-dbms/tasks.md`

- [ ] **Step 1: Consolidate current state**

Replace accumulated historical appendices with one current implementation table, verified test counts, remaining limitations, and D-review notes. Remove obsolete Parser/Engine/pytest/CatalogManager blockers.

- [ ] **Step 2: Update runbook and task evidence**

Document Windows/Linux REPL, file, data-directory, compile-only, catalog query, demo, and restart commands. Mark only tasks backed by implementation and passing tests; leave review, report, rehearsal, and optional work unchecked.

- [ ] **Step 3: Run fresh final verification**

Run full pytest under Python 3.11, compileall, `start.ps1 --file tests/sql/demo_e2e.sql` against a fresh exact temp directory, `start.ps1 --help`, PowerShell syntax parsing, `bash -n install.sh start.sh` when available, and `git diff --check`.

- [ ] **Step 4: Commit docs**

Commit the four documentation files as `docs: finalize MiniSQL runbook and project status`.
