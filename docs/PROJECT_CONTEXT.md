# MiniSQL 项目上下文

> 最后更新：2026-09-09  
> 用途：帮助新成员、新对话和其他 Agent 快速了解项目。开始工作前先读本文；完成有意义的代码、接口或决策变更后同步更新本文。

## 1. 项目目标

本项目是使用 Python 3.11 编写的教学型关系数据库，支持：

- `CREATE TABLE`
- `INSERT`
- `SELECT`（含 WHERE）
- `DELETE`
- 固定 4KB 页、LRU/FIFO 缓冲池和磁盘持久化
- REPL、SQL 文件执行和编译器演示模式

项目只考虑单用户、单进程场景。UPDATE、JOIN、ORDER BY、GROUP BY、索引、事务和并发控制不属于当前必做范围。

## 2. 首次阅读顺序

1. `.specify/memory/constitution.md`：最高优先级的开发原则。
2. `specs/001-minisql-dbms/spec.md`：功能需求与验收标准。
3. `specs/001-minisql-dbms/contracts/`：模块间冻结接口。
4. `specs/001-minisql-dbms/tasks.md`：任务编号、依赖和负责人。
5. 本文：当前实现状态、已确认决策和下一步。
6. 与当前任务直接相关的源码与测试。

若文档冲突，优先级为：宪章、冻结契约、批准后的规格、计划与任务清单、本文。

## 3. 系统数据流

```text
SQL 字符串
   ↓ A：Lexer
Token 列表（含行列号和 EOF）
   ↓ A：Parser
AST
   ↓ B：SemanticAnalyzer
完成名字绑定和类型检查的 AST
   ↓ B：Planner / Optimizer
Logical Plan
   ↓ D：Executor / MiniDB
行数据与执行结果
   ↓ C + D：Buffer / Page / FileManager / StorageEngine
内存页和磁盘文件
```

任何模块不得直接访问其他模块的内部数据结构，只能通过 `contracts/` 中的接口通信。

## 4. 团队分工

| 成员 | 负责范围 |
|------|----------|
| A | 文法、Token、AST、Lexer、Parser 及对应测试 |
| B | 统一错误、Catalog、语义分析、Planner、Optimizer |
| C | Page、FileManager、BufferPool、缓存测试与持久化验证 |
| D | StorageEngine、CatalogManager、Executor、MiniDB、CLI 和集成 |

跨模块接口变更必须先与对应负责人确认。Token 和 AST 的结构变更至少需要 B、D 评审；冻结契约变更需要全组评审。

## 5. 当前文件

| 文件 | 作用 | 状态 |
|------|------|------|
| `docs/grammar.md` | SQL 子集的唯一文法准绳 | 已完成初稿，待全组冻结 |
| `database_system/sql_compiler/ast_nodes.py` | AST、类型和运算符节点 | 已完成草案，待 B、D 最终确认 |
| `database_system/sql_compiler/lexer.py` | SQL 词法分析器 | 正常输入路径完成；错误路径待 A 接入 `LexError` |
| `database_system/sql_compiler/parser.py` | 递归下降语法分析器 | **尚未创建**（T014，A），阻塞完整流水线 |
| `database_system/utils/errors.py` | 统一错误：`MiniSQLError` 基类 + `LexError`/`ParseError`/`SemanticError`/`StorageError`/`ExecError` | T006 已完成 |
| `database_system/sql_compiler/catalog.py` | 内存 Catalog，保存表、列顺序、列类型和 VARCHAR 长度 | T015 已完成 |
| `database_system/sql_compiler/semantic.py` | 表/列存在性、名字绑定、表达式类型、INSERT 和 VARCHAR UTF-8 长度检查 | T016 已完成 |
| `database_system/sql_compiler/planner.py` | 构造 CreateTable、Insert、Project、Filter、SeqScan、Delete 逻辑计划，并提供 JSON/树形输出 | T017 已完成 |
| `database_system/sql_compiler/optimizer.py` | 常量折叠、布尔化简、冗余节点消除 | T018 已完成 |
| `database_system/sql_compiler/demo.py` | `compile_sql()` 流水线与 `--compile-only` 命令行；`render_compilation()` 后端演示 | T019 部分完成，等待 A 的 Parser |
| `tests/test_ast_nodes.py` | AST 结构与约束测试 | 8 项通过 |
| `tests/test_lexer.py` | Lexer 行为测试 | 6 项通过，错误测试待补 |
| `tests/test_errors.py` | 五类统一错误的字段、层次与兼容性测试 | 15 项通过 |
| `tests/test_catalog.py` | Catalog 的创建、查找、重复名称、类型和边界测试 | 13 项通过 |
| `tests/test_semantic.py` | 语义错误、表达式类型推导、列绑定、INSERT 和字符串长度测试 | 32 项通过 |
| `tests/test_planner.py` | 计划结构、JSON 序列化、优化规则、恒假谓词与折叠安全性测试 | 47 项通过 |
| `tests/test_demo.py` | 后端演示、完整流水线与 `--compile-only` 命令行测试 | 19 项通过 |

## 6. 已确认的设计决定

### 文法

- 每条语句必须以 `;` 结束；允许多语句输入。
- WHERE 表达式满足 `NOT > 比较 > AND > OR`，算术运算优先级更高。
- `VARCHAR` 必须写为 `VARCHAR(n)`，其中 `1 <= n <= 255`。
- 关键字大小写不敏感；标识符和字符串内容保留原样。
- 字符串使用单引号，`''` 表示字符串中的一个单引号。

### AST

- 所有 AST 节点直接保存 1-based `line` 和 `column`。
- AST 使用 Python 3.11 `dataclass`，表达式的 `resolved_type` 由 B 的语义分析回填。
- `-12` 表示为 `UnaryExpr(MINUS, LiteralExpr(12))`。
- 运算符使用统一的字符串枚举，例如 `NOT`、`-`、`AND`。
- `InsertStmt.columns` 表示可选目标列；`None` 表示省略列名列表。该名称与
  `data-model.md` 保持一致。
- `SelectStmt.columns=None` 唯一表示 `SELECT *`；非空列表表示明确列名。
- `TypeSpec` 自身保证 VARCHAR 长度为 1–255，INT/BOOL 不允许携带长度。
- `LiteralExpr.value` 必须与 INTEGER/FLOAT/STRING 字面量种类匹配；INTEGER
  明确排除 Python 的 bool。
- 复合表达式的 `line`、`column` 表示整个源码片段的起始位置；字符串 AST
  值不含外围引号，并把源码中的 `''` 解码为 `'`。
- FLOAT 字面量可以被 Lexer/Parser 识别并保存在 AST，但当前语义阶段必须报告“不支持 FLOAT 类型”；Executor 不实现浮点运算。
- BOOL 仅可作为表达式结果类型；表列只能使用 INT 或 VARCHAR。
- AST 与 Logical Plan 严格分离，`ast_nodes.py` 不包含 SeqScan、Filter 或 Project。

### 统一错误（T006）

- 所有阶段的诊断都继承 `MiniSQLError`，并暴露 `type`、`line`、`column`、`message` 四个属性。
- `type` 取自类名，`str(error)` 固定为 `"<Type> at <line>:<column>: <message>"`。
- `line`、`column` 与 AST 一致为 1-based，默认 `(1, 1)`；传入 0 或负数抛 `ValueError`。
- 契约文本里的 `reason` 作为 `message` 的别名同时支持：构造参数与只读属性都可用，两者同时给出且不一致时抛 `TypeError`。
- 存在公共基类的目的是让 CLI 写 `except MiniSQLError` 报告诊断，而 `TypeError`、`AttributeError` 等实现缺陷继续向上抛出。
- `SemanticError` 的既有调用方式（`SemanticError(msg)`、`SemanticError(msg, line=, column=)`）保持不变。

### Catalog 与语义分析

- Catalog 按表名和列名精确匹配，查找不到表或列时返回 `None`。
- Catalog 创建表时原子校验：重复表名、重复列名、空 schema、非 `INT`/`VARCHAR` 类型和不在 1–255 范围内的 VARCHAR 长度都会抛 `SemanticError`，失败不会登记半成品表。
- Catalog 保存和返回 schema/column 的副本，避免调用者通过修改可变 AST 节点改变已登记元数据。
- SemanticAnalyzer 将表达式类型写回 `Expr.resolved_type`，并在 `column_bindings` 中保存最近一次分析涉及的列定义。
- 算术运算只接受 `INT`；比较运算接受相同类型的 `INT` 或 `VARCHAR`；`AND`、`OR`、`NOT` 只接受 `BOOL`。FLOAT 字面量在语义阶段拒绝。
- VARCHAR 值按 `len(value.encode("utf-8"))` 校验字节数；空字符串合法，长度上限包含边界值。

### Logical Plan 与优化器

- `plan_to_json` 使用稳定的 `type`、`table`、`columns`、`predicate`、`child`、`schema` 和 `rows` 字段；表达式 JSON 不包含源码位置或 `resolved_type`。
- SELECT 计划为 `Project -> Filter（可选）-> SeqScan`；DELETE 计划为 `Delete -> Filter（可选）-> SeqScan`。INSERT 按当前单行语法保存为一个 row。
- `Optimizer.optimize()` 先深拷贝输入计划，调用方持有的计划永不被修改；优化自底向上单趟完成，且幂等。
- 三条规则：整数常量折叠（算术与比较）、`AND`/`OR` 布尔化简、冗余节点消除（恒真 Filter 与 `Project(*)`）。
- **恒假 Filter 必须保留。** `WHERE 1 = 2` 不选中任何行；删掉 Filter 会退化成全表扫描，使 SELECT 返回全部行、DELETE 删除全部行。冻结契约中没有表示“空结果”的计划节点，D 的 Executor 也不支持，因此保留恒假谓词是唯一保持语义等价的做法。
- **常量折叠不得抛异常。** 无法求值的表达式（`1 / 0`、混合类型比较、FLOAT 字面量、字符串算术）原样保留，交由 Executor 在运行期报告，符合宪章 II。
- 折叠布尔值的表示：AST 没有布尔字面量种类（`LiteralKind` 只有 INTEGER/FLOAT/STRING，且 `LiteralExpr` 明确排除 Python `bool`），因此真值统一编码为 INTEGER 字面量 `1` / `0`，并把 `resolved_type` 标为 `BOOL`。`literal_kind` 描述源码形态，`resolved_type` 描述语义类型；**只有 `resolved_type` 为 BOOL 的字面量才被当作常量谓词**，避免把折叠后的 INT（如 `age > 10 + 8` 中的 `18`）误判成真值而删除 Filter。
- **INT 除法向零截断**（`int(a / b)`，而非 Python 的 `//` 向下取整），且仅在除数非零时折叠。**D 的 Executor 必须采用同一约定**，否则优化前后对负数除法的结果会不一致。

### 待确认接口决定

- D 建议由 B 的 SemanticAnalyzer/Planner 把列名绑定为 tuple 列序号，使 Executor 只按下标取值、不在逐行执行时查询 Catalog。
- 该建议尚未写入 `compiler-api.md`，必须等待 B 确认 Plan 的具体表示后再决定是否修改冻结契约。

## 7. 当前 Lexer 能力

已经支持：

- 规格中声明的 14 个关键字。
- ASCII 标识符：字母或下划线开头，后续可含数字。
- 分隔符 `(`、`)`、`,`、`;`。
- 整数、浮点数和单引号字符串常量。
- 字符串中的 `''` 转义形式（Token 保留原始词素）。
- 运算符 `=`、`!=`、`>`、`>=`、`<`、`<=`、`+`、`-`、`*`、`/`，并采用最长匹配。
- `--` 单行注释和不嵌套的 `/* ... */` 多行注释。
- 空白、LF 和 Windows CRLF 的行列号更新。
- EOF Token。
- 保留关键字原始词素，同时以大小写不敏感方式识别关键字。

尚未支持：

- 非法数字（例如 `12abc`、`.5`、`1.`）的正式错误。
- 非法字符、未闭合字符串和未闭合块注释的正式错误。

遇到上述情况时，当前 Lexer 仍抛 `NotImplementedError`。`LexError` 已由 B 提供（见 §6），A 可以直接替换，不需要另建错误类。

## 8. 测试状态

当前可运行：

```powershell
python -m unittest discover -s tests -v
```

最近一次验证结果：**140 项全部通过**（AST 8、Lexer 6、Errors 15、Catalog 13、Semantic 32、Planner/Optimizer 47、Demo 19）；`python -m compileall database_system` 与 `git diff --check` 通过。

项目最终测试入口仍应为：

```powershell
python -m pytest tests -v
```

当前开发环境未安装 pytest，因此现有测试全部用标准库 `unittest` 编写；pytest 可以发现并运行 unittest 测试。

## 9. 编译器演示入口（T019，部分完成）

`database_system/sql_compiler/demo.py` 提供两个入口：

| 入口 | 作用 | 状态 |
|------|------|------|
| `render_compilation(tokens, statements, catalog)` | 只跑 B 的后端阶段：语义检查 → 原始 Plan → 优化 Plan | 可用 |
| `compile_sql(source, catalog=None)` | 完整流水线：SQL 文本 → Lexer → Parser → Semantic → Planner → Optimizer | Lexer 段可用，Parser 段待 A |
| `main(argv)` / `--compile-only` | 命令行入口，接受 SQL 文件或 `--sql "..."` | 可用 |

运行方式：

```powershell
python -m database_system.sql_compiler.demo --compile-only demo.sql
python -m database_system.sql_compiler.demo --compile-only --sql "SELECT name FROM student;"
```

已确认的实现决定：

- 只捕获 `LexError`、`ParseError`、`SemanticError` 并带位置报告；`TypeError`、`AttributeError`、Lexer 残留的 `NotImplementedError` 一律向上抛出。把实现缺陷伪装成语义错误会让现场 Debug 无法定位阶段。
- 单条语句的语义错误不会中断后续语句，一个演示脚本可同时展示成功与失败路径。
- `compile_sql` 会把演示脚本里的 `CREATE TABLE` 登记进演示用的内存 Catalog，使同一文件里后续的 `SELECT` 能解析。这只是演示便利，不执行语句、不做磁盘 I/O；表的持久化仍属于 D 的 CatalogManager。
- `compile_sql` 的 `lexer_factory` / `parser_factory` 参数用于在 A 的 Parser 缺席时驱动测试，生产调用不传，自动使用真实 Lexer 与 Parser。
- Parser 缺席时，流水线输出 Token 流后明确打印“语法分析阶段尚未接通（T014，负责人 A）”，不伪装成功。A 的 `parser.py` 落地后无需修改 demo。

因此 **T019 不能标记为完成**：B 侧的后端串接、命令行、错误分层与测试已完成，AST 与 Plan 阶段的实际演示依赖 A 的 T014。

## 10. 当前依赖与阻塞

- **已解除**：`LexError`、`ParseError` 等统一错误类型（T006）已交付，A 可以接入 Lexer 与 Parser 的错误路径。
- **进行中阻塞**：`parser.py`（T014，A）缺席，`compile_sql` 无法演示 AST 与 Logical Plan；T019 因此只能部分完成。
- AST 结构需要 B、D 最终确认后冻结。
- Logical Plan 字段与 INT 除法约定需要 D 在实现 Executor 前确认（见 §6）。
- `.gitignore` 当前是用户已有的独立暂存改动，不应在角色 A 的提交中擅自包含、修改或撤销。
- 本地角色 A 的 `AGENTS.md` 被 `.git/info/exclude` 排除，不上传到共享仓库。

## 11. 下一步

角色 A：

1. 用 `LexError` 替换 Lexer 中的 `NotImplementedError`，补非法字符、非法数字、未闭合字符串和注释测试。
2. 全组冻结文法，B、D 冻结 AST。
3. 编写 `tests/test_parser.py`，实现递归下降 `parser.py`（T014）。
4. 与 B 联调 `compile_sql`，把 T019 补完。

角色 B：

1. 等 Parser 就位后，补 `compile_sql` 的端到端测试（真实 Lexer + 真实 Parser）。
2. 与 D 评审并冻结 Logical Plan 字段表示与 INT 除法约定。

## 12. 上下文维护规则

完成以下任何事项时，必须同步更新本文：

- 新增或完成任务。
- 修改模块接口、AST、Token、Plan 或错误格式。
- 做出会影响其他成员的设计决定。
- 新增重要文件、测试入口或运行方式。
- 出现或解除阻塞。
- 测试数量或状态发生变化。

更新时只记录当前事实。删除已经失效的描述，不把聊天记录、大段代码或临时推测堆入本文。提交前确认本文与源码、测试和 `tasks.md` 一致。
