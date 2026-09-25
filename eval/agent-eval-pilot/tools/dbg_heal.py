import os, shutil, sys, tempfile
from pathlib import Path
sys.path.insert(0, '.')
from core import Tricorder
from database import DBStore
from utils import stat_fingerprint

tmp = Path(tempfile.mkdtemp(prefix='dbg_heal_'))
(tmp / 'a.py').write_text('def foo():\n    return 1\n', encoding='utf-8')
(tmp / 'b.py').write_text('from a import foo\ndef bar():\n    return foo()\n', encoding='utf-8')
db_path = str(tmp / 'idx.db')
msgs = []
kw = dict(root=str(tmp), use_db=True, db_path=db_path, verbose=False,
          output_handler_funcs={'info': msgs.append, 'warning': msgs.append, 'error': msgs.append})
files = [os.path.join(str(tmp), f) for f in ('a.py', 'b.py')]
tc = Tricorder(**kw)
tree, _ = tc.get_ranked_tags_map_uncached([], files, 2048)
print('scan tree?', bool(tree))
print('msgs:', msgs)
tc.close()

db = DBStore(db_path)
print('file_state:', db.get_file_state())
for f in files:
    st = os.stat(f)
    print(os.path.basename(f), 'cur=', stat_fingerprint(st))
db.conn.execute('DELETE FROM file_ranks')
db.conn.execute('DELETE FROM ranks_stamp')
db.conn.commit()
print('fresh after stale:', db.ranks_fresh())
db.close()

msgs2 = []
kw2 = dict(kw)
kw2['output_handler_funcs'] = {'info': msgs2.append, 'warning': msgs2.append, 'error': msgs2.append}
tc2 = Tricorder(**kw2)
tree2, _ = tc2.get_ranked_tags_map_uncached([], files, 2048)
print('serve2 tree?', bool(tree2))
print('msgs2:', msgs2)
print('fresh after serve2:', tc2._db_store.ranks_fresh())
tc2.close()
shutil.rmtree(tmp, ignore_errors=True)
