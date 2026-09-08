# Data Model: MiniSQL 教学数据库系统

## 编译器侧

### Token
| 字段 | 类型 | 说明 |
|------|------|------|
| type | enum | KEYWORD / IDENTIFIER / CONST / OPERATOR / DELIMITER / EOF |
| lexeme | str | 原始词素（常量含值，字符串含引号或解析后值，组内定一处） |
| line, column | int | 1-based，用于错误定位 |

### AST（docs/design.md 详述）
- 语句节点：`CreateTableStmt(table, columns: [ColumnDef])` /
  `InsertStmt(table, columns: [str] | None, values)` /
  `SelectStmt(columns: [str] | None, table, where)` /
  `DeleteStmt(table, where)`
- 表达式节点：`BinaryExpr(op, left, right)` / `UnaryExpr(NOT, operand)` /
  `IdentifierExpr(name)` / `LiteralExpr(value, type)`
- 所有节点带 `line, column`；复合表达式记录其整个源码片段的起始位置，
  例如 `age > 18 AND ...` 的 AND 节点位置为 `age` 的位置；语义阶段回填
  `resolved_type`。
- `InsertStmt.columns=None` 表示省略目标列列表；`SelectStmt.columns=None`
  表示 `SELECT *`，非空列表表示显式列名。
- 字符串 `LiteralExpr.value` 不含外围引号，源码中的 `''` 解码为一个 `'`。
- `LiteralExpr` 的 value 必须与 INTEGER/FLOAT/STRING 字面量种类匹配；FLOAT
  可暂存在 AST，但当前语义阶段统一拒绝。

### Catalog（内存视图）
- `TableSchema: { name, columns: [ {name, type: INT|VARCHAR, length: int|None} ], first_page }`
- VARCHAR 长度范围为 1–255，按 UTF-8 字节数校验；INT 的 length 为 None。
- `TypeSpec` 自身保证 VARCHAR 必须带 1–255 的长度，INT/BOOL 不得带长度；
  BOOL 只可作为表达式结果类型，不可作为表列类型。
- 接口：`create_table / find_table / find_column / get_type`（见 contracts/compiler-api.md）
- 校验规则：表名/列名唯一；INSERT 列数、顺序、值类型与模式一致。

## 存储侧

### Page（4KB = 4096 字节）
- 页头（固定 32B）：page_id(u32) / page_type(u8: 0=空闲,1=数据,2=目录) /
  slot_count(u16) / free_start(u16) / free_end(u16) / reserved
- 槽数组：从 32B 起向后生长，每槽 (offset u16, length u16)
- 行数据：从页尾向前生长
- 不变式：`free_start <= free_end`；新行需 `len(row)+4 <= free_end-free_start`

### BufferPool
- 容量 N（默认 64 页）；帧表 page_id → frame；每帧 dirty 标志
- 统计：hits / misses / evictions / flushes；行为日志经 logging 输出

### 磁盘文件
- 每表一个 `<table>.dat`；页 0 固定为文件头页（magic/version/page_count/free_list_head），
  不存用户行；数据页从页 1 起连续编号，`page_count()` 包含页 0
- 目录表 `__catalog__.dat`：每行 = 一条 (table_name, col_name, col_type, col_order)

## 引擎侧

### Logical Plan 节点
`CreateTable(table, schema)` / `Insert(table, rows)` / `Delete(table, child)` /
`SeqScan(table)` / `Filter(predicate)` / `Project(columns)`
- 仅含执行所需信息；可序列化为 JSON。

### Row（执行期）
- Python tuple，按 TableSchema 列序排列；序列化格式见 research.md 决策 3。

## 状态流转

- 页：空闲 → 已分配（数据/目录）→ 脏（内存中被改）→ flush 后干净 → 可释放回空闲链表
- 语句：文本 → Token → AST → 已语义检查 AST → Logical Plan → 优化 Plan → 执行结果/错误
