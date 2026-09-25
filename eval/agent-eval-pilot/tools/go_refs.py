import sqlite3, os
p = r'D:\Projects\Tricorder-Testing-Repos\bench_temp\eval-go-v13.db'
db = sqlite3.connect('file:%s?mode=ro' % p.replace('\\', '/'), uri=True)
print('refs edges', db.execute('SELECT COUNT(*) FROM refs').fetchone()[0])
print('file_state', db.execute('SELECT COUNT(*) FROM file_state').fetchone()[0])
print('stop_names', db.execute('SELECT COUNT(*) FROM stop_names').fetchone()[0])
