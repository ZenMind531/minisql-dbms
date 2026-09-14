# Task 2 Report: Durable CREATE and rollback

## Status

DONE

## Requirements delivered

- Added `CatalogManager.create_table(schema, catalog)` with the required order:
  create the table file, durably register catalog rows, then publish the schema
  to the in-memory Catalog.
- If `register_table` raises, the exact newly created user-table file is closed
  and removed, the original exception is re-raised, and the in-memory Catalog is
  not modified. Failure to clean up is attached as an exception note without
  hiding the registration failure.
- `StorageEngine.create_table` rejects any existing target path instead of
  allowing `FileManager` to open or truncate it.
- Added `StorageEngine.remove_table(table)` for CREATE rollback and protected
  `__catalog__` from removal.
- `MiniDB` now loads its Catalog through `CatalogManager` on startup and injects
  that manager into Executor.
- `Executor(engine, catalog, catalog_manager=None)` preserves the existing
  two-argument construction path; CREATE is durable when the manager is supplied.
- Catalog row format and INT/VARCHAR encoding are unchanged. No compiler AST,
  Token, grammar, page layout, or buffer policy was modified.

## TDD evidence

### RED

Command:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_engine.py -k "minidb_create_survives or rolls_back_only or storage_create_rejects or storage_remove_rejects or two_argument" -v
```

Observed: 4 failed, 1 passed. Failures were the intended missing behaviors:

- restarted MiniDB raised `SemanticError` because its Catalog was empty;
- `CatalogManager.create_table` did not exist;
- duplicate storage creation did not raise;
- `StorageEngine.remove_table` did not exist.

The compatibility test passed immediately because it characterizes the existing
two-argument constructor that the change must preserve.

### GREEN

The same focused command after the minimal implementation reported:

```text
5 passed, 18 deselected in 0.08s
```

The complete engine suite reported:

```text
23 passed in 0.14s
```

The full regression suite reported:

```text
203 passed, 162 subtests passed in 0.83s
```

## Files changed

- `database_system/engine/catalog_manager.py`
- `database_system/engine/storage_engine.py`
- `database_system/engine/executor.py`
- `database_system/engine/minidb.py`
- `tests/test_engine.py`
- `docs/PROJECT_CONTEXT.md`
- `.superpowers/sdd/2026-09-10-catalog-persistence/task-2-report.md`

## Self-review

- Verified rollback targets the schema name passed to this CREATE and cannot
  delete the protected catalog table.
- Verified disk metadata is flushed by the existing `register_table` before the
  in-memory Catalog is updated.
- Verified duplicate table-file creation checks the path before `_open`, so an
  existing valid, truncated, or otherwise non-table path is not overwritten.
- Verified the optional manager avoids a runtime import cycle via `TYPE_CHECKING`.
- Mutation check: removing startup load breaks restart; removing rollback breaks
  the `broken.dat` assertion; dropping either protection breaks its focused test;
  removing the optional default breaks the compatibility test.

## Concerns

None for the scoped requirements.

## Fix round 1: partial catalog-row rollback

Review identified that `register_table` writes one row at a time, while the
initial rollback removed only the user table file. A failure after the first
row could therefore leave a durable partial schema that made the next startup
fail.

### RED

Command:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_engine.py -k "partial_catalog_rows or registration_and_cleanup_failures or two_argument" -v
```

Observed:

```text
2 failed, 1 passed, 22 deselected in 0.24s
```

- After an injected failure on the second `__catalog__` insertion, scanning the
  catalog still returned `('broken', 'id', 'INT', 0)`.
- When catalog cleanup was injected to fail, the raised error contained only
  `registration failed`, losing the cleanup context.
- The strengthened legacy test already passed and now executes CREATE through
  `Executor(engine, catalog)` rather than only inspecting constructor state.

### GREEN

After adding exact-table catalog-row deletion, an explicit flush, continued
user-file cleanup, and combined structured diagnostics, the same command
reported:

```text
3 passed, 22 deselected in 0.10s
```

The complete engine suite reported:

```text
25 passed in 0.27s
```

The full regression command and result were:

```powershell
.\.venv\Scripts\python.exe -m pytest tests -v
```

```text
205 passed, 162 subtests passed in 0.77s
```

The new restart assertion constructs a new `MiniDB` after the injected partial
write and verifies that startup succeeds with no `broken` schema or catalog row,
while a pre-existing `stable` table and its exact catalog row remain intact.
