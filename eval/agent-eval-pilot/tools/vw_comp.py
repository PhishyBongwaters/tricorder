import sqlite3
from collections import Counter
db = sqlite3.connect(r'.tricorder/db/vaultwarden.db')
files = [r[0] for r in db.execute('SELECT DISTINCT rel_file FROM tags')]
print('tagged files:', len(files))
print('by ext:', Counter(f.rsplit('.', 1)[-1] for f in files))
print('file_state:', db.execute('SELECT COUNT(*) FROM file_state').fetchone()[0])
print('flags:', Counter(r[0] for r in db.execute('SELECT reason FROM file_flags')))
print('defs:', db.execute("SELECT COUNT(*) FROM tags WHERE kind='def'").fetchone()[0])
