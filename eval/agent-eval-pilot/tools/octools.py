import sqlite3, json
db = sqlite3.connect(r'file:C:\Users\macdo\.local\share\opencode/opencode.db?mode=ro', uri=True)
# shell tool parts in r02 leg 2 (baseline = mostly shell): content present? how large?
n_tool = n_with_content = maxlen = 0
kinds = {}
for (data,) in db.execute("SELECT data FROM session_message WHERE session_id LIKE 'ses_f27380e37%' AND type='assistant'"):
    try:
        d = json.loads(data)
    except Exception:
        continue
    for p in d.get('content') or []:
        if isinstance(p, dict) and p.get('type') == 'tool':
            n_tool += 1
            st = p.get('state') or {}
            name = p.get('name', '?')
            kinds[name] = kinds.get(name, 0) + 1
            c = st.get('content')
            if c:
                n_with_content += 1
                s = json.dumps(c)
                maxlen = max(maxlen, len(s))
print('tool parts:', n_tool, 'with content:', n_with_content, 'max content chars:', maxlen)
print('by tool:', kinds)
