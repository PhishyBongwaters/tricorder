import sqlite3, json
db = sqlite3.connect(r'file:C:\Users\macdo\.local\share\opencode/opencode.db?mode=ro', uri=True)
sid = 'ses_f273572d1ffeN3f6yf2LRARvOC'
cum_in = cum_out = cum_cache = 0
ntools = 0
first_hit = None
rows = db.execute("SELECT seq, data FROM session_message WHERE session_id=? AND type='assistant' ORDER BY seq", (sid,)).fetchall()
for seq, data in rows:
    try:
        d = json.loads(data)
    except Exception:
        continue
    t = d.get('tokens') or {}
    cum_in += t.get('input', 0)
    cum_out += t.get('output', 0)
    cum_cache += (t.get('cache') or {}).get('read', 0)
    for p in d.get('content') or []:
        if isinstance(p, dict) and p.get('type') == 'tool':
            ntools += 1
            blob = json.dumps(p.get('state') or {})
            if first_hit is None and 'buildssa' in blob and 'ssa.go' in blob and '302' in blob:
                first_hit = (ntools, seq, cum_in, cum_out, cum_cache)
print('total tool parts:', ntools)
if first_hit:
    n, s, i, o, c = first_hit
    print('first buildssa-ssa.go-302 evidence at tool #%d (msg seq %d): in=%d out=%d cache=%d total=%d' % (n, s, i, o, c, i + o + c))
tot = db.execute("SELECT tokens_input, tokens_output, tokens_cache_read FROM session_v2 WHERE id=?", (sid,)).fetchone()
print('session total: in=%d out=%d cache=%d total=%d' % (tot[0], tot[1], tot[2], tot[0] + tot[1] + tot[2]))
