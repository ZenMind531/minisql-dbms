import os
import struct

from database_system.utils.constants import PAGE_SIZE
from database_system.storage.page import Page

MAGIC = b"MSQL"
VERSION = 1
HEADER_FMT = "<4sIII"   # magic(4B) version(4B) 页总数(4B) 空闲链表头(4B)


class FileManager:
      def __init__(self, path):
          self.path = path
          if os.path.exists(path) and os.path.getsize(path) >= PAGE_SIZE:
              self._f = open(path, "r+b")
              self._read_header()
          else:
              # 新建文件：先写一个空白的页 0（文件头页）
              self._f = open(path, "w+b")
              self._count = 1
              self._free_head = 0
              self._f.write(b"\x00" * PAGE_SIZE)
              self._flush_header()

      # ---------- 文件头（页 0） ----------
      def _read_header(self):
          self._f.seek(0)
          magic, _, self._count, self._free_head = struct.unpack(HEADER_FMT,
  self._f.read(16))
          if magic != MAGIC:
              raise ValueError(f"不是 MiniSQL 数据文件: {self.path}")

      def _flush_header(self):
          self._f.seek(0)
          self._f.write(struct.pack(HEADER_FMT, MAGIC, VERSION, self._count,
  self._free_head))
          self._f.flush()

      # ---------- 分配 / 释放页 ----------
      def allocate_page(self):
          if self._free_head != 0:          # 有空闲页就复用
              pid = self._free_head
              self._f.seek(pid * PAGE_SIZE)
              (nxt,) = struct.unpack("<I", self._f.read(4))
              self._free_head = nxt
          else:                             # 没有空闲页，文件末尾加一页
 
              pid = self._count
              self._count += 1
              self._f.seek(0, 2)
              self._f.write(b"\x00" * PAGE_SIZE)
          # 关键修复：分配时直接写一个格式化好的空白数据页
          # 读回来才是合法空页；顺带清掉旧数据（复用页不泄漏）
          self.write_page(pid, Page(page_id=pid,page_type=Page.DATA))
          self._flush_header()
          return pid

      def free_page(self, page_id):
          self._f.seek(page_id * PAGE_SIZE)
          self._f.write(struct.pack("<I", self._free_head))   # 挂到空闲链表头
          self._free_head = page_id
          self._flush_header()

      # ---------- 按页号读 / 写一整页 ----------
      def read_page(self, page_id):
          self._f.seek(page_id * PAGE_SIZE)
          data = self._f.read(PAGE_SIZE)
          if len(data) < PAGE_SIZE:
              raise ValueError(f"页 {page_id} 越界")
          return Page.from_bytes(data)

      def write_page(self, page_id, page):
          self._f.seek(page_id * PAGE_SIZE)
          self._f.write(page.to_bytes())
          self._f.flush()

      def page_count(self):
          return self._count

      def close(self):
          self._f.close()