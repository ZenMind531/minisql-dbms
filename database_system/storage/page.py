import struct

from database_system.utils.constants import PAGE_SIZE

HEADER_SIZE = 32   # 页头固定 32 字节
SLOT_SIZE = 4      # 一个槽 = offset(u16) + length(u16)


class Page:
      # 页类型
      FREE = 0
      DATA = 1
      CATALOG = 2

      def __init__(self, page_id, page_type=DATA):
          self.page_id = page_id
          self.page_type = page_type
          self._slots = []                   # 每个有效槽: [行起始位置, 行长度]
          self._data = bytearray(PAGE_SIZE)  # 整页内存
          self._free_start = HEADER_SIZE     # 槽数组写到的位置（往前长）
          self._free_end = PAGE_SIZE         # 行数据写到的位置（往后长）

      def insert_row(self, row):
          # 放一行需 新槽(4B)+行本身；空间不够返回 None（满页）
          if len(row) + SLOT_SIZE > self._free_end - self._free_start:
              return None
          self._free_end -= len(row)
          self._data[self._free_end:self._free_end + len(row)] = row
          slot = len(self._slots)
          self._slots.append([self._free_end, len(row)])
          self._free_start += SLOT_SIZE
          return slot

      def get_row(self, slot):
          offset, length = self._slots[slot]
          return b"" if length == 0 else bytes(self._data[offset:offset +
  length])

      def delete_row(self, slot):
          self._slots[slot][1] = 0  # 长度置 0 = 已删，先不搬数据

      def rows(self):
          for i, (offset, length) in enumerate(self._slots):
              if length == 0:
                  continue
              yield i, bytes(self._data[offset:offset + length])

      def to_bytes(self):
          # 页头: page_id(u32) type(u8) slot数(u16) free_start(u16) free_end(u16)
          h = struct.pack("<IBHHH", self.page_id, self.page_type,
                          len(self._slots), self._free_start, self._free_end)
          self._data[0:len(h)] = h
          pos = HEADER_SIZE
          for offset, length in self._slots:
              self._data[pos:pos + SLOT_SIZE] = struct.pack("<HH", offset,
  length)
              pos += SLOT_SIZE
          return bytes(self._data)

      @classmethod
      def from_bytes(cls, data):
          pid, pt, sc, fs, fe = struct.unpack_from("<IBHHH", data, 0)
          page = cls(pid, pt)
          page._free_start, page._free_end = fs, fe
          pos = HEADER_SIZE
          page._slots = []
          for _ in range(sc):
              o, l = struct.unpack_from("<HH", data, pos)
              page._slots.append([o, l])
              pos += SLOT_SIZE
          page._data = bytearray(data)
          return page
