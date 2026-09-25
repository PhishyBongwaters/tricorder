import sqlite3
db=sqlite3.connect('file:.tricorder/db/go.db?mode=ro', uri=True)
print('defs', db.execute("SELECT COUNT(*) FROM tags WHERE kind='def'").fetchone()[0])
print('refs', db.execute("SELECT COUNT(*) FROM tags WHERE kind='ref'").fetchone()[0])
print('files', db.execute('SELECT COUNT(DISTINCT rel_file) FROM tags').fetchone()[0])
print('ranked_files', db.execute('SELECT COUNT(*) FROM file_ranks').fetchone()[0])
print('stamp', db.execute('SELECT * FROM ranks_stamp').fetchall()[:2])
print('meta', db.execute('SELECT root FROM meta ORDER BY rowid DESC LIMIT 1').fetchone())
