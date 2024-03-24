"""
We treat an sqlite db as a read-only serialisation/archive format.

https://www.sqlite.org/fileformat.html
"""

from typing import BinaryIO, Optional, Dict, List
from enum import Enum
from dataclasses import dataclass
from functools import lru_cache
import struct
import io

def parse_varint(stream: BinaryIO) -> int:
	n = 0
	for _ in range(9):
		val = stream.read(1)
		if not val:
			raise ValueError("unexpected end of varint input")
		val = val[0]
		n = (n << 7) | (val & 0x7f)
		if not val & 0x80:
			return n
	raise ValueError("varint too long")

def parse_be_uint(stream: BinaryIO, n: int) -> int:
	data = stream.read(n)
	if len(data) != n:
		raise ValueError("uint underread")
	return int.from_bytes(data, "big")

def parse_be_int(stream: BinaryIO, n: int) -> int:
	data = stream.read(n)
	if len(data) != n:
		raise ValueError("int underread")
	return int.from_bytes(data, "big", signed=True)

def parse_record(stream: BinaryIO):
	start_offset = stream.tell()
	header_len = parse_varint(stream)
	serial_types = []
	while stream.tell() < (start_offset + header_len):
		serial_types.append(parse_varint(stream))
	
	# we could calculate the offset of each column, if we wanted to parse out a specific one

	for serial_type in serial_types:
		if serial_type == 0:
			yield None
		elif serial_type == 1:
			yield parse_be_int(stream, 1)
		elif serial_type == 2:
			yield parse_be_int(stream, 2)
		elif serial_type == 3:
			yield parse_be_int(stream, 3)
		elif serial_type == 4:
			yield parse_be_int(stream, 4)
		elif serial_type == 5:
			yield parse_be_int(stream, 6)
		elif serial_type == 6:
			yield parse_be_int(stream, 8)
		elif serial_type == 7:
			yield struct.unpack(">d", stream.read(8))[0] # TODO: test this
		elif serial_type == 8:
			yield 0
		elif serial_type == 9:
			yield 1
		elif serial_type in [10, 11]:
			raise ValueError("unexpected")
		else:
			read_len, is_str = divmod(serial_type - 12, 2)
			data = stream.read(read_len)
			if len(data) != read_len:
				print(len(data), read_len, data)
				raise ValueError("blob/str underread")
			if is_str:
				yield data.decode()
			else:
				yield data

@dataclass(frozen=True)
class DatabaseHeader:
	HEADER_MAGIC = b"SQLite format 3\x00"
	MAX_EMBEDDED_PAYLOAD_FRACTION = 64
	MIN_EMBEDDED_PAYLOAD_FRACTION = 32
	LEAF_PAYLOAD_FRACTION = 32

	page_size: int
	write_version: int  # 1=legacy, 2=WAL
	read_version: int  # 1=legacy, 2=WAL
	rsvd_per_page: int
	page_count: int
	first_freelist_trunk_page: int
	freelist_page_count: int
	schema_format: int
	text_encoding: int
	user_version: int
	application_id: int
	version_valid_for_number: int
	sqlite_version_number: int

	@classmethod
	def parse(cls, stream: BinaryIO, check_magic: bool = True) -> "DatabaseHeader":
		magic = stream.read(len(DatabaseHeader.HEADER_MAGIC))
		if check_magic and magic != DatabaseHeader.HEADER_MAGIC:
			raise ValueError("not a database")
		
		page_size = parse_be_uint(stream, 2)
		if page_size < 512 or page_size > 32768 or page_size.bit_count() != 1:
			raise ValueError(f"invalid page size ({page_size})")
		
		write_version = parse_be_uint(stream, 1) # not checked
		read_version = parse_be_uint(stream, 1)
		
		if read_version != 1:  # only support "legacy" for now (not WAL)
			raise ValueError(f"unsupported read version ({read_version})")
		
		rsvd_per_page = parse_be_uint(stream, 1)

		if parse_be_uint(stream, 1) != DatabaseHeader.MAX_EMBEDDED_PAYLOAD_FRACTION:
			raise ValueError("invalid max embedded payload fraction")
		
		if parse_be_uint(stream, 1) != DatabaseHeader.MIN_EMBEDDED_PAYLOAD_FRACTION:
			raise ValueError("invalid min embedded payload fraction")
		
		if parse_be_uint(stream, 1) != DatabaseHeader.LEAF_PAYLOAD_FRACTION:
			raise ValueError("invalid leaf payload fraction")

		file_change_counter = parse_be_uint(stream, 4) # ignored
		page_count = parse_be_uint(stream, 4)
		first_freelist_trunk_page = parse_be_uint(stream, 4)
		freelist_page_count = parse_be_uint(stream, 4)
		schema_cookie = parse_be_uint(stream, 4) # ignored
		schema_format = parse_be_uint(stream, 4)

		if schema_format != 4:
			raise ValueError(f"unsupported schema format ({schema_format})")

		default_page_cache_size = parse_be_uint(stream, 4) # ignored
		vacuum_thing = parse_be_uint(stream, 4) # ignored
		if vacuum_thing != 0:
			raise ValueError("unsupported")

		text_encoding = parse_be_uint(stream, 4)
		if text_encoding != 1:
			raise ValueError(f"unsupported text encoding ({text_encoding})")
		
		user_version = parse_be_uint(stream, 4)
		incremental_vacuum = parse_be_uint(stream, 4)
		if incremental_vacuum != 0:
			raise ValueError("unsupported")
		
		application_id = parse_be_uint(stream, 4)

		rsvd = stream.read(20)
		if any(rsvd):
			raise ValueError("invalid reserved bytes")
		
		version_valid_for_number = parse_be_uint(stream, 4)
		sqlite_version_number = parse_be_uint(stream, 4)

		return cls(
			page_size=page_size,
			write_version=write_version,
			read_version=read_version,
			rsvd_per_page=rsvd_per_page,
			page_count=page_count,
			first_freelist_trunk_page=first_freelist_trunk_page,
			freelist_page_count=freelist_page_count,
			schema_format=schema_format,
			text_encoding=text_encoding,
			user_version=user_version,
			application_id=application_id,
			version_valid_for_number=version_valid_for_number,
			sqlite_version_number=sqlite_version_number,
		)

class BTreePageType(Enum):
	IDX_INTERIOR = 0x02
	TBL_INTERIOR = 0x05
	IDX_LEAF = 0x0a
	TBL_LEAF = 0x0d

@dataclass(frozen=True)
class BTreePageHeader:
	page_type: BTreePageType
	first_freeblock: int
	num_cells: int
	cell_content_start: int
	fragmented_free_bytes: int
	right_ptr: Optional[int]
	cell_offsets: List[int]
	
	@classmethod
	def parse(cls, stream: BinaryIO) -> "BTreePageHeader":
		page_type = BTreePageType(parse_be_uint(stream, 1))
		first_freeblock = parse_be_uint(stream, 2)
		num_cells = parse_be_uint(stream, 2)
		cell_content_start = parse_be_uint(stream, 2)
		if cell_content_start == 0:
			cell_content_start = 65536
		fragmented_free_bytes = parse_be_uint(stream, 1)
		if page_type in [BTreePageType.IDX_INTERIOR, BTreePageType.TBL_INTERIOR]:
			right_ptr = parse_be_uint(stream, 4)
		else:
			right_ptr = None
		
		cell_offsets = [parse_be_uint(stream, 2) for _ in range(num_cells)]

		return cls(
			page_type=page_type,
			first_freeblock=first_freeblock,
			num_cells=num_cells,
			cell_content_start=cell_content_start,
			fragmented_free_bytes=fragmented_free_bytes,
			right_ptr=right_ptr,
			cell_offsets=cell_offsets,
		)


class Database:
	table_roots: Dict[str, int]
	table_schemas: Dict[str, str]

	def __init__(self, file: BinaryIO, check_magic: bool = True) -> None:
		self.file = file
		self.hdr = DatabaseHeader.parse(file, check_magic)

		# implicitly defined schema table
		self.table_roots = {"sqlite_schema": 1}
		self.table_schemas = {
			"sqlite_schema":
			"CREATE TABLE sqlite_schema(type text, name text, tbl_name text, rootpage integer, sql text)"
		}

		# parse all of sqlite_schema
		for idx, (type_, name, tbl_name, rootpage, sql) in self.scan_table("sqlite_schema"):
			#print(idx, (type_, name, tbl_name, rootpage, sql))
			if type_ == "table":
				if name != tbl_name:
					raise ValueError("table name mismatch")
				self.table_roots[name] = rootpage
				self.table_schemas[name] = sql
				#print(name, sql)
	
	def seek_page(self, idx: int) -> None:
		self.file.seek((idx - 1) * self.hdr.page_size)

	@lru_cache(128)
	def get_btree_page(self, idx: int):
		# TODO: LRU cache this
		self.seek_page(idx)
		page = self.file.read(self.hdr.page_size)
		if len(page) != self.hdr.page_size:
			raise ValueError("page underread")
		pagestream = io.BytesIO(page)
		if idx == 1: # special case for first page, skip the db header
			pagestream.seek(100)
		hdr = BTreePageHeader.parse(pagestream)
		return hdr, page

	def scan_table(self, name: str):
		return self._scan_table_btree(self.table_roots[name])

	def _scan_table_btree(self, idx: int):
		hdr, page = self.get_btree_page(idx)
		pagestream = io.BytesIO(page)

		if hdr.page_type == BTreePageType.TBL_INTERIOR:
			for cell_offset in hdr.cell_offsets:
				pagestream.seek(cell_offset)
				left_child = parse_be_uint(pagestream, 4)
				rowid = parse_varint(pagestream)
				#print("interior", left_child, rowid)
				yield from self._scan_table_btree(left_child)
			yield from self._scan_table_btree(hdr.right_ptr)
		elif hdr.page_type == BTreePageType.TBL_LEAF:
			for cell_offset in hdr.cell_offsets:
				pagestream.seek(cell_offset)
				payload_len = parse_varint(pagestream)
				rowid = parse_varint(pagestream)
				U = self.hdr.page_size - self.hdr.rsvd_per_page
				P = payload_len
				X = U - 35
				payload = io.BytesIO()
				if P <= X:
					buf = pagestream.read(payload_len)
					if len(buf) != payload_len:
						raise ValueError("payload underread")
					payload.write(buf)
				else:
					M = ((U - 12) * 32 // 255) - 23
					K = M + ((P - M) % (U - 4))
					bytes_stored_in_leaf_page = K if K <= X else M
					buf = pagestream.read(bytes_stored_in_leaf_page)
					if len(buf) != bytes_stored_in_leaf_page:
						raise ValueError("payload underread")
					payload.write(buf)
					payload_len -= bytes_stored_in_leaf_page
					overflow_page = parse_be_uint(pagestream, 4)
					while payload_len:
						#print("overflow", overflow_page)
						self.seek_page(overflow_page)
						overflow_page = parse_be_uint(self.file, 4)
						length_to_read = min(U - 4, payload_len)
						buf = self.file.read(length_to_read)
						if len(buf) != length_to_read:
							raise ValueError("payload underread")
						payload.write(buf)
						payload_len -= length_to_read
					if overflow_page:
						raise ValueError("unexpected last overflow page")
				payload.seek(0)
				yield rowid, parse_record(payload)
		else:
			raise NotImplementedError("TODO")


if __name__ == "__main__":
	with open("test.db", "rb") as dbfile:
		db = Database(dbfile)
		for idx, (*row,) in db.scan_table("my_table"):
			print(idx, row)
