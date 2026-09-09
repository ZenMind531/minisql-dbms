from database_system.storage.file_manager import FileManager
from database_system.storage.buffer import BufferPool,StorageError


def _fm(path, pages):
      fm = FileManager(path)
      for _ in range(pages):
          fm.allocate_page()
      return fm

def _get(pool, pid, dirty=False):
      pool.get_page(pid)
      pool.unpin_page(pid, dirty=dirty)


def test_lru_evicts_least_recent(tmp_path):
      fm = _fm(str(tmp_path / "a.dat"), 4)
      pool = BufferPool(fm, capacity=3, policy="LRU")
      for p in (1, 2, 3):
          _get(pool, p)
      _get(pool, 1)              # 命中，1 变成最近使用
      _get(pool, 4)              # miss，应淘汰 2（最久未用）
      assert pool.stats()["evictions"] == 1
      _get(pool, 2)
      assert pool.stats()["misses"] == 5   # 2 已被淘汰 → miss


def test_fifo_evicts_oldest(tmp_path):
      fm = _fm(str(tmp_path / "b.dat"), 4)
      pool = BufferPool(fm, capacity=3, policy="FIFO")
      for p in (1, 2, 3):
          _get(pool, p)
      _get(pool, 1)              # 命中，但 FIFO 不挪位
      _get(pool, 4)              # miss，应淘汰 1（最早进入）
      assert pool.stats()["evictions"] == 1
      _get(pool, 2)
      assert pool.stats()["misses"] == 4   # 2 还在缓存 →hit，没增加 miss


def test_pinned_page_not_evicted(tmp_path):
      fm = _fm(str(tmp_path / "c.dat"), 3)
      pool = BufferPool(fm, capacity=1, policy="LRU")
      pool.get_page(1)           # 钉住，不 unpin
      try:
          pool.get_page(2)
          raise AssertionError("应抛 StorageError（唯一一帧被pin）")
      except StorageError:
          pass
      pool.unpin_page(1)


def test_dirty_page_flushed_on_eviction(tmp_path):
      fm = _fm(str(tmp_path / "d.dat"), 3)
      pool = BufferPool(fm, capacity=1, policy="LRU")
      p1 = pool.get_page(1)
      p1.insert_row(b"AAA")
      pool.unpin_page(1, dirty=True)
      pool.get_page(2)           # 挤走页 1，触发脏页写回
      pool.unpin_page(2)
      assert pool.stats()["evictions"] == 1 and pool.stats()["flushes"] == 1
      assert list(fm.read_page(1).rows()) == [(0, b"AAA")]
      