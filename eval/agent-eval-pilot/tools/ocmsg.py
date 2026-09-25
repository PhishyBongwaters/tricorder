import sqlite3, json
db = sqlite3.connect(r'file:C:\Users\macdo\.local\share\opencode/opencode.db?mode=ro', uri=True)
row = db.execute("SELECT data FROM session_message WHERE session_id LIKE 'ses_f274e3bd2%' AND seq=5").fetchone()[0]
d = json.loads(row)
print('tokens:', json.dumps(d.get('tokens')))
print('cost:', d.get('cost'))
print('finish:', d.get('finish'))
for p in d.get('content') or []:
    if p.get('type') != 'text':
        print('NON-TEXT part:', json.dumps(p)[:400])
