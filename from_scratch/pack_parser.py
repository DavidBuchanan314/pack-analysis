
from typing import Dict, List, BinaryIO
import os
from functools import lru_cache

import zstandard

from sqlite_parser import Database

class PackReader:
	def __init__(self, file: BinaryIO) -> None:
		self.db = Database(file, check_magic=False)

		# build in-memory index of Items
		self.dir_kids: Dict[int, List[int]] = {}
		self.kinds: Dict[int, int] = {}
		self.names: Dict[int, str] = {}
		for idx, (_, parent, kind, name) in self.db.scan_table("Item"):
			if parent not in self.dir_kids:
				self.dir_kids[parent] = []
			self.dir_kids[parent].append(idx)
			self.kinds[idx] = kind
			self.names[idx] = name
		
		# build in-memory index of ItemContents
		self.item_contents: Dict[int, List[tuple]] = {}
		for _, (_, item, itempos, content, contentpos, size) in self.db.scan_table("ItemContent"):
			if item not in self.item_contents:
				self.item_contents[item] = []
			self.item_contents[item].append((itempos, content, contentpos, size))
		
		# possibly unnecessary, but make sure the itempos's are in ascending order
		for v in self.item_contents.values():
			v.sort()
		
		# reusable compression object for marginally better perf (supposedly)
		self.zstd = zstandard.ZstdDecompressor()
	
	@lru_cache(4) # shouldn't need a big number here, if we're extracting files in order
	def get_content(self, idx: int) -> bytes:
		_, value = self.db.lookup_row("Content", idx)
		return self.zstd.decompress(value)

	def extract_tree(self, idx: int = 0, path: list = ["/tmp"]):
		for child in self.dir_kids.get(idx, []):
			this_path = path + [self.names[child]]
			strpath = "/".join(this_path)
			kind = self.kinds[child]
			if kind == 0:
				print(repr(strpath))
				with open(strpath, "wb") as f:
					for itempos, content, contentpos, size in self.item_contents.get(child, []):
						if f.tell() != itempos:
							raise Exception("idk")
						region = self.get_content(content)[contentpos:contentpos+size]
						if len(region) != size:
							raise Exception("idk")
						f.write(region)
			elif kind == 1:
				strpath += "/"
				os.makedirs(strpath, exist_ok=True)
				print(repr(strpath))
				self.extract_tree(child, this_path)

if __name__ == "__main__":
	with open("/home/david/Downloads/MediaKit.pack", "rb") as dbfile:
	#with open("linux.pack", "rb") as dbfile:
		pack = PackReader(dbfile)
		pack.extract_tree()
