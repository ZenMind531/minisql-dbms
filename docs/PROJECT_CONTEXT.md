# MiniSQL 项目上下文

> 最后更新：2026-09-14
> 本文只记录当前事实。历史过程由 Git 追踪，不在此追加时间线。

## 1. 项目范围

MiniSQL 是使用 Python 3.11 标准库实现的教学型关系数据库，面向单用户、
单进程场景。当前支持：

- `CREATE TABLE`、`INSERT`、`SELECT`、`DELETE`；
- `SHOW DATABASES`、`SHOW TABLES`；
- `WHERE` 表达式与多列 `ORDER BY`；
- 4KB slotted page、LRU/FIFO 缓冲池和磁盘持久化；
- REPL、SQL 文件执行和 `--compile-only` 编译器演示。

`DROP TABLE`、`UPDATE`、`LIMIT` 当前只完成编译器前端，尚不能端到端执行。
`JOIN`、`GROUP BY`、事务、并发控制和索引不在当前范围。

## 2. 权威文档与优先级

1. `.specify/memory/constitution.md`：最高优先级的开发原则。
2. `specs/001-minisql-dbms/contracts/`：冻结的跨模块接口。
3. `specs/001-minisql-dbms/spec.md`：功能需求与验收标准。
4. `docs/grammar.md`：Lexer/Parser 支持语法的唯一准绳。
5. `specs/001-minisql-dbms/tasks.md`：任务状态、依赖与负责人。
6. 本文：当前实现、验证结果、阻塞和下一步。

`specs/001-minisql-dbms/plan.md`、`research.md`、`data-model.md` 和
`quickstart.md` 分别记录实施路线、技术决策、数据结构和验收命令。

## 3. 系统数据流

```text
SQL → Lexer → Token → Parser → AST
    → SemanticAnalyzer → Planner → Optimizer → Logical Plan
    → Executor → StorageEngine → BufferPool / FileManager / Page
```

`MiniDB` 负责顶层编排；`CatalogManager` 使用内部 `__catalog__` 表持久化模式，
启动时恢复用户表定义并连接已有数据文件。

## 4. 当前实现状态

### SQL 编译器

- Lexer 已支持全部关键字、标识符、整数、浮点数、字符串、运算符、分隔符、
  两类注释和精确位置；非法字符、非法数字及未闭合结构统一抛 `LexError`。
- 递归下降 Parser 已支持全部正式文法、多语句、空输入、表达式优先级和括号
  深度保护；错误统一抛包含实际 Token 与 expected 集合的 `ParseError`。
- AST、语义分析、Logical Plan、树形/JSON 输出和规则优化器均已接通。
- SHOW 和多列 ORDER BY 已贯通 Lexer、AST、Parser、Semantic、Planner、
  Optimizer 与 Executor；Sort 位于 Project 之前，可按未投影列排序。
- DROP TABLE、UPDATE、LIMIT 已完成成员 A 范围的关键字、AST、Parser 与前端
  测试。新增 `DropTableStmt`、`Assignment`、`UpdateStmt`、`LimitClause`，其中
  UPDATE 支持多列赋值和可选 WHERE，LIMIT 接受非负整数并位于 ORDER BY 后。
- `tests/sql/compiler_cases.json` 含 34 个正常、词法、语法和语义案例。

### 存储与引擎

- Page、FileManager、BufferPool 和跨进程持久化测试已完成（`tests/test_storage.py` 9 项、`tests/test_buffer.py` 5 项、`tests/test_storage_persist.py` 1 项）。
- 新增 `Page.update_row(slot, row)` 支持 UPDATE 写回：长度相同则原地覆盖（不额外占页空间），长度变化则退化为删除+插入，空间不足返回 `None`。
- 存储部分测试报告见 `docs/T036-storage-test-report.md`；DROP TABLE / UPDATE 的存储层评审与给 D 的操作顺序、失败补偿建议见 `docs/C-review-drop-update.md`。
- StorageEngine、Executor、MiniDB 与 CLI 已实现，支持交互、脚本、数据目录和
  编译器演示模式。
- CatalogManager 已实现 `__catalog__` bootstrap、模式恢复以及 CREATE 失败补偿；
  已存在的用户表通过 `attach_table()` 恢复，避免覆盖数据文件。
- `SHOW DATABASES` 当前显示所选数据目录名称；`SHOW TABLES` 按名称升序显示
  用户表并隐藏 `__catalog__`。

### 尚未完成的交付项

- `tests/test_e2e.py` 与 `tests/sql/demo_e2e.sql` 尚未创建，正式 T028/T034
  端到端验收仍未完成。
- SC-006 要求的“插入至少 100 行后删除并重启验证”尚未形成版本库测试。
- T036 整组测试报告、T037 实习报告和 T039 最终验收彩排尚未完成；存储模块的测试报告（`docs/T036-storage-test-report.md`）已产出。
- 契约冲突待评审：契约写“存储错误抛 `StorageError`”，但 `FileManager.read_page` 的越界/坏 magic 需抛 `ValueError` 才能被引擎正确包装（`tests/test_engine.py` 依赖此行为）。详见 `docs/C-review-drop-update.md` 第 4 节。
- SHOW / ORDER BY 是已实现扩展，但冻结的三份契约尚未同步这些新增节点；若要
  把扩展接口正式冻结，需要 B、C、D 与全组评审，成员 A 不单独改契约。
- DROP TABLE / UPDATE / LIMIT 尚待 B 完成语义与计划、D 完成执行与目录/存储
  集成；新增 AST 同样必须在端到端接入前由 B、D 与全组评审冻结。
- 当前旧 Planner 尚不读取 `SelectStmt.limit`，所以 LIMIT 虽能解析，但通过
  MiniDB 执行时可能被静默忽略；B 接入前不得将其视为有效的限行功能。

## 5. 关键设计决定

- 所有源码位置均为 1-based `line`、`column`。
- 关键字大小写不敏感；标识符与字符串内容保持原样。
- `VARCHAR(n)` 强制显式长度，`1 <= n <= 255`，按 UTF-8 字节数校验。
- 表达式优先级见 `docs/grammar.md`；FLOAT 可进入 AST，但在语义阶段拒绝。
- SELECT 计划为 `Project → Sort（可选）→ Filter（可选）→ SeqScan`；DELETE
  计划为 `Delete → Filter（可选）→ SeqScan`。
- 优化器深拷贝输入，执行常量折叠、布尔化简和冗余节点消除；恒假 Filter
  必须保留，除法采用向零截断且除零表达式不折叠。
- Page 固定 4096 字节、页头 32 字节；BufferPool 使用 `OrderedDict` 实现
  LRU/FIFO，并在淘汰或关闭前写回脏页。
- CREATE 顺序为“创建数据文件 → 持久化目录行 → 更新内存 Catalog”；失败时
  回滚本次创建的文件和目录记录。
- UPDATE 写回优先使用 `Page.update_row`：同长度原地覆盖；`delete_row` 不回收
  空间，反复“删除+插入”会使页提前判满。
- DROP TABLE 删除 `.dat` 前必须 `flush_all → close`（Windows 下文件被打开则
  无法删除），顺序为“存储层清理 → 删元数据 → 删文件”；失败时最多留下无害的
  孤儿文件，不会出现“元数据在、文件没了”。

## 6. 验证状态

2026-09-14 使用仓库 `.venv` 运行：

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q
```

结果：`220 passed, 171 subtests passed`（含 C 本轮新增的 4 个存储测试）。其中
成员 A 直接相关的 AST、Lexer、Parser、SHOW/ORDER BY 精简回归为
`47 passed, 24 subtests passed`。该结果覆盖当前已有测试，但不代表缺失的
T028/T034 和 SC-006 已完成。

## 7. 下一步

1. 先新增 `tests/test_e2e.py` 与 `tests/sql/demo_e2e.sql`，覆盖至少 100 行、
   条件查询、删除、关闭和重启恢复。
2. 用 quickstart 完成三阶段验收；T036 的存储部分报告已产出（`docs/T036-storage-test-report.md`），整组报告待收口。
3. 由 B/D 接入 DROP TABLE、UPDATE、LIMIT 的语义、计划与执行，再由全组统一
   评审 SHOW、ORDER BY 和三项新扩展的 AST/Plan 冻结契约。
4. 完成报告与最终彩排；必做项验收前不继续扩大 SQL 范围。

## 8. 维护规则

完成任务、修改接口或语法、改变测试状态、出现或解除阻塞后，同一轮更新本文。
只保留当前事实；删除失效描述，不追加按日期排列的开发日志。
