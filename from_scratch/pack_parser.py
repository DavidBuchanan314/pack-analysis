
from typing import Dict, List, BinaryIO
import os
import io
import zstandard

from sqlite_parser import Database

class PackReader:
	def __init__(self, file: BinaryIO) -> None:
		self.db = Database(file, check_magic=False)

		# build in-memory index of Items
		self.dir_kids: Dict[int, List[int]] = {}
		self.kinds: Dict[int, int] = {}
		self.names: Dict[int, str] = {}
		for idx, (_, parent, kind, name) in self.db.parse_table("Item"):
			if parent not in self.dir_kids:
				self.dir_kids[parent] = []
			self.dir_kids[parent].append(idx)
			self.kinds[idx] = kind
			self.names[idx] = name
		
		# build in-memory index if ItemContents
		self.item_contents: Dict[int, List[tuple]] = {}
		for idx, (_, item, itempos, content, contentpos, size) in self.db.parse_table("ItemContent"):
			if item not in self.item_contents:
				self.item_contents[item] = []
			self.item_contents[item].append((itempos, content, contentpos, size))
		
		# possibly unnecessary, but make sure the itempos's are in ascending order
		for v in self.item_contents.values():
			v.sort()
	
	def get_content(self, idx: int) -> bytes:
		# TODO: LRU cache this!
		# TODO: proper btree search algorithm (with page cache), not linear scan!!!!
		for this_id, (_, value) in self.db.parse_table("Content"):
			if this_id == idx:
				return zstandard.decompress(value)
		raise KeyError("not found")

	def extract_tree(self, idx: int = 0, path: list = []):
		for child in self.dir_kids[idx]:
			this_path = path + [self.names[child]]
			strpath = "/".join(this_path)
			kind = self.kinds[child]
			if kind == 0:
				print(repr(strpath))
				with open(strpath, "wb") as f:
					for itempos, content, contentpos, size in self.item_contents[child]:
						if f.tell() != itempos:
							raise Exception("idk")
						f.write(self.get_content(content)[contentpos:contentpos+size])
			elif kind == 1:
				strpath += "/"
				os.makedirs(strpath, exist_ok=True)
				print(repr(strpath))
				self.extract_tree(child, this_path)

if __name__ == "__main__":
	with open("/home/david/Downloads/MediaKit.pack", "rb") as dbfile:
		pack = PackReader(dbfile)
		pack.extract_tree()
