# Contract: 存储模块接口（负责人 C）

> D（引擎）只准通过本契约访问磁盘；禁止直接 open 数据文件。
> 错误抛 `utils.errors.StorageError`。

## Page

```python
PAGE_SIZE = 4096  # utils.constants

class Page:
    page_id: int
    def insert_row(self, row: bytes) -> int | None   # 返回 slot 号；页满返回 None
    def get_row(self, slot: int) -> bytes
    def delete_row(self, slot: int) -> None
    def rows(self) -> Iterator[tuple[int, bytes]]    # (slot, row) 有效行迭代
    def to_bytes(self) -> bytes                      # 恰好 4096 字节
    @classmethod
    def from_bytes(cls, data: bytes) -> "Page"
```

## FileManager

```python
class FileManager:
    def __init__(self, path: str): ...                # 每表一个文件
    # 页 0 为文件头页；普通数据页编号从 1 开始
    def allocate_page(self) -> int                    # 复用空闲链表，否则追加
    def free_page(self, page_id: int) -> None
    def read_page(self, page_id: int) -> Page
    def write_page(self, page_id: int, page: Page) -> None
    def page_count(self) -> int                       # 包含页 0
```

## BufferPool

```python
class BufferPool:
    def __init__(self, file_manager: FileManager, capacity: int = 64,
                 policy: str = "LRU"): ...            # "LRU" | "FIFO"
    def get_page(self, page_id: int) -> Page          # 命中/加载并增加 pin_count
    def unpin_page(self, page_id: int, dirty: bool = False) -> None
                                                        # dirty=True 表示本次访问修改过页面
    def flush_page(self, page_id: int) -> None
    def flush_all(self) -> None                       # CLI 退出前必调
    def stats(self) -> dict   # {"hits": int, "misses": int,
                              #  "evictions": int, "flushes": int, "policy": str}
```

- 命中统计语义：**get_page 命中缓存** 记 hit，触发磁盘读记 miss。
- 淘汰脏页必须先写回再丢弃（FR-013）。
- pin_count > 0 的页不得淘汰；若所有帧均被 pin，get_page 抛 StorageError。
- 每次成功 get_page 后，调用方必须在 finally 中调用一次 unpin_page；写路径
  传 dirty=True，读路径传 dirty=False。
- 缓存行为经 `logging.getLogger("buffer")` 输出（FR-012）。
