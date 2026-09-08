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
