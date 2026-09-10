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

## 12. 当前状态补充（2026-09-08）

本节追加记录最近完成的工作；前文内容保持不变。若与前文的历史状态描述冲突，以本节和当前源码为准。

### 已新增或完成的文件

| 文件 | 当前作用 | 状态 |
|------|----------|------|
| `database_system/utils/errors.py` | 提供带 `type`、`line`、`column`、`message` 的 `SemanticError` | 已完成；其他统一错误类型仍待补充 |
| `database_system/sql_compiler/catalog.py` | 内存 Catalog，保存表、列顺序、列类型和 VARCHAR 长度 | T015 已完成 |
| `database_system/sql_compiler/semantic.py` | 表/列存在性、名字绑定、表达式类型、INSERT 和 VARCHAR UTF-8 长度检查 | T016 已完成 |
| `database_system/sql_compiler/planner.py` | 构造 CreateTable、Insert、Project、Filter、SeqScan、Delete 逻辑计划，并提供 JSON/树形输出 | T017 已完成 |
| `tests/test_catalog.py` | Catalog 的创建、查找、重复名称、类型和边界测试 | 13 项通过 |
| `tests/test_semantic.py` | 语义错误、表达式类型推导、列绑定、INSERT 和字符串长度测试 | 32 项通过 |
| `tests/test_planner.py` | 计划结构、JSON 序列化和优化行为的测试 | 已写；等待 Optimizer 实现后运行 |

### 已确认的实现决定

- Catalog 按表名和列名精确匹配，查找不到表或列时返回 `None`。
- Catalog 创建表时原子校验：重复表名、重复列名、空 schema、非 `INT`/`VARCHAR` 类型和不在 1–255 范围内的 VARCHAR 长度都会抛 `SemanticError`，失败不会登记半成品表。
- Catalog 保存和返回 schema/column 的副本，避免调用者通过修改可变 AST 节点改变已登记元数据。
- SemanticAnalyzer 将表达式类型写回 `Expr.resolved_type`，并在 `column_bindings` 中保存最近一次分析涉及的列定义。
- 算术运算只接受 `INT`；比较运算接受相同类型的 `INT` 或 `VARCHAR`；`AND`、`OR`、`NOT` 只接受 `BOOL`。FLOAT 字面量在语义阶段拒绝。
- VARCHAR 值按 `len(value.encode("utf-8"))` 校验字节数；空字符串合法，长度上限包含边界值。
- Planner 的 `plan_to_json` 使用稳定的 `type`、`table`、`columns`、`predicate`、`child`、`schema` 和 `rows` 字段；表达式 JSON 不包含源码位置或 `resolved_type`。
- Planner 的 SELECT 计划为 `Project -> Filter（可选）-> SeqScan`；DELETE 计划为 `Delete -> Filter（可选）-> SeqScan`。INSERT 按当前单行语法保存为一个 row。

### 最近测试状态

使用工作区提供的 Python 运行时执行标准库 unittest：AST 8 项、Lexer 6 项、Catalog 13 项、Semantic 32 项，共 59 项通过。`tests/test_planner.py` 当前因 `database_system/sql_compiler/optimizer.py` 尚未实现，在测试收集阶段导入失败；Optimizer 对应 T018，尚未开始实现。当前环境没有安装 pytest，最终入口仍为 `python -m pytest tests -v`。

### 下一步

1. 实现 T018 `optimizer.py`，使 `tests/test_planner.py` 中的常量折叠、布尔化简和冗余节点测试可运行。
2. 补齐 `LexError`、`ParseError` 等统一错误类型及 Parser，再接通 Lexer → Parser → SemanticAnalyzer → Planner 流水线。
3. 根据执行器需求评审并冻结 Logical Plan 的具体字段，随后继续引擎和存储阶段。

## 13. T018 状态补充（2026-09-09）

已完成 `database_system/sql_compiler/optimizer.py`。`Optimizer.optimize()` 对计划做深拷贝后递归应用三类规则：整数常量折叠（包括算术和比较）、`AND`/`OR` 的真假值化简，以及恒真 Filter 和 `Project(*)` 冗余节点消除。优化保留 Delete 的目标表和扫描子树，不增加计划节点数量；恒假 Filter 保留为恒假谓词以保持删除/筛选语义。

T012 的 18 项 Planner/Optimizer 测试全部通过；完整 unittest 回归共 77 项通过，`optimizer.py` 编译检查和 `git diff --check` 通过。当前工作区仍未安装 pytest。

下一项编译器工作是实现 Parser 并补齐统一 `LexError`、`ParseError` 路径，然后联调完整 SQL 文本到 Logical Plan 的流水线。

## 14. T019 状态补充（2026-09-09）

新增 `database_system/sql_compiler/demo.py`，提供 `render_compilation(tokens, statements, catalog)` 后端演示入口。它按顺序输出 Token 流、AST、语义检查结果、原始 Logical Plan 和优化后的 Logical Plan；语义错误会显示带位置的错误信息并继续处理后续语句，便于课堂演示成功与失败路径。

T019 的演示入口依赖 A 提供的 Token 列表和 Parser 产出的 AST，不负责词法或语法分析，也不执行磁盘读写。Planner、Optimizer 和 SemanticAnalyzer 分别复用现有实现。新增 `tests/test_demo.py` 覆盖完整成功流程和语义错误继续处理流程；完整 unittest 回归共 79 项通过。

## 15. C（存储）状态补充（2026-09-09）

已完成 Page / FileManager / BufferPool 及测试，存储模块（US2）可独立交付。测试入口：

```powershell
python -m pytest tests/test_storage.py tests/test_buffer.py -v
```

存储测试共 **10 项通过**（Python 3.11.9 + pytest）。

| 文件 | 作用 | 状态 |
|------|------|------|
| `database_system/utils/constants.py` | `PAGE_SIZE = 4096` | 完成（T007） |
| `database_system/utils/helpers.py` | 空占位 | 待组内确认内容 |
| `database_system/storage/page.py` | 4KB slotted page：页头 32B，槽数组(前)/行数据(尾)，insert/get/delete/rows/to_bytes/from_bytes | 完成（T021/T023） |
| `database_system/storage/file_manager.py` | 每表 `.dat`，页 0 文件头，allocate/free/read/write_page，空闲链表 | 完成（T024） |
| `database_system/storage/buffer.py` | LRU/FIFO 缓冲池（OrderedDict），pin/dirty、命中统计、logging | 完成（T022/T025） |
| `tests/test_storage.py` | Page 行为 + 文件读写/释放复用 | 6 项通过 |
| `tests/test_buffer.py` | LRU/FIFO 淘汰 / pin 保护 / 脏页写回 | 4 项通过 |

已确认的关键决定：
- 页头固定 32B：page_id(u32) / page_type(u8) / slot_count(u16) / free_start(u16) / free_end(u16)；每槽 4B = offset(u16)+length(u16)。
- FileManager 分配页时**直接写一个格式化好的空白数据页**——否则读回的新页 `free_end=0` 表现为“全满”，首次插行会失败；写空页同时保证释放页复用后旧数据不泄漏。
- BufferPool 用 `OrderedDict`：LRU 命中 `move_to_end`，FIFO 保持插入序；被 pin 的页不淘汰；所有帧都被 pin 时抛 `StorageError`；脏页在淘汰/退出前写回。
- 目前 `utils/errors.py` 还没有统一 `StorageError`，`buffer.py` 先做本地兜底定义；B 补上 `utils/errors.StorageError` 后即可改用统一类。
- 存储层只处理字节，不感知 INT/VARCHAR/FLOAT 语义；行序列化由 D 的 StorageEngine 负责。

C 下一步：
- [ ] T026 持久化验证：写入 → 杀进程 → 重启 → 读回一致。
- [ ] 与 D 的 StorageEngine 联调（FileManager/BufferPool 接口对接）。

## 16. C（存储）T026 补充（2026-09-09）

完成 T026 持久化验证：

- 新增 `tests/_persist_helper.py`（独立进程写库脚本）与 `tests/test_storage_persist.py`。
- 测试逻辑：进程 1 写入 2 页数据后退出 → 进程 2 用新的 `FileManager` 打开同一文件 → 按页号读回，行内容一致；同时验证页 0 文件头（page_count / free 链表）跨进程正确恢复。
- 结果：存储相关测试共 **11 项通过**（`python -m pytest tests/test_storage.py tests/test_buffer.py tests/test_storage_persist.py -v`，Python 3.11.9 + pytest）。

接口核对（对照 `contracts/storage-api.md`）：`Page` / `FileManager` / `BufferPool` 的方法名、参数、返回语义均已对齐；`BufferPool` 支持 LRU/FIFO、pin/dirty、stats 统计；错误先用本地 `StorageError` 兜底，等 B 在 `utils/errors.py` 补上统一类后自动切换。

**C 剩余项（依赖他人或收尾阶段，无法独立完成）**：
- [ ] `utils/helpers.py` 内容：等 B/D 说明需要哪些公共函数再填。
- [ ] 与 D 的 StorageEngine 联调：D 的 `engine/` 尚未开始（2026-09-09 尚无该目录），需等 D 提供实现后对接。
- [ ] T036 测试报告：最终集成并验收后整理。

## 17. A（编译器前端）完成状态（2026-09-09）

本节是组员 A 当前状态的最新事实；前文中“Parser 缺席”“Lexer 错误路径待补”
等历史描述均已失效。

- T009/T013：Lexer 已统一使用 `LexError` 报告非法字符、非法数字、未闭合
  字符串和未闭合块注释，错误位置指向非法词素或未闭合结构的起点。
- T010/T014：新增递归下降 `parser.py`，支持 CREATE TABLE、INSERT、SELECT、
  DELETE、多语句和空输入；表达式层级与 `docs/grammar.md` 一一对应，支持
  `NOT > 比较 > AND > OR`、算术优先级、左结合与括号。
- Parser 对语法错误统一抛 `ParseError`，消息包含 actual Token 与 expected
  集合；VARCHAR 长度必须是 1–255 的无符号整数。
- Parser 对括号嵌套设置安全上限，超深输入报告 `ParseError`，不会泄漏
  Python `RecursionError`。
- T019：真实 Lexer 和 Parser 已接入 `compile_sql`/`--compile-only`，示例
  `tests/sql/demo_compiler.sql` 可完整输出 Token、AST、语义检查、原始 Plan
  与优化 Plan。
- T020：`tests/sql/compiler_cases.json` 包含 34 个命名案例，覆盖正常、词法
  错误、语法错误和语义错误，并由 `tests/test_sql_cases.py` 自动验证。
- T035：新增根目录 `README.md` 和 `docs/design.md`，记录运行方式、Token、
  AST、递归下降层级和错误边界。

组员 A 相关新增测试为 Lexer 错误 6 项、Parser 16 项、SQL 案例集 3 项。
完整标准库 unittest 回归为 **165 项通过**。当前工作区 Python 运行时未安装
pytest，因此 `python -m pytest` 尚不能执行；unittest 用例兼容 pytest 收集。
使用固定随机种子 `20260909` 生成 10,000 条长度 0–80 的随机输入，Lexer 与
Parser 未出现 `LexError`/`ParseError` 以外的异常，意外崩溃数为 0。

仓库当前跟踪了部分 `__pycache__/*.pyc` 文件。执行测试会改变这些生成文件，
但它们不是源码变更，后续应由仓库维护者统一从版本控制中移除。

## 18. CLI 与 Python 3.11 环境补充（2026-09-10）

- `database_system/cli/main.py` 已支持无参数 REPL、`--file SQL_FILE`、
  `--data DIRECTORY`、`--compile-only SQL_FILE` 和 `--help`。批处理读取失败或
  SQL 诊断返回非零退出码且不打印 traceback。
- 新增 `tests/test_cli.py`，覆盖帮助、脚本执行、指定数据目录、编译模式不创建
  数据目录及文件读取错误，共 4 项。
- `StorageEngine.close()` 会先 flush 再关闭所有 `FileManager`，避免 CLI 退出后
  遗留文件句柄。该项及 `cli/main.py` 属成员 D 范围，需要 D 复核。
- 新增 Windows 的 `install.ps1` / `start.ps1` 和 Linux 的 `start.sh`；
  `install.sh` 固定检查 Python 3.11。README 与 quickstart 已补齐两个平台的
  安装、交互、脚本、编译和测试命令。
- 已在隔离的 CPython 3.11.16 + pytest 9.1.1 环境运行完整测试：
  **180 项测试、162 个 subtests 全部通过**。
- 当前仍未实现 CatalogManager，重启后恢复表结构仍是端到端验收阻塞；
  `tests/test_engine.py`、`tests/test_e2e.py` 和 `tests/sql/demo_e2e.sql` 仍待补。

## 19. 系统目录持久化与可恢复 CREATE（2026-09-10）

- `CatalogManager.load()` 已能 bootstrap 或加载 `__catalog__`，按
  `(table_name, col_name, col_type, col_order)` 重建内存 Catalog，并把已登记的
  用户表连接到新的 `StorageEngine` 实例。
- `CatalogManager.create_table(schema, catalog)` 固定按“创建用户表文件 → 持久化
  目录行 → 更新内存 Catalog”执行。目录登记失败时只关闭并删除本次新建的用户表
  文件，并按新表的精确名称删除、flush 已写入的目录行，不登记内存 schema；
  `StorageEngine.remove_table()` 明确禁止删除 `__catalog__`。若补偿清理自身失败，
  对外抛出的结构化 `StorageError` 同时保留原登记错误与清理错误上下文。
- `StorageEngine.create_table()` 不再打开或覆盖已存在的路径；恢复已有表必须使用
  `attach_table()`。`Executor(engine, catalog, catalog_manager=None)` 保持两参数调用
  兼容，提供 CatalogManager 时由其执行持久化 CREATE。
- `MiniDB` 启动时加载 CatalogManager，因此 CREATE + INSERT 后关闭并新建实例，
  SELECT 可恢复 schema 与数据。
- `tests/test_engine.py` 当前 25 项通过；完整 pytest 回归为 **205 项测试、162 个
  subtests 全部通过**（CPython 3.11.16 + pytest 9.1.1）。

下一步引擎工作是补齐 `tests/test_e2e.py` 与 `tests/sql/demo_e2e.sql`，完成
quickstart 的百行插入、条件查询、删除和再次重启验收。
