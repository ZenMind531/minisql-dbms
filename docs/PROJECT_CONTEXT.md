# MiniSQL 项目上下文

> 最后更新：2026-09-08  
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
| `database_system/sql_compiler/lexer.py` | SQL 词法分析器 | 正常输入路径完成，错误路径待 B 的 LexError |
| `tests/test_ast_nodes.py` | AST 结构与约束测试 | 8 项通过 |
| `tests/test_lexer.py` | Lexer 行为测试 | 6 项通过，错误测试待补 |

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

- 统一 `LexError` 错误路径。
- 非法数字（例如 `12abc`、`.5`、`1.`）的正式错误。
- 非法字符、未闭合字符串和未闭合块注释的正式错误。

遇到尚未实现的字符时，当前 Lexer 会暂时抛出 `NotImplementedError`。这不是最终行为。

## 8. 测试状态

当前可运行：

```powershell
python -m unittest discover -s tests -v
```

最近一次验证结果：14 项测试通过，其中 AST 8 项、Lexer 6 项；`compileall` 通过。

项目最终测试入口仍应为：

```powershell
python -m pytest tests -v
```

当前开发环境未提供 pytest，因此现有基础测试暂用标准库 `unittest` 编写；pytest 可以发现并运行 unittest 测试。

## 9. 当前依赖与阻塞

- B 的 `database_system/utils/errors.py` 尚未出现在当前工作区。
- Lexer 最终错误必须使用 B 提供的 `LexError`，A 不应越界另建不兼容的错误类。
- Parser 错误必须使用 B 提供的 `ParseError`。
- AST 结构需要 B、D 最终确认后冻结。
- `.gitignore` 当前是用户已有的独立暂存改动，不应在角色 A 的提交中擅自包含、修改或撤销。
- 本地角色 A 的 `AGENTS.md` 被 `.git/info/exclude` 排除，不上传到共享仓库。

## 10. 下一步

角色 A 的推荐顺序：

1. B 完成 `LexError` 后补非法字符、非法数字、未闭合字符串和注释测试。
2. 全组冻结文法，B、D 冻结 AST。
3. 编写 `tests/test_parser.py`。
4. 实现递归下降 `parser.py`。
5. 与 B 联调 Token → AST → Semantic → Plan 流水线。

## 11. 上下文维护规则

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
