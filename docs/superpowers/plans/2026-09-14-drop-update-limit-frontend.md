# DROP TABLE、UPDATE、LIMIT Frontend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add member A's tested Lexer, AST, and Parser support for `DROP TABLE`, `UPDATE`, and `LIMIT`, with synchronized frontend documentation.

**Architecture:** Extend the existing keyword set and recursive-descent statement dispatch while reusing the expression parser. Represent the syntax with source-positioned dataclasses and an optional `LimitClause` on `SelectStmt`; stop at the AST boundary so B/C/D implementation files remain unchanged.

**Tech Stack:** Python 3.11 standard library, dataclasses, unittest tests executed by pytest.

**Spec:** `docs/superpowers/specs/2026-09-14-drop-update-limit-frontend-design.md`

## Global Constraints

- Follow `.specify/memory/constitution.md`, frozen contracts, approved specification, task plan, and `AGENTS.md` in that order.
- Modify only member A frontend files, frontend tests, and synchronized documentation.
- Do not modify Semantic, Catalog, Planner, Optimizer, Engine, Storage, CLI internals, or frozen contracts.
- Preserve 1-based source positions and structured `ParseError` behavior.
- Use Red-Green-Refactor and keep grammar, AST, Parser, tests, and status documents consistent.

---

### Task 1: Recognize the four new keywords

**Files:**
- Modify: `tests/test_lexer.py`
- Modify: `database_system/sql_compiler/lexer.py`

**Interfaces:**
- Consumes: `Lexer(source).tokenize()` and `TokenType.KEYWORD`.
- Produces: case-insensitive keyword tokens for `DROP`, `UPDATE`, `SET`, and `LIMIT`, preserving source lexemes.

- [ ] **Step 1: Write the failing Lexer test**

Extend `test_recognizes_every_supported_keyword_case_insensitively`:

```python
source = (
    "select FROM where CREATE table INSERT into VALUES delete "
    "and OR not int varchar show databases tables order by asc desc "
    "drop UPDATE set limit"
)
tokens = Lexer(source).tokenize()
self.assertTrue(all(token.type is TokenType.KEYWORD for token in tokens[:-1]))
self.assertEqual(tokens[-2].lexeme, "limit")
```

- [ ] **Step 2: Verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_lexer.py::LexerBasicTests::test_recognizes_every_supported_keyword_case_insensitively -q
```

Expected: FAIL because the four words are identifiers.

- [ ] **Step 3: Implement the keywords**

Add to `KEYWORDS`:

```python
"DROP",
"UPDATE",
"SET",
"LIMIT",
```

- [ ] **Step 4: Verify GREEN**

Run Step 2 again. Expected: PASS.

---

### Task 2: Define the AST contract

**Files:**
- Modify: `tests/test_ast_nodes.py`
- Modify: `database_system/sql_compiler/ast_nodes.py`

**Interfaces:**
- Consumes: existing `ASTNode`, `Expr`, and `SelectStmt` conventions.
- Produces: `DropTableStmt`, `Assignment`, `UpdateStmt`, `LimitClause`, `SelectStmt.limit`, and updated exports.

- [ ] **Step 1: Write failing AST tests**

Import the AST module as `ast_nodes` (so collection succeeds before the classes exist), then add:

```python
def test_drop_update_and_limit_nodes_preserve_frontend_structure(self) -> None:
    self.assertTrue(hasattr(ast_nodes, "Assignment"))
    self.assertTrue(hasattr(ast_nodes, "DropTableStmt"))
    self.assertTrue(hasattr(ast_nodes, "UpdateStmt"))
    self.assertTrue(hasattr(ast_nodes, "LimitClause"))
    Assignment = ast_nodes.Assignment
    DropTableStmt = ast_nodes.DropTableStmt
    UpdateStmt = ast_nodes.UpdateStmt
    LimitClause = ast_nodes.LimitClause
    one = LiteralExpr(line=2, column=26, value=1,
                      literal_kind=LiteralKind.INTEGER)
    assignment = Assignment(line=2, column=20,
                            column_name="age", value=one)
    drop = DropTableStmt(line=1, column=1, table="student")
    update = UpdateStmt(line=2, column=1, table="student",
                        assignments=[assignment], where=None)
    limit = LimitClause(line=3, column=23, count=0)
    select = SelectStmt(line=3, column=1, columns=None, table="student",
                        where=None, limit=limit)
    self.assertEqual(drop.table, "student")
    self.assertEqual(update.assignments, [assignment])
    self.assertIs(select.limit, limit)
    self.assertEqual((limit.line, limit.column, limit.count), (3, 23, 0))

def test_update_requires_assignment_and_limit_rejects_negative_count(self) -> None:
    UpdateStmt = ast_nodes.UpdateStmt
    LimitClause = ast_nodes.LimitClause
    with self.assertRaisesRegex(ValueError, "at least one assignment"):
        UpdateStmt(line=1, column=1, table="student",
                   assignments=[], where=None)
    with self.assertRaisesRegex(ValueError, "non-negative"):
        LimitClause(line=1, column=23, count=-1)
```

- [ ] **Step 2: Verify RED**

Run `python -m pytest tests/test_ast_nodes.py -q` with the repository venv.
Expected: FAIL at the first `hasattr` assertion because the classes do not exist.

- [ ] **Step 3: Implement the AST classes**

Add:

```python
@dataclass(slots=True, kw_only=True)
class Assignment(ASTNode):
    column_name: str
    value: Expr

@dataclass(slots=True, kw_only=True)
class LimitClause(ASTNode):
    count: int
    def __post_init__(self) -> None:
        ASTNode.__post_init__(self)
        if self.count < 0:
            raise ValueError("LIMIT count must be non-negative")

@dataclass(slots=True, kw_only=True)
class DropTableStmt(ASTNode):
    table: str

@dataclass(slots=True, kw_only=True)
class UpdateStmt(ASTNode):
    table: str
    assignments: list[Assignment]
    where: Expr | None
    def __post_init__(self) -> None:
        ASTNode.__post_init__(self)
        if not self.assignments:
            raise ValueError("UPDATE requires at least one assignment")
```

Add `limit: LimitClause | None = None` after `SelectStmt.order_by`. Extend `Stmt` with the two statement types and export all four classes in `__all__`.

- [ ] **Step 4: Verify GREEN**

Run the AST test command again. Expected: PASS.

---

### Task 3: Parse DROP TABLE and UPDATE

**Files:**
- Modify: `tests/test_parser.py`
- Modify: `database_system/sql_compiler/parser.py`

**Interfaces:**
- Consumes: the new AST classes and existing expression parser.
- Produces: source-positioned DROP/UPDATE AST with one or more assignments and optional WHERE.

- [ ] **Step 1: Write failing normal-path and malformed-syntax tests**

Add imports and these behaviors:

```python
def test_parses_drop_table_and_update_assignments(self) -> None:
    drop, update = parse(
        "DROP TABLE student;"
        "UPDATE student SET name = 'Alice', age = age + 1 WHERE id = 7;"
    )
    self.assertIsInstance(drop, DropTableStmt)
    self.assertEqual((drop.table, drop.line, drop.column), ("student", 1, 1))
    self.assertIsInstance(update, UpdateStmt)
    self.assertEqual([a.column_name for a in update.assignments],
                     ["name", "age"])
    self.assertEqual(update.assignments[0].value.value, "Alice")
    self.assertEqual(update.assignments[1].value.op, BinaryOperator.ADD)
    self.assertIsInstance(update.where, BinaryExpr)

def test_update_where_is_optional(self) -> None:
    statement = parse("UPDATE student SET age = 20;")[0]
    self.assertIsInstance(statement, UpdateStmt)
    self.assertIsNone(statement.where)

def test_drop_and_update_report_precise_missing_parts(self) -> None:
    invalid = [
        ("DROP student;", "TABLE"),
        ("DROP TABLE;", "IDENTIFIER"),
        ("UPDATE student age = 1;", "SET"),
        ("UPDATE student SET;", "IDENTIFIER"),
        ("UPDATE student SET age 1;", "="),
        ("UPDATE student SET age =;", "expression"),
        ("UPDATE student SET age = 1,;", "IDENTIFIER"),
    ]
    for source, expected in invalid:
        with self.subTest(source=source):
            self.assert_parse_error(source, expected)
```

- [ ] **Step 2: Verify RED**

Run the three test node IDs. Expected: FAIL because dispatch rejects DROP/UPDATE.

- [ ] **Step 3: Implement parsing**

Import `Assignment`, `DropTableStmt`, and `UpdateStmt`; add DROP/UPDATE branches to `_parse_statement` and its expected set. Implement:

```python
def _parse_drop_table(self) -> DropTableStmt:
    start = self._consume_keyword("DROP")
    self._consume_keyword("TABLE")
    table = self._consume_identifier()
    return DropTableStmt(line=start.line, column=start.column,
                         table=table.lexeme)

def _parse_update(self) -> UpdateStmt:
    start = self._consume_keyword("UPDATE")
    table = self._consume_identifier()
    self._consume_keyword("SET")
    assignments = [self._parse_assignment()]
    while self._match_lexeme(","):
        assignments.append(self._parse_assignment())
    where = self._parse_expression() if self._match_keyword("WHERE") else None
    return UpdateStmt(line=start.line, column=start.column,
                      table=table.lexeme, assignments=assignments, where=where)

def _parse_assignment(self) -> Assignment:
    column = self._consume_identifier()
    self._consume_lexeme("=", {"="})
    value = self._parse_expression()
    return Assignment(line=column.line, column=column.column,
                      column_name=column.lexeme, value=value)
```

- [ ] **Step 4: Verify GREEN**

Run the three test node IDs again. Expected: PASS. If an error case differs, make only the smallest Parser correction; do not weaken the expected token.

---

### Task 4: Parse SELECT LIMIT

**Files:**
- Modify: `tests/test_parser.py`
- Modify: `database_system/sql_compiler/parser.py`

**Interfaces:**
- Consumes: `LimitClause` and `_is_integer_literal`.
- Produces: optional non-negative integer limit parsed after optional ORDER BY.

- [ ] **Step 1: Write failing normal-path and malformed-syntax tests**

```python
def test_parses_limit_after_optional_order_by(self) -> None:
    zero = parse("SELECT * FROM student LIMIT 0;")[0]
    ordered = parse(
        "SELECT name FROM student ORDER BY age DESC LIMIT 10;"
    )[0]
    self.assertEqual(zero.limit.count, 0)
    self.assertEqual((zero.limit.line, zero.limit.column), (1, 23))
    self.assertEqual(ordered.limit.count, 10)
    self.assertEqual(ordered.order_by[0].column_name, "age")
    self.assertTrue(ordered.order_by[0].descending)

def test_limit_rejects_missing_negative_float_and_wrong_clause_order(self) -> None:
    invalid = [
        ("SELECT * FROM student LIMIT;", "LIMIT"),
        ("SELECT * FROM student LIMIT -1;", "LIMIT"),
        ("SELECT * FROM student LIMIT 1.5;", "LIMIT"),
        ("SELECT * FROM student LIMIT age;", "LIMIT"),
        ("SELECT * FROM student LIMIT 1 ORDER BY id;", ";"),
    ]
    for source, expected in invalid:
        with self.subTest(source=source):
            self.assert_parse_error(source, expected)
```

- [ ] **Step 2: Verify RED**

Run both test nodes. Expected: FAIL because LIMIT remains unconsumed.

- [ ] **Step 3: Implement LIMIT parsing**

Import `LimitClause`, parse it after optional ORDER BY, pass it to `SelectStmt`, and add:

```python
def _parse_limit(self) -> LimitClause:
    start = self._consume_keyword("LIMIT")
    count = self._current()
    if not self._is_integer_literal(count):
        raise self._error(count, {"non-negative integer LIMIT"})
    self._advance()
    return LimitClause(line=start.line, column=start.column,
                       count=int(count.lexeme))
```

- [ ] **Step 4: Verify GREEN**

Run both test nodes again. Expected: PASS with structured `ParseError` for every malformed case.

- [ ] **Step 5: Run member A code tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_ast_nodes.py tests/test_lexer.py tests/test_parser.py -v
```

Expected: exit 0.

---

### Task 5: Synchronize documentation and project status

**Files:**
- Modify: `docs/grammar.md`
- Modify: `README.md`
- Modify: `docs/design.md`
- Modify: `specs/001-minisql-dbms/tasks.md`
- Modify: `docs/PROJECT_CONTEXT.md`

**Interfaces:**
- Consumes: implemented frontend behavior and fresh test evidence.
- Produces: consistent documentation that distinguishes frontend support from end-to-end execution.

- [ ] **Step 1: Update `docs/grammar.md`**

Add DROP and UPDATE statement productions, Assignment, optional LIMIT after ORDER BY, examples, four keywords, and Parser method mapping. Remove UPDATE/LIMIT from the frontend exclusion sentence and explicitly say B/D integration is pending.

- [ ] **Step 2: Update README and design docs**

Document syntax examples and this exact status distinction: Lexer/AST/Parser support is complete; Semantic/Planner/Executor support is pending, so MiniDB cannot yet execute these features end to end.

- [ ] **Step 3: Update tasks and project context**

Annotate T038 as “DROP/UPDATE/LIMIT A frontend complete; B/D pending” without checking the whole extension task. Set project context date to `2026-09-14`, record AST/grammar/test status, preserve the current end-to-end supported list, and add B/D integration plus full-team contract review to next steps.

- [ ] **Step 4: Verify documentation consistency**

Run:

```powershell
rg -n "DROP|UPDATE|LIMIT|DropTableStmt|UpdateStmt|LimitClause" docs README.md specs/001-minisql-dbms/tasks.md
git diff --check
```

Expected: all three features are documented without any end-to-end execution claim; diff check exits 0.

---

### Task 6: Final verification

**Files:**
- Verify only.

**Interfaces:**
- Consumes: Tasks 1–5.
- Produces: fresh evidence for member A completion and repository compatibility.

- [ ] **Step 1: Run required Lexer/Parser acceptance tests**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_lexer.py tests/test_parser.py -v
```

- [ ] **Step 2: Run all directly affected tests**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_ast_nodes.py tests/test_lexer.py tests/test_parser.py tests/test_show_order.py -q
```

- [ ] **Step 3: Run the complete suite**

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q
```

If B/D tests fail only because they exhaustively dispatch the expanded `Stmt` union, do not edit their modules; report the exact compatibility point.

- [ ] **Step 4: Check scope and formatting**

```powershell
git status --short
git diff --stat
git diff --check
```

Expected: only planned member A source/tests/docs changed; frozen contracts and B/C/D implementations remain untouched.
