# Feature Specification: MiniSQL 教学数据库系统

**Feature Branch**: `001-minisql-dbms`
**Created**: 2026-09-07
**Status**: Approved
**Input**: User description: "《大型平台软件设计实习》实训项目：设计并实现一个教学用小型关系数据库系统，包含 SQL 编译器（词法/语法/语义分析、执行计划生成与优化）、页式存储系统（4KB 页、LRU/FIFO 缓存）和数据库引擎（执行器、存储引擎、系统目录、CLI），支持 CREATE TABLE / INSERT / SELECT / DELETE 四类语句，4 人小组协作完成。"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - SQL 编译器：从 SQL 文本到优化后的执行计划 (Priority: P1)

学生（或教师）向编译器输入一条或多条 SQL 文本，系统依次输出 Token 流、
AST、语义检查结果、逻辑执行计划与优化后的计划。合法 SQL 完整通过流水线；
非法 SQL 被准确拒绝并报告错误类型（词法/语法/语义）、行列号与原因。

**Why this priority**: 编译器是整个系统的第一阶段，其输出的 Logical Plan
直接驱动后续执行引擎；课程第一阶段验收只考编译器，先交付它即可独立成
为一个可演示的 MVP。

**Independent Test**: 不依赖任何存储/引擎代码，用测试 SQL 文件跑
`lexer → parser → semantic → planner → optimizer` 流水线，核对每个阶段的
输出结构与错误定位。

**Acceptance Scenarios**:

1. **Given** 输入 `CREATE TABLE student(id INT, name VARCHAR(32), age INT);`，
   **When** 运行编译器，**Then** 输出包含 5 类 Token 的 Token 流（带行列号）、
   CreateTableStmt AST，并通过语义检查、生成 CreateTable 计划。
2. **Given** 输入 `SELECT name FROM student WHERE age > 18 AND id != 3;`，
   **When** 运行编译器，**Then** AST 中 AND 为根、两个比较为子节点，
   计划为 `Project[name] → Filter[age>18 AND id!=3] → SeqScan[student]`。
3. **Given** 输入 `SELECT name FROM student WHERE age > 18 AND;`，
   **When** 运行编译器，**Then** 报告 SyntaxError，含出错 Token 的行列号、
   实际符号 `;` 与期望符号集合，程序不崩溃。
4. **Given** 输入 `SELECT score FROM student;`（score 列不存在），
   **When** 运行编译器，**Then** 报告 SemanticError：column 'score' does
   not exist in table 'student'。
5. **Given** 输入 `SELECT name FROM student WHERE 1=1 AND age > 10+8;`，
   **When** 启用优化，**Then** 优化后计划等价于 `Filter[age > 18]`，
   且能展示优化前后两棵计划树的结构差异。

---

### User Story 2 - 页式存储系统：页管理与缓存 (Priority: P2)

数据库模块通过存储接口申请、读、写、释放固定大小（4KB）的页；缓存层
以 LRU 或 FIFO 策略管理缓冲池，记录命中/未命中统计并写日志。

**Why this priority**: 存储系统为引擎提供数据访问接口，是第二阶段的独立
交付物；在引擎完成前即可用模拟读写负载单独验证正确性与缓存行为。

**Independent Test**: 直接用页管理 API 分配/写入/读回/释放页，断言数据
一致；用固定访问序列分别跑 LRU 与 FIFO，核对命中率统计与淘汰顺序。

**Acceptance Scenarios**:

1. **Given** 一个空数据文件，**When** 分配一页、写入 4KB 数据、按页号读回，
   **Then** 读回内容与写入完全一致。
2. **Given** 缓冲池容量为 N，**When** 依次访问超过 N 个不同页，
   **Then** 按所选策略（LRU/FIFO）淘汰正确的页，且命中统计数值正确。
3. **Given** 修改过的页（脏页）在缓存中，**When** 触发 flush 或程序正常退出，
   **Then** 数据落盘，重启进程后按页号仍能读出修改后的内容。
4. **Given** 释放一页后再次分配新页，**When** 分配策略复用空闲页，
   **Then** 旧数据不泄漏到新页，页分配记录一致。

---

### User Story 3 - 端到端小型数据库：CLI 执行四类 SQL (Priority: P3)

用户通过命令行 REPL 或 SQL 脚本文件，依次执行 CREATE TABLE、INSERT、
SELECT（含 WHERE）、DELETE，得到正确结果；数据持久化到磁盘，重启后
可继续查询。系统目录（表/列元数据）作为特殊表存储并可被查询。

**Why this priority**: 这是第三阶段完整系统交付，依赖前两个故事的全部
接口，风险最高、集成工作量最大，故排最后。

**Independent Test**: 跑 quickstart.md 中的端到端演示脚本（建表→插入→
条件查询→删除→再查询），核对每步输出；杀进程重启后再次 SELECT，
数据仍在。

**Acceptance Scenarios**:

1. **Given** 空数据库，**When** 执行 quickstart.md 的完整演示脚本，
   **Then** 建表成功、插入 3 行、条件查询只返回 Alice、删除 Alice 后全表查询
   返回 Bob 与 Tom，且每行包含 id/name/age 三列。
2. **Given** 已插入多行数据，**When** 执行
   `SELECT id, name FROM student WHERE age > 18 AND id != 3;`，
   **Then** 返回的列、行与 WHERE 条件完全一致（比较/AND/OR/NOT/括号
   语义正确）。
3. **Given** 已成功写入并 flush 的数据，**When** 退出 CLI 并重新启动，**Then** 再次 SELECT
   能看到之前插入的数据（持久化生效，元数据与数据均恢复）。
4. **Given** 用户输入不存在的表或不匹配的 INSERT 值，**When** 执行，
   **Then** CLI 显示语义错误信息（类型+位置+原因）并继续接受下一条命令。

---

### Edge Cases

- 空输入、纯注释输入、多条 SQL 混合输入：不崩溃，逐条处理。
- 未闭合字符串 `'Alice`、非法字符 `@`、非法数字：词法错误，精确定位。
- 关键字大小写混合 `SeLeCt`、字符串内 `''` 转义（`'Tom''s book'`）：正确处理。
- 极长标识符/超深括号嵌套：有明确上限或优雅报错，不崩溃。
- WHERE 中类型不匹配（`age + 'abc'`）：语义错误而非执行期崩溃。
- 缓冲池容量为 1 的极端配置：仍正确工作。
- 数据文件被删/损坏：启动时报清晰错误而非静默丢数据。

## Requirements *(mandatory)*

### Functional Requirements

**SQL 编译器（US1）**

- **FR-001**: 词法分析器 MUST 识别关键字（SELECT/FROM/WHERE/CREATE/TABLE/INSERT/INTO/VALUES/DELETE/AND/OR/NOT/INT/VARCHAR）、标识符、常量（整数、浮点、字符串）、运算符（= != > >= < <= + - * /）、分隔符（( ) , ;），并跳过空白与注释（`--` 单行、`/* */` 多行）。
- **FR-002**: 每个 Token MUST 携带类型、词素、行号、列号；关键字大小写不敏感，标识符与字符串内容保持原样。
- **FR-003**: 语法分析器 MUST 支持 CREATE TABLE / INSERT / SELECT / DELETE 四类语句并构造结构化 AST（语句节点 + 表达式节点），AST 节点保留源码位置；VARCHAR 列类型必须写为 `VARCHAR(n)`，其中 `1 <= n <= 255`。
- **FR-004**: WHERE 表达式 MUST 按 NOT > 比较 > AND > OR 的优先级构造 AST，括号可显式改变结合结构。
- **FR-005**: 系统 MUST 显式提交所支持的 SQL 子集文法（grammar.md），且 Parser 实现与文法一致。
- **FR-006**: 语义分析 MUST 完成：表存在性、列存在性、名字绑定（标识符→Catalog 列定义）、类型一致性检查、INSERT 列数/顺序/值类型匹配。
- **FR-007**: 类型规则 MUST 集中管理，至少覆盖 INT/VARCHAR/BOOL 的比较、算术与逻辑运算组合。
- **FR-008**: 计划生成器 MUST 把 AST 转换为逻辑执行计划，算子至少含 CreateTable / Insert / Delete / SeqScan / Filter / Project；Delete 节点持有目标表及可选过滤子计划。输出形式为树形、JSON 或 S-表达式之一且结构明确。
- **FR-009**: 优化器 MUST 实现至少 2 条规则式优化（如常量折叠、布尔化简、冗余节点消除），并能展示优化前后计划结构差异、保证语义等价。
- **FR-010**: 词法/语法/语义错误 MUST 输出"错误类型 + 行号 + 列号 + 原因"，语法错误应给出期望符号集合；任何非法输入不得导致崩溃。

**页式存储（US2）**

- **FR-011**: 存储层 MUST 以固定 4KB 页为磁盘 I/O 最小单位，提供页分配、释放、按页号读写的接口（read_page / write_page 语义）。
- **FR-012**: 缓存层 MUST 实现 LRU 与 FIFO 两种可切换的淘汰策略，提供 get_page / flush_page 语义，并统计命中率、记录缓存行为日志。
- **FR-013**: 脏页 MUST 在淘汰或显式 flush 时写回磁盘，保证进程重启后数据可读。
- **FR-013A**: 缓存层 MUST 提供 pin/unpin 生命周期和显式 dirty 标记；被 pin 的页不得淘汰，若无可淘汰帧则返回结构化 StorageError。

**数据库引擎（US3）**

- **FR-014**: 执行引擎 MUST 支持 CreateTable / Insert / SeqScan / Filter / Project 算子的实际执行，结果与 Logical Plan 语义一致。
- **FR-015**: 存储引擎 MUST 实现行与页的映射（行序列化/反序列化、页内组织）与磁盘文件组织。
- **FR-016**: 系统目录 MUST 维护表/列元数据，并作为特殊表存储、可查询。
- **FR-016A**: 首次启动 MUST 先以专用 bootstrap 流程创建 `__catalog__`，不递归登记自身；普通表由 StorageEngine 创建数据文件后，再由 CatalogManager 登记并更新内存 Catalog。
- **FR-017**: CLI MUST 支持交互式 REPL 与执行 SQL 脚本文件两种模式，逐条显示结果或错误，单条语句失败不影响后续语句。

### Key Entities

- **Token**: 词法单元；属性：类型、词素、行号、列号。
- **AST 节点**: 语句节点（CreateTableStmt/InsertStmt/SelectStmt/DeleteStmt）与表达式节点（BinaryExpr/UnaryExpr/IdentifierExpr/LiteralExpr）；携带源码位置。
- **Catalog（系统目录）**: 模式元数据；表 → 列名/类型 的映射，支持 create_table/find_table/find_column/get_type。
- **Logical Plan 节点**: CreateTable/Insert/Delete/SeqScan/Filter/Project；仅保存执行所需信息。
- **Page**: 4KB 固定大小；页号、页头、行数据、槽、空闲空间。
- **Row（记录）**: 按表模式序列化的字节序列，映射到页内槽位。

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: `tests/sql/` 中覆盖四类语句及全部已声明语法分支的合法用例 100% 通过"词法→语法→语义→计划"完整流水线，输出结构正确。
- **SC-002**: 使用固定随机种子生成至少 10,000 条非法/随机输入时程序崩溃次数为 0；每个错误均归类到词法/语法/语义之一且具有有效行列号。
- **SC-003**: 纳入版本库的正常、错误、边界、集成与端到端测试必须 100% 通过；教师隐藏测试结果另行记录。
- **SC-004**: 优化规则前后对同一查询的执行结果完全一致（语义等价），且优化后计划节点数不增加。
- **SC-005**: 缓存测试序列下，LRU/FIFO 的命中/淘汰结果与手工推演 100% 一致，统计数值正确。
- **SC-006**: 端到端演示（建表→插入≥100 行→条件查询→删除→重启再查）一次通过，结果正确且重启后数据完整。
- **SC-007**: 全组 4 人都能对随机指定的模块函数进行现场讲解，并能手工画出任意示例 SQL 的 AST 与 Logical Plan。

## Assumptions

- 实现语言为 Python 3.11（课程 PPT 示例结构为 Python 模块）；核心功能仅用标准库。
- 数据类型仅需 INT / VARCHAR(n)（n 为 1–255；布尔为表达式结果类型）；VARCHAR 长度按 UTF-8 编码后的字节数校验，NULL、更多类型属扩展项。
- 单用户、单进程、无并发控制与事务（属扩展项，不在必做范围）。
- 表规模以教学演示为准（数千行量级），无硬性能指标要求，但全表扫描在演示数据量下应瞬时返回。
- 目录结构采用课程建议的 `database_system/` 布局，4 人小组按模块分工。
- UPDATE / JOIN / ORDER BY / GROUP BY / 索引 / 代价模型为扩展项，仅在必做项完成并验收后投入。
