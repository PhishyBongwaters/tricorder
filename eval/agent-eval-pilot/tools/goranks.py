import sqlite3
db = sqlite3.connect(r'.tricorder/db/go.db')
rows = db.execute('SELECT rel_file, rank FROM file_ranks ORDER BY rank DESC LIMIT 12').fetchall()
allr = [r[0] for r in db.execute('SELECT rank FROM file_ranks')]
print('n=', len(allr), 'sum=', round(sum(allr), 4), 'max=', round(max(allr), 6), 'min=', round(min(allr), 6))
print('top12:')
for f, r in rows:
    print('  %.6f %s' % (r, f))
t = open(r'C:\Users\macdo\AppData\Local\Temp\opencode\go_map.txt', encoding='utf-8').read()
print('--- MAP head ---')
print(t[:700])
