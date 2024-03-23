import sqlite3
import zstandard
from typing import List, Tuple
from enum import Enum
import os
import io

PACK_MAGIC = b"Pack\0 \0\0\0\0\0\0\0\0\0\0"
SQLITE3_MAGIC = b"SQLite format 3\0"

class MagicFixup:
	"""
	This is an ugly hack to hot-patch the file's magic bytes on-disk
	"""

	def __init__(self, path: str) -> None:
		self.path = path
	
	def __enter__(self) -> "MagicFixup":
		with open(self.path, "rb+") as f:
			header = f.read(16)
			if header != PACK_MAGIC:
				raise ValueError("bad file magic")
			f.seek(0)
			f.write(SQLITE3_MAGIC)
	
	def __exit__(self, *_):
		with open(self.path, "rb+") as f:
			header = f.read(16)
			if header != SQLITE3_MAGIC:
				raise ValueError("bad file magic")
			f.seek(0)
			f.write(PACK_MAGIC)

class ItemKind(Enum):
	FILE = 0
	DIR = 1

def get_extents(cur: sqlite3.Cursor, id_: int) -> List[Tuple[int, int, int, int]]: # itempos, content id, contentpos, size
	return list(cur.execute(
		"""
			SELECT ItemPosition, Content, ContentPosition, Size
			FROM ItemContent
			WHERE Item=?
			ORDER BY ItemPosition
		""",
		(id_,)
	).fetchall())

def read_file(cur: sqlite3.Cursor, id_: int) -> bytes: # just load the whole file into memory
	buf = io.BytesIO()
	for itempos, content_id, contentpos, size in get_extents(cur, id_):
		assert(itempos == 0) # TODO: find out if this is index or byte offset
		with con.blobopen("Content", "Value", content_id) as blob:
			blob.seek(0)
			decompressed_blob = zstandard.decompress(blob.read()) # XXX: decompress the whole blob because...
			buf.write(decompressed_blob[contentpos:contentpos+size]) # XXX: wtf???? offsets are into the decompressed buffer???
	return buf.getvalue()

def walk_dir(cur: sqlite3.Cursor, parent: int, path: List[str]): # recursive
	for id_, kind, name in cur.execute(
		"SELECT ID, Kind, Name FROM Item WHERE Parent=?",
		(parent,)
	).fetchall():

		kind = ItemKind(kind)
		this_path = path + [name]
		if kind == ItemKind.FILE:
			strpath = "/".join(this_path)
			file_size = sum(x[3] for x in get_extents(cur, id_))
			print(f"{strpath!r} - {file_size} bytes")
			file_data = read_file(cur, id_)
			open(strpath, "wb").write(file_data)
		elif kind == ItemKind.DIR:
			strpath = "/".join(this_path) + "/"
			os.makedirs(strpath, exist_ok=True)
			print(repr(strpath))
			walk_dir(cur, id_, this_path)
		else:
			raise ValueError("Unknown item kind {kind}")

if __name__ == "__main__":
	import sys

	pack_path = sys.argv[1]
	with MagicFixup(pack_path), sqlite3.connect(pack_path) as con:
		cur = con.cursor()
		walk_dir(cur, 0, [])
