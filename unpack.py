import sqlite3
from typing import List

PACK_MAGIC = b"Pack\0 \0\0\0\0\0\0\0\0\0\0"
SQLITE3_MAGIC = b"SQLite format 3\0"

class MagicFixup:
	def __init__(self, path: str) -> None:
		self.path = path
	
	def __enter__(self) -> "MagicFixup":
		with open(self.path, "rb+") as f:
			header = f.read(16)
			if header != PACK_MAGIC:
				raise ValueError("bad file magic")
			f.seek(0)
			f.write(SQLITE3_MAGIC)
	
	def __exit__(self, exc_type, exc_val, exc_tb):
		with open(self.path, "rb+") as f:
			header = f.read(16)
			if header != SQLITE3_MAGIC:
				raise ValueError("bad file magic")
			f.seek(0)
			f.write(PACK_MAGIC)

def printdir(cur: sqlite3.Cursor, parent: int, path: List[str]): # recursive
	for id_, kind, name in cur.execute("SELECT ID, Kind, Name FROM Item WHERE Parent=?", (parent,)).fetchall():
		this_path = path + [name]
		if kind == 0:  # file
			print(repr("/".join(this_path)))
		elif kind == 1:  # dir
			print(repr("/".join(this_path) + "/"))
			printdir(cur, id_, this_path)
		else:
			raise ValueError("Unknown item kind {kind}")

if __name__ == "__main__":
	import sys

	pack_path = sys.argv[1]
	with MagicFixup(pack_path), sqlite3.connect(pack_path) as con:
		cur = con.cursor()
		printdir(cur, 0, [])
