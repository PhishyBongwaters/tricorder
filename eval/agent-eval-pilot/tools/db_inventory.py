import sqlite3, os, glob
for p in sorted(glob.glob(r'.tricorder/db/*.db')):
    if '-shm' in p or '-wal' in p:
        continue
    try:
        db = sqlite3.connect('file:%s?mode=ro' % p.replace('\\', '/'), uri=True)
        tables = [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        has_r = 'file_ranks' in tables
        try:
            ndef = db.execute("SELECT COUNT(*) FROM tags WHERE kind='def'").fetchone()[0]
        except Exception:
            ndef = '?'
        try:
            meta = db.execute('SELECT root, extractor_version FROM meta ORDER BY rowid DESC LIMIT 1').fetchone()
            root = (meta[0] or '')[-30:] if meta else '?'
            ev = meta[1] if meta else '?'
        except Exception:
            root, ev = '?', '?'
        print(os.path.basename(p), 'defs=%s' % ndef, 'ranks=%s' % has_r, 'ev=%s' % ev, 'root=...%s' % root)
        db.close()
    except Exception as e:
        print(os.path.basename(p), 'ERR', e)
