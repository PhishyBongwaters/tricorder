import sqlite3, os
for p in [r'D:\Projects\Tricorder-Testing-Repos\bench_temp\eval-go-v13.db',
          r'D:\Projects\tricorder\.tricorder\db\go.db']:
    print('===', p, os.path.getsize(p))
    db=sqlite3.connect('file:%s?mode=ro' % p.replace('\\','/'), uri=True)
    tables=[r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")]
    print('tables:', tables)
    print('defs', db.execute("SELECT COUNT(*) FROM tags WHERE kind='def'").fetchone()[0])
    try:
        print('fileranks', db.execute('SELECT COUNT(*) FROM file_ranks').fetchone()[0])
    except Exception as e:
        print('fileranks ERR', e)
    try:
        print('stamp', db.execute('SELECT * FROM ranks_stamp').fetchall())
    except Exception as e:
        print('stamp ERR', e)
    print('meta', db.execute('SELECT root, signature, extractor_version FROM meta ORDER BY rowid DESC LIMIT 1').fetchone())
