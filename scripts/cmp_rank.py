import sys, os
sys.path.insert(0, "D:/projects/tricorder")
os.chdir("D:/projects/tricorder")
from core import Tricorder
from utils import count_tokens, read_text, discover_src_files

def rss():
    try:
        import psutil
        return psutil.Process().memory_info().rss/1e6
    except Exception:
        return 0.0

def run(root, max_files, use_db):
    from utils import discover_src_files as ds
    other = ds(root, use_gitignore=True)[:max_files]
    t = Tricorder(map_tokens=20000, root=root, token_counter_func=count_tokens,
                  file_reader_func=read_text,
                  output_handler_funcs={'info':lambda *a:None,'warning':lambda *a:None,'error':lambda *a:None},
                  full_map=False, refresh="auto", use_db=use_db, db_path=None)
    rt, rep = t.get_ranked_tags([], other)
    # order string
    order = [(round(r,12), t.get_rel_fname(tg.fname), tg.line, tg.name) for r,tg in rt]
    return order, rep, rss()

if __name__ == "__main__":
    root = sys.argv[1]; n = int(sys.argv[2])
    # force networkx pagerank path even w/o scipy: default uses uniform (chat empty). Compare db (real) vs default.
    a, ra, ma = run(root, n, use_db=False)
    b, rb, mb = run(root, n, use_db=True)
    print("default len", len(a), "db len", len(b))
    print("SAME ORDER:", a == b)
    if a != b:
        # find first divergence
        for i,(x,y) in enumerate(zip(a,b)):
            if x!=y:
                print("first diff idx", i)
                print("  default:", x)
                print("  db:     ", y)
                break
        print("rank sets equal(defloats):", [x[0] for x in a][:5], [x[0] for x in b][:5])