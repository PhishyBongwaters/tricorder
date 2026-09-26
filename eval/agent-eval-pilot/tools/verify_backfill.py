import sqlite3
# 2026-09-26: rails want 3490 -> 3456 after T1 rebuild (fixture/testdata
# subtrees + fingerprinted assets excluded from discovery; backup of the
# pre-T1 DB at temp rails-pre-t1-backup.db).
for p, want in [('.tricorder/db/go.db', 10736), ('.tricorder/db/rails.db', 3456)]:
    db = sqlite3.connect('file:%s?mode=ro' % p, uri=True)
    n = db.execute('SELECT COUNT(*) FROM file_ranks').fetchone()[0]
    stamp = db.execute('SELECT * FROM ranks_stamp').fetchall()
    meta = db.execute('SELECT signature, extractor_version FROM meta ORDER BY rowid DESC LIMIT 1').fetchone()
    print(p, 'ranks=%d want~%d fresh=%s' % (n, want, stamp and (stamp[0][0], stamp[0][1]) == (meta[0], meta[1])))
    db.close()
