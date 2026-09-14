# C 对 DROP TABLE / UPDATE 的存储层评审（负责人 C）

> 面向成员 D。范围：DROP TABLE 与 UPDATE 落到存储层时会碰到的问题。
> 本轮 C 不改 Lexer / Parser / AST（A 的字段待评审冻结）。

## 1. DROP TABLE：删除 `.dat` 文件前的顺序与风险

### 存储层现状（事实）

- `FileManager` 内部持有打开的文件句柄（`open(path, "r+b")`）。
- **Windows 上被打开的文件无法删除**，`os.remove` 会抛 `PermissionError`。因此删除文件前**必须先 `close()`**。
- `BufferPool` 只持有内存中的 Page 对象，不持有文件句柄；但其中的**脏页若未写回，会与磁盘状态不一致**。

### 推荐的 DROP 顺序

1. 若该表有缓冲池：`bp.flush_all()`（把脏页写回，保证磁盘状态是最新的）
2. `fm.close()`（释放文件句柄，否则第 4 步删不掉）
3. 删除该表的元数据（内存 Catalog + `__catalog__` 中的行）
4. `os.remove("<table>.dat")`

### 失败补偿（每步失败怎么办）

| 失败点 | 处理 |
|---|---|
| 第 1、2 步失败 | 整个 DROP 失败，**元数据不动**，文件保留，报 `StorageError` |
| 第 3 步失败 | 回滚内存改动，报错；文件保留（此时只是没删成功，数据仍完整） |
| 第 4 步失败 | 元数据已删、文件残留 → 只留下**孤儿文件**，不影响后续运行；记录告警即可 |

**不要用相反的顺序**（先删文件再删元数据）：那样一旦删元数据失败，就会出现“元数据指向一个不存在的文件”，之后对该表的任何操作都会因文件缺失而报错。

### 缓存相关提醒

- 若 D 的设计是“每张表一个 `FileManager` + 一个 `BufferPool`”（推荐，契约就是这么建模的），删除时直接丢弃该 BufferPool 对象即可。
- 若使用**跨表共享**的缓冲池，删除某表前必须确保该表的所有页都不再被缓存引用，否则后续写入可能把已删除的文件重新创建出来。当前的 `BufferPool` 没有“按表丢弃页”的方法，若 D 需要共享池，请提出，我们再评估加接口。

## 2. UPDATE 写回：行长度与页内空间

### 前提

行的字节长度由 D 的序列化方式决定（`research.md` 决策 3）：`struct` 定长，INT 4 字节，VARCHAR 按声明长度上限定长。因此**同一张表内所有行等长**。

### 两种做法对比

**做法 A（推荐）：用新增的 `Page.update_row(slot, row)`**

本轮 C 新增了该方法：

```python
def update_row(self, slot, row):
    # 长度与旧行相同 → 原地覆盖，槽号不变，不额外占用空间
    # 长度不同     → 内部转为 删除旧行 + 插入新行，返回新槽号
    # 空间不足     → 返回 None
```

因为同表行等长，UPDATE 时新旧行长度相同 → **原地覆盖**，页内空间不增长，`rows()` 立即反映新值，页满时也能改。

**做法 B：`delete_row` + `insert_row`（不推荐，有空间泄漏）**

- `delete_row` 只把槽长度置 0，**既不回收空间也不复用槽号**。
- 每次 UPDATE 都会多消耗「4 字节槽 + 一行数据」，反复更新同一张表会**过早把页判定为满**，随后 `insert_row` 返回 `None`，D 必须处理“把该行迁到新页”的情况。
- 如果实在要用做法 B，必须实现“页满 → 分配新页 → 行迁移”。

### 行宽上限

- 单行序列化后的字节数必须 ≤ 一页可用空间（约 4092 字节），否则 `insert_row` 永远返回 `None`。
- 建议 D 在 CREATE TABLE 时按列宽估算并校验单行最大长度，避免出现“一行都放不下”的表。

## 3. DROP 失败时的资源恢复（结论）

- 不做复杂的两阶段提交；采用上面第 1 节的**可重入补偿顺序**即可：先让存储层状态干净 → 再删元数据 → 最后删文件。
- 结果特征：
  - 中途失败要么“什么都没变”，要么“只留下孤儿文件”（无害，可选地在启动时清理）。
  - 不会出现“元数据在、文件没了”这种会直接导致查询报错的状态。

## 4. C 本轮改动清单（供接口评审确认）

- `Page.update_row(slot, row)`：**新增方法**（不在 `contracts/storage-api.md` 现有列表中），用于 UPDATE 写回；建议接口评审时决定是否正式写入契约。
- `BufferPool.flush_page` / `flush_all` 增加日志输出（FR-012）。
- 新增测试：`test_update_row_same_length_in_place`、`test_update_row_length_change_moves_slot`、`test_update_row_on_full_page_same_length_still_works`、`test_flush_all_writes_dirty_pages`。

**一处需要接口评审解决的契约冲突**：

- 契约开头写“错误抛 `utils.errors.StorageError`”。但 `FileManager.read_page` 在读到越界页、以及文件头 magic 不合法时，D 的 `tests/test_engine.py` 明确期望底层异常为 **`ValueError`**（由引擎包装成 `StorageError` 并附带上下文）。
- 本轮曾按契约把这两处改为抛 `StorageError`，结果 `test_engine.py::test_load_wraps_catalog_scan_and_decode_corruption[missing-declared-page-ValueError]` 失败，因此**已回退为 `ValueError`**（保持引擎现有依赖）。
- 请评审二选一：① 契约补充“存储层内部读失败抛底层异常（`ValueError`/`struct.error`/`UnicodeDecodeError`），由调用方包装为 `StorageError`”；或 ② D 调整引擎与测试，存储层统一抛 `StorageError`。

存储测试当前结果（仓库 `.venv`）：

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_storage.py tests/test_buffer.py tests/test_storage_persist.py -q
# 15 passed
```

## 5. 给 D 的行动清单

- [ ] DROP：按 `flush_all → close → 删元数据 → 删文件` 的顺序实现，并处理上述失败分支。
- [ ] DROP：禁止删除 `__catalog__`；删除前确认该表不在任何缓冲池中。
- [ ] UPDATE：优先调用 `Page.update_row(slot, row)`；检查返回值 `None`（空间不足）并处理。
- [ ] UPDATE：确认行序列化是定长；若因 VARCHAR 变长导致行长度变化，必须处理“删除+插入”和页满迁移。
- [ ] 若使用跨表共享缓冲池，或需要“按表丢弃缓存页”，请提出需求，C 再评估接口。
