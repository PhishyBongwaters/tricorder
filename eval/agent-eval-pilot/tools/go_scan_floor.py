import sqlite3, time
p = r'D:\Projects\Tricorder-Testing-Repos\bench_temp\eval-go-v13.db'
db = sqlite3.connect('file:%s?mode=ro' % p.replace('\\', '/'), uri=True)
t0 = time.perf_counter()
n = db.execute('SELECT COUNT(*) FROM refs').fetchone()[0]
t1 = time.perf_counter()
print('count(*) over %d refs edges: %.1fs' % (n, t1 - t0))
t0 = time.perf_counter()
# Floor proxy for one pagerank iteration: full-table grouped aggregation
rows = db.execute('SELECT to_file, SUM(1.0) FROM refs GROUP BY to_file').fetchall()
t1 = time.perf_counter()
print('group-by over refs -> %d nodes: %.1fs' % (len(rows), t1 - t0))
