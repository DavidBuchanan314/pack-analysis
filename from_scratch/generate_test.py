import sqlite3
import secrets

with sqlite3.connect("test.db") as con:
	cur = con.cursor()
	cur.execute("CREATE TABLE my_table(foo TEXT, bar INTEGER)")
	for _ in range(1000):
		cur.execute("INSERT INTO my_table(foo, bar) VALUES (?, ?)", (secrets.token_urlsafe(1+secrets.randbelow(32)), secrets.randbelow(100000)))
