# pack-analysis

The [`pack`](https://github.com/PackOrganization/Pack) file format is an interesting new file archive format. However, they forgot to document the format, so I'll do my best to fill in the gaps.

This document is a work-in-progress based on reverse-engineering (I don't know Pascal), and may contain incorrect information.

A `.pack` file is an sqlite3 database, but with the magic bytes of `Pack\0 ` rather than the usual `SQLite format 3`. This makes it impossible to use standard sqlite3 bindings to work with pack files. You'll need to build your own sqlite if you want seamless support (build with custom [`SQLITE_FILE_HEADER`](https://github.com/sqlite/sqlite/blob/378bf82e2bc09734b8c5869f9b148efe37d29527/src/btreeInt.h#L236-L250)).

There is no version field (unless the magic bytes act as one, I guess).

`unpack.py` implements a crude extraction utility (which dumps all files into the cwd)

Beware, my implementation is very vulnerable to unbounded recursion and/or decompression bombs. I haven't checked whether the reference implementation is, too.

### Schema

There are 3 tables, `Content`, `Item`, and `ItemContent`. Their schemae are as follows:

```sql
CREATE TABLE Content(
	ID INTEGER PRIMARY KEY,
	Value BLOB
);
```

```sql
CREATE TABLE Item(
	ID INTEGER PRIMARY KEY,
	Parent INTEGER,
	Kind INTEGER,
	Name TEXT
);
```

```sql
CREATE TABLE ItemContent(
	ID INTEGER PRIMARY KEY,
	Item INTEGER,
	ItemPosition INTEGER,
	Content INTEGER,
	ContentPosition INTEGER,
	Size INTEGER
);
```

The data is stored in the `Value` column of the Content table, with potentially many files stored in a single blob.

Files and directories are listed in the `Item` table. The root directory is implicitly ID 0 (Items with Parent=0 are therefore in the root directory). You'd probably want to put an index on `Parent`!

The `ItemContent` table describes where to find the actual file contents, within the `Value` blob(s).

Except wait, no it doesn't! The offsets given in `ItemContent` refer to *decompressed* offsets. This means if the file you're looking for is midway through a blob, you need to decompress it from the start. This isn't quite as bad as it sounds, because `pack` seems to limit blobs to 8MB (uncompressed size) each.

There are no indexes(!).
