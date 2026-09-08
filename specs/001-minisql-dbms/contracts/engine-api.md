# Contract: 引擎与 CLI 接口（负责人 D）

## StorageEngine（行/页映射）

```python
class StorageEngine:
    def __init__(self, data_dir: str, buffer_capacity: int = 64,
                 policy: str = "LRU"): ...
    def create_table(self, schema: TableSchema) -> None     # 仅创建并初始化 .dat
    def insert_row(self, table: str, row: tuple) -> None    # 序列化→找页/分配→写入
    def scan(self, table: str) -> Iterator[tuple]           # 全表行迭代（反序列化）
    def delete_where(self, table: str, pred: Callable[[tuple], bool]) -> int
    def flush(self) -> None
```

## CatalogManager（系统目录持久化）

```python
class CatalogManager:
    # 目录即特殊表 __catalog__，行 = (table_name, col_name, col_type, col_order)
    def load(self) -> Catalog          # 启动时重建内存 Catalog
    def register_table(self, schema: TableSchema) -> None   # 写目录行
```

首次启动时 CatalogManager 直接创建固定模式的 `__catalog__` 文件，不调用
`register_table(__catalog__)`。普通 CREATE TABLE 的编排顺序固定为：
`StorageEngine.create_table` → `CatalogManager.register_table` → 更新内存 Catalog。
任一步失败都返回结构化错误；若目录登记失败，删除本次新建且尚未对外可见的数据文件。

## Executor（算子执行）

```python
class Executor:
    def __init__(self, engine: StorageEngine, catalog: Catalog): ...
    def execute(self, plan: PlanNode) -> Result:
        # CreateTable → "OK"
        # Insert      → "N row(s) inserted"
        # SeqScan+Filter+Project → list[tuple]（已投影、已过滤）
        # Delete+Filter+SeqScan → "N row(s) deleted"
```

## CLI

```text
用法:  python -m database_system.cli.main [--file script.sql] [--data data/]
REPL:  MiniDB> <SQL>            # quit / exit 退出
规则:  逐条执行；成功打印结果表或 OK 信息；
       失败打印 "XxxError at line L, column C: 原因" 并继续；
       退出前自动 flush_all。
```

## 顶层编排（供集成测试复用）

```python
class MiniDB:
    def __init__(self, data_dir: str = "data/"): ...
    def execute(self, sql: str) -> str    # 全流程：Lex→Parse→Semantic→
                                          # Plan→Optimize→Execute→格式化输出
```
