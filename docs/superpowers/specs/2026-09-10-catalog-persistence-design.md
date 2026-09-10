# MiniSQL 系统目录持久化与端到端验收设计

## 目标

完成系统目录持久化，使数据库关闭并重新启动后仍能恢复表结构并读取原有
数据；补齐引擎、端到端和演示 SQL 测试；清理项目状态文档中过时且互相矛盾
的描述。

实现遵守 `specs/001-minisql-dbms/contracts/engine-api.md` 和 FR-016、FR-016A，
不使用契约外的 JSON 元数据旁路。

## 系统目录格式

目录存储在数据目录中的 `__catalog__.dat`，通过现有 `StorageEngine`、
`BufferPool` 和 `FileManager` 读写。目录表固定包含四列：

1. `table_name VARCHAR(255)`
2. `col_name VARCHAR(255)`
3. `col_type VARCHAR(16)`
4. `col_order INT`

`col_type` 使用 `INT` 或 `VARCHAR(n)`，因此不改变冻结契约规定的四字段行格式，
同时完整保留 VARCHAR 长度。

`__catalog__` 不把自己的列作为普通目录行写进自身，避免递归 bootstrap；启动时
由代码中的固定模式把它加入内存 Catalog 和 StorageEngine，所以用户仍可执行
`SELECT * FROM __catalog__;` 查询普通表的目录行。

## 启动与建表数据流

首次启动：

1. 构造 StorageEngine。
2. CatalogManager 发现目录文件不存在，按固定模式 bootstrap
   `__catalog__.dat`。
3. 建立包含 `__catalog__` 的内存 Catalog。

重启：

1. 按固定模式挂载 `__catalog__.dat`。
2. 扫描目录行，校验类型描述、列顺序、重复项和对应数据文件。
3. 按表分组并依列序重建内存 `TableSchema`。
4. 把每个恢复出的 schema 挂载到 StorageEngine。

普通 CREATE TABLE：

1. 语义层确认内存 Catalog 中不存在同名表。
2. StorageEngine 创建新的表数据文件。
3. CatalogManager 把所有列元数据写入目录表并 flush。
4. 成功后才更新内存 Catalog。

如果目录登记失败，CatalogManager 删除本次创建且尚未对外可见的数据文件，
内存 Catalog 保持不变。已存在文件、损坏目录或缺失数据文件均抛结构化
`StorageError`，不得静默覆盖或丢弃。

## 组件改动

- 新增 `database_system/engine/catalog_manager.py`，公开冻结契约中的 `load()`
  和 `register_table()`，并集中负责 bootstrap、解析和一致性校验。
- `StorageEngine` 增加挂载既有 schema、判断/删除精确表文件的最小能力；删除只
  用于 CREATE 回滚。
- `Executor` 可选接收 CatalogManager。MiniDB 始终提供它；保留既有两参数构造
  方式供已有单元测试使用。
- `MiniDB` 启动时调用 CatalogManager.load()，不再创建空 Catalog。

## 错误与一致性

- 目录行只接受 `INT` 和 `VARCHAR(1..255)`。
- 同表列序必须从 0 开始连续且列名不重复。
- 目录声明的普通表必须存在对应 `.dat` 文件。
- 注册目录行后立即 flush，使正常关闭前的后续异常不造成“数据文件存在但目录
  尚未落盘”。
- 回滚只删除当前 CREATE 新建的精确文件，不扫描或删除其他文件。

当前项目不提供事务日志。进程在多列目录写入的中途被强制杀死时，启动阶段会
将不完整目录识别为损坏并报告 `StorageError`；原子日志属于规格外扩展。

## 测试与演示

- `tests/test_engine.py`：行编解码、四类计划执行、WHERE/投影/删除、目录加载与
  注册、损坏目录、创建失败回滚。
- `tests/test_e2e.py`：从 SQL 文本执行完整演示、关闭并新建 MiniDB 后查询原有
  数据、查询 `__catalog__`、错误后继续使用。
- `tests/sql/demo_e2e.sql`：固定七条建表/插入/查询/删除演示 SQL。
- CLI 文件模式测试验证脚本输出和重启后的数据可查询。
- 最终使用 Python 3.11 运行完整 pytest，并执行 compileall、CLI 演示和
  `git diff --check`。

## 文档收尾

重写 `docs/PROJECT_CONTEXT.md` 为单一当前状态，删除 Parser 缺失、Engine 尚未
开始等历史快照；同步 README、quickstart 和 tasks 中已经有测试证据的任务
状态。成员 D 范围的接口改动明确标注需 D 复核。
