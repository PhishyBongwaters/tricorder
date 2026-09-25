import sqlite3
db = sqlite3.connect(r'file:C:\Users\macdo\.local\share\opencode/opencode.db?mode=ro', uri=True)
print('--- all general-agent subagent sessions ---')
for r in db.execute("SELECT id, parent_id, model, tokens_input, tokens_output, tokens_cache_read, title FROM session_v2 WHERE agent='general' ORDER BY time_created"):
    print(r[5] and (r[0][:13], r[2][:40] if r[2] else None, r[3], r[4], r[5], (r[6] or '')[:44]) or r)
