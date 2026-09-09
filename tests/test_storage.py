"""Page 的测试：先写测试（红），再实现 page.py 让它变绿。"""

from database_system.storage.page import Page
from database_system.storage.file_manager import FileManager

def test_insert_and_get_row():
    """把一行字节塞进页，再按槽号取回来，应该一模一样。"""
    page = Page(page_id=1)
    slot = page.insert_row(b"hello")
    assert slot == 0
    assert page.get_row(slot) == b"hello"
def test_full_page_returns_none():
      page = Page(page_id=2)
      n = 0
      while page.insert_row(b"abc") is not None:
          n += 1
      assert n >= 500          # 页里至少能塞 500 个 "abc"
      assert page.get_row(0) == b"abc"


def test_delete_removes_from_rows():
      page = Page(page_id=3)
      page.insert_row(b"a")
      page.insert_row(b"b")
      page.delete_row(0)
      assert list(page.rows()) == [(1, b"b")]   # 只剩第 1 槽的 b


def test_to_from_bytes_roundtrip():
      page = Page(page_id=7)
      page.insert_row(b"hello")
      page.insert_row(b"world")
      data = page.to_bytes()
      assert len(data) == 4096                  # 整页正好 4096 字节
      page2 = Page.from_bytes(data)             # 从字节还原
      assert page2.page_id == 7
      assert page2.get_row(0) == b"hello"
      assert page2.get_row(1) == b"world"
def test_file_write_read(tmp_path):
      path = str(tmp_path / "student.dat")
      fm = FileManager(path)
      assert fm.page_count() == 1          # 刚开始只有页 0（文件头）
      pid = fm.allocate_page()
      page = Page(page_id=pid)
      page.insert_row(b"alice")
      page.insert_row(b"bob")
      fm.write_page(pid, page)
      assert list(fm.read_page(pid).rows()) == [(0, b"alice"), (1, b"bob")]


def test_free_reuse_and_restart(tmp_path):
      path = str(tmp_path / "student.dat")
      fm = FileManager(path)
      p1 = fm.allocate_page()              # 1
      p2 = fm.allocate_page()              # 2
      p3 = fm.allocate_page()              # 3
      fm.free_page(p2)                     # 释放 2
      fm.close()
      fm2 = FileManager(path)              # 模拟重启
      assert fm2.page_count() == 4
      assert fm2.allocate_page() == 2      # 复用了被释放的页 2