import sqlite3, json
db = sqlite3.connect(r'file:C:\Users\macdo\.local\share\opencode/opencode.db?mode=ro', uri=True)
legs = {
 'A-G5': 'ses_f31a9adad', 'B-G5': 'ses_f30fb5f26',
 'A-G1': 'ses_f30f8aff', 'B-G1': 'ses_f30f2a15',
 'A-G1Q': 'ses_f302bf44',
 'A-G3': 'ses_f30f0653', 'B-G3': 'ses_f30eac39',
 'A-Q1': 'ses_f30bfb01', 'B-Q1': 'ses_f30bab1c',
 'A-Q2a1': 'ses_f3065b79', 'A-Q2a2': 'ses_f304fb6c', 'B-Q2': 'ses_f305c066',
 'A-Q3': 'ses_f3047b03', 'B-Q3': 'ses_f30459c3',
 'A-Q4': 'ses_f303db78', 'B-Q4': 'ses_f303836f',
}
print('%-7s %8s %8s %10s %10s %8s' % ('leg', 'fresh_in', 'output', 'cache_read', 'peak_ctx', 'cache%'))
for leg, sid in legs.items():
    tot_in = tot_out = tot_cache = peak = 0
    n = 0
    for (data,) in db.execute("SELECT data FROM session_message WHERE session_id LIKE ? AND type='assistant'", (sid + '%',)):
        try:
            t = json.loads(data).get('tokens') or {}
        except Exception:
            continue
        i, o = t.get('input', 0), t.get('output', 0)
        c = (t.get('cache') or {}).get('read', 0)
        tot_in += i; tot_out += o; tot_cache += c
        peak = max(peak, i + c)
        n += 1
    ctx = tot_in + tot_cache
    print('%-7s %8d %8d %10d %10d %7.1f%%' % (leg, tot_in, tot_out, tot_cache, peak, 100.0 * tot_cache / ctx if ctx else 0))
