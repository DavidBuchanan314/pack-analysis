# pack-analysis

The [`pack`](https://github.com/PackOrganization/Pack) file format is an interesting new file archive format. However, they forgot to document the format, so I'll do my best to fill in the gaps.

This document is a work-in-progress based on reverse-engineering (I don't know Pascal), and may contain incorrect information.

A `.pack` file is an sqlite3 database, but with the magic bytes of `Pack\0 ` rather than the usual `SQLite format 3`. This makes it impossible to use standard sqlite3 bindings to work with pack files. You'll need to build your own sqlite if you want seamless support (build with custom [`SQLITE_FILE_HEADER`](https://github.com/sqlite/sqlite/blob/378bf82e2bc09734b8c5869f9b148efe37d29527/src/btreeInt.h#L236-L250)).

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

Files and directories are listed in the `Item` table.

The `ItemContent` table describes where to find the actual file contents, within the `Value` blob(s).

There are no indexes(!).
