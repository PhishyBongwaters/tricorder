import sqlite3, json
db = sqlite3.connect(r'file:C:\Users\macdo\.local\share\opencode/opencode.db?mode=ro', uri=True)
sess = [r[0] for r in db.execute(
    "SELECT id FROM session_v2 WHERE agent='general' AND (tokens_input+tokens_output) > 0 ORDER BY time_created")]
print('%-14s %-6s %-42s %8s %8s %10s %6s' % ('session', 'model', 'title', 'input', 'output', 'cache_read', 'tools'))
for sid in sess:
    meta = db.execute("SELECT model, title, tokens_input, tokens_output, tokens_cache_read FROM session_v2 WHERE id=?", (sid,)).fetchone()
    try:
        model = json.loads(meta[0]).get('id', '?')[:6]
    except Exception:
        model = '?'
    ntools = 0
    for (data,) in db.execute("SELECT data FROM session_message WHERE session_id=? AND type='assistant'", (sid,)):
        try:
            d = json.loads(data)
        except Exception:
            continue
        for p in d.get('content') or []:
            if isinstance(p, dict) and p.get('type') == 'tool':
                ntools += 1
    print('%-14s %-6s %-42s %8d %8d %10d %6d' % (sid[:12], model, (meta[1] or '')[:42], meta[2], meta[3], meta[4], ntools))
