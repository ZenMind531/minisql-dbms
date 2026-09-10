 #"""缓存池：按 LRU/FIFO 淘汰，支持 pin/dirty，命中统计 + 日志。"""

import logging
from collections import OrderedDict

from database_system.storage.file_manager import FileManager
from database_system.storage.page import Page

  # B 还没写 StorageError，先用本地兜底；等他在 utils/errors.py加了会自动改用他的
try:
      from database_system.utils.errors import StorageError
except ImportError:
      class StorageError(Exception):
          def __init__(self, message):
              self.type = "StorageError"
              self.message = message
              super().__init__(message)

logger = logging.getLogger("buffer")


class BufferPool:
      def __init__(self, file_manager, capacity=64, policy="LRU"):
          self._fm = file_manager
          self.capacity = capacity
          self.policy = policy
          self._frames = OrderedDict()   # page_id -> {"page","pin", "dirty"}
          self._hits = 0
          self._misses = 0
          self._evictions = 0
          self._flushes = 0

      def _touch(self, pid):
          # LRU：命中后把页挪到“最近使用”那一端；FIFO不动（按插入序）
          if self.policy == "LRU":
              self._frames.move_to_end(pid)

      def _evict_one(self):
          # 从最久未用端开始，找第一个没被 pin 的页淘汰；脏页先写回
          for pid in list(self._frames.keys()):
              if self._frames[pid]["pin"] == 0:
                  fr = self._frames.pop(pid)
                  if fr["dirty"]:
                      self._fm.write_page(pid, fr["page"])
                      self._flushes += 1
                      logger.info("evict dirty page %s flushed",pid)
                  self._evictions += 1
                  logger.info("evict page %s", pid)
                  return pid
          raise StorageError("buffer pool full: all frames pinned")

      def get_page(self, pid):
          fr = self._frames.get(pid)
          if fr is not None:                     # 命中缓存
              self._hits += 1
              self._touch(pid)
              fr["pin"] += 1
              return fr["page"]
          self._misses += 1                      # 未命中：淘汰腾位 → 读盘
          while len(self._frames) >= self.capacity:self._evict_one()
          page = self._fm.read_page(pid)
          self._frames[pid] = {"page": page, "pin": 1, "dirty":False}
          return page

      def unpin_page(self, pid, dirty=False):
          fr = self._frames.get(pid)
          if fr is None:
              return
          if dirty:
              fr["dirty"] = True
          if fr["pin"] > 0:
              fr["pin"] -= 1

      def flush_page(self, pid):
          fr = self._frames.get(pid)
          if fr is not None and fr["dirty"]:
              self._fm.write_page(pid, fr["page"])
              fr["dirty"] = False
              self._flushes += 1

      def flush_all(self):
          for pid, fr in list(self._frames.items()):
              if fr["dirty"]:
                  self._fm.write_page(pid, fr["page"])
                  fr["dirty"] = False
                  self._flushes += 1

      def stats(self):
          return {"hits": self._hits, "misses": self._misses,"evictions": self._evictions, "flushes": self._flushes,"policy": self.policy}