import sqlite3, sys
p = sys.argv[1]
db = sqlite3.connect('file:%s?mode=ro' % p, uri=True)
print(p, 'tags=', db.execute('SELECT COUNT(*) FROM tags').fetchone()[0],
      'refs=', db.execute('SELECT COUNT(*) FROM refs').fetchone()[0])
