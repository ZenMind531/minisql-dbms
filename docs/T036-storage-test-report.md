# T036 存储模块测试报告（负责人 C）

> 范围：`database_system/storage/`（Page / FileManager / BufferPool）及其测试。
> 环境：Windows 11，仓库内 `.venv`，Python 3.11.9，pytest 9.1.1。
> 日期：2026-09-14

## 1. 测试文件与覆盖行为清单

| 测试文件 | 用例 | 覆盖行为 |
|---|---|---|
| `tests/test_storage.py` | `test_insert_and_get_row` | Page：插入一行返回槽号 0，按槽号读回内容一致 |
| | `test_full_page_returns_none` | Page：连续插入直至放不下，`insert_row` 返回 `None`（页满判定），已有行仍可读 |
| | `test_delete_removes_from_rows` | Page：`delete_row` 后 `rows()` 不再产出该行，其它行不受影响 |
| | `test_to_from_bytes_roundtrip` | Page：`to_bytes()` 长度恰好 4096；`from_bytes` 还原后 page_id 与各行内容一致 |
| | `test_update_row_same_length_in_place` | Page：`update_row` 同长度时**原地覆盖**，槽号不变 |
| | `test_update_row_length_change_moves_slot` | Page：`update_row` 长度变化时退化为删除+插入，返回新槽号 |
| | `test_update_row_on_full_page_same_length_still_works` | Page：页满时仍可对已有行做同长度原地改写 |
| | `test_file_write_read` | FileManager：新文件 `page_count()==1`（仅文件头页）；分配页→写页→按页号读回一致 |
| | `test_free_reuse_and_restart` | FileManager：分配 3 页→释放页 2→关闭→重新打开；`page_count()` 正确，再次分配复用页 2 |
| `tests/test_buffer.py` | `test_lru_evicts_least_recent` | BufferPool(LRU)：固定序列下淘汰最久未使用的页；命中/未命中计数正确 |
| | `test_fifo_evicts_oldest` | BufferPool(FIFO)：固定序列下淘汰最早进入的页；命中/未命中计数正确 |
| | `test_pinned_page_not_evicted` | BufferPool：被 pin 的页不淘汰；全部帧被 pin 时抛 `StorageError` |
| | `test_dirty_page_flushed_on_eviction` | BufferPool：脏页被淘汰前写回磁盘，`evictions`/`flushes` 计数正确 |
| | `test_flush_all_writes_dirty_pages` | BufferPool：`flush_all()`（CLI 退出前调用）把脏页写回磁盘 |
| `tests/test_storage_persist.py` | `test_restart_persistence` | 独立进程写入并退出后，新进程重新打开文件能读回全部数据（页 0 文件头与数据页均持久） |

辅助脚本：`tests/_persist_helper.py`（不属于测试用例，供上面的持久化测试以独立进程调用）。

合计：`test_storage.py` 9 项 + `test_buffer.py` 5 项 + `test_storage_persist.py` 1 项 = **15 项**。

## 2. 执行命令与结果

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_storage.py tests/test_buffer.py tests/test_storage_persist.py -v
```

结果：**15 passed**。

同时与全仓测试一起运行时通过（2026-09-14，合并 `codex/catalog-persistence` 之后）：

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q
# 220 passed, 171 subtests passed
```

## 3. LRU / FIFO 固定序列手工推演

缓冲池容量 = 3，访问序列：`1, 2, 3, 1, 4`，之后再访问 2。表中“帧顺序”按淘汰优先级排列（最左最先被淘汰）。

### 3.1 LRU（命中后把页移到“最近使用”一端）

| 访问 | 结果 | 帧顺序 | 说明 |
|---|---|---|---|
| 1 | miss | 1 | 读盘 |
| 2 | miss | 1, 2 | 读盘 |
| 3 | miss | 1, 2, 3 | 读盘 |
| 1 | **hit** | 2, 3, 1 | 1 变为最近使用 |
| 4 | miss | 3, 1, 4 | 淘汰最久未用的 **2** |
| 2 | miss | … | 2 已被淘汰，需重新读盘 |

计数：hits = 1，misses = 5，evictions = 1。

### 3.2 FIFO（命中不改变顺序，只按进入先后淘汰）

| 访问 | 结果 | 帧顺序 | 说明 |
|---|---|---|---|
| 1 | miss | 1 | 读盘 |
| 2 | miss | 1, 2 | 读盘 |
| 3 | miss | 1, 2, 3 | 读盘 |
| 1 | **hit** | 1, 2, 3 | 命中但不挪位 |
| 4 | miss | 2, 3, 4 | 淘汰最早进入的 **1** |
| 2 | **hit** | 2, 3, 4 | 2 仍在缓存中 |

计数：hits = 2，misses = 4，evictions = 1。

### 3.3 与测试断言对照

- LRU 用例断言 `misses == 5`；FIFO 用例断言 `misses == 4`；两者都断言 `evictions == 1`。与推演一致。

## 4. 持久化验证过程

目的：证明数据与文件头跨进程退出后仍在磁盘上，可被重新打开读出。

1. 测试进程用 `subprocess.run` 启动一个新的 Python 进程执行 `tests/_persist_helper.py <临时文件路径>`。
2. 该子进程（“进程 1”）新建 FileManager，分配两个页，分别写入 `row-1`、`row-2`，随后 `close()` 并正常退出。
3. 测试进程（“进程 2”，相当于重启数据库）用新的 FileManager 打开同一个文件，断言：
   - `page_count() == 3`（页 0 文件头 + 页 1 + 页 2）
   - `read_page(1).rows() == [(0, b"row-1")]`，`read_page(2).rows() == [(0, b"row-2")]`

## 5. 与规格的一致性复核

对照 `specs/001-minisql-dbms/data-model.md`（存储侧）与 `contracts/storage-api.md`：

已对齐：

- 页头固定 32B：page_id(u32) / page_type(u8) / slot_count(u16) / free_start(u16) / free_end(u16) / reserved；槽数组自第 32B 向后生长，每槽 (offset u16, length u16)；行数据自页尾向前生长。
- 不变式 `free_start <= free_end`；插入判定 `len(row) + 4 <= free_end - free_start`。
- `Page` / `FileManager` / `BufferPool` 的方法签名与返回语义。
- 页 0 为文件头页（不存用户行），数据页从 1 开始编号，`page_count()` 包含页 0。
- 命中统计语义（缓存命中记 hit，触发磁盘读记 miss）；脏页先写回再淘汰；被 pin 的页不淘汰；全部帧被 pin 时抛 `StorageError`；缓存日志走 `logging.getLogger("buffer")`。

复核中发现的一处契约与实际依赖的冲突（**已保留原行为，待接口评审决定**）：

- 契约开头写“错误抛 `utils.errors.StorageError`”。但 `FileManager.read_page` 读到越界页、以及文件头 magic 不合法时，成员 D 的 `tests/test_engine.py` 明确期望底层异常是 **`ValueError`**（由引擎负责包装成 `StorageError`）。本轮曾按契约改为抛 `StorageError`，导致 `test_engine.py::test_load_wraps_catalog_scan_and_decode_corruption[missing-declared-page-ValueError]` 失败，因此**回退为 `ValueError`**。
- 建议在接口评审时二选一：① 契约补充说明“存储层内部读失败抛 `ValueError`/`struct.error` 等底层异常，由调用方包装为 `StorageError`”；或 ② 修改 D 的引擎与测试，统一改为存储层直接抛 `StorageError`。

本轮实际保留的修改：

- `Page.update_row(slot, row)`：契约外**新增方法**，用于 UPDATE 写回（同长度原地覆盖；长度变化则删除+插入；空间不足返回 `None`）。
- `BufferPool.flush_page` / `flush_all`：增加日志输出（FR-012）。
- `Page` 增加 `StorageError` 导入兜底（供将来统一错误类型使用；当前 `page.py` 自身不抛出该异常）。

## 6. 已知限制与未覆盖场景

- **删除不回收空间**：`Page.delete_row` 仅把槽长度置 0，不复用槽号、不移动行数据、不做碎片整理。反复“插入+删除”会使页提前判定为满。UPDATE 应优先使用 `Page.update_row`（同长度原地覆盖），避免该问题。
- **页内超大行**：未测试单行接近或超过页容量（约 4092 字节可用）的情况；`insert_row` 会返回 `None`，需上层另分配页。
- **缓冲池边界**：未测试 `capacity = 0`、跨多个 FileManager 的共享缓冲池；`policy` 仅接受 `"LRU"`/`"FIFO"`，其它取值会退化为 FIFO 语义，无参数校验。
- **文件损坏恢复**：仅校验文件头 magic，没有损坏检测、备份或修复能力。
- **目录页（page_type = 2）**：常量已定义，目录表 `__catalog__` 的页使用属 D 的 CatalogManager，不在存储模块测试范围内。
- **契约外扩展**：`FileManager.close()`、`Page.update_row()` 不在 `contracts/storage-api.md` 现有列表中，待接口评审确认是否正式写入契约。
- **环境说明**：本机网络受限，`.venv` 用 `python -m venv --system-site-packages .venv` 创建（pytest 9.1.1 来自系统 Python 环境），并非从 PyPI 独立安装。
