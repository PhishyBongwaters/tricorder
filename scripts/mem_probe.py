"""Memory probe for tricorder map build. Traces peak + per-stage RSS/alloc.
No source changes; runs the real pipeline off an existing repo root.
"""
import sys, os, time, tracemalloc, io, contextlib, json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from core import Tricorder
from utils import count_tokens, read_text

def rss_mb():
    try:
        import psutil
        return psutil.Process().memory_info().rss / 1e6
    except Exception:
        return 0.0

def stage(name):
    cur, peak = tracemalloc.get_traced_memory()
    print(f"[{name}] rss={rss_mb():.1f}MB traced_current={cur/1e6:.1f}MB traced_peak={peak/1e6:.1f}MB", flush=True)

def main():
    root = sys.argv[1]
    map_tokens = int(sys.argv[2]) if len(sys.argv) > 2 else 20000
    full = "--full" in sys.argv
    max_files = int(sys.argv[sys.argv.index("--max-files")+1]) if "--max-files" in sys.argv else 2000

    from utils import discover_src_files
    other = discover_src_files(root, use_gitignore=True)[:max_files]
    print(f"files: {len(other)} (capped {max_files})", flush=True)

    t = Tricorder(
        map_tokens=map_tokens, root=root,
        token_counter_func=count_tokens, file_reader_func=read_text,
        output_handler_funcs={'info': lambda *a: None, 'warning': lambda *a: None, 'error': lambda *a: None},
        full_map=full, refresh="auto",
    )

    tracemalloc.start()
    snap = tracemalloc.take_snapshot()
    stage("init")

    # Stage 1: get_ranked_tags (full tree walk + parse + graph + pagerank)
    t0 = time.time()
    ranked_tags, report = t.get_ranked_tags([], other)
    print(f"[get_ranked_tags] {time.time()-t0:.1f}s tags={len(ranked_tags)} defs={report.definition_matches} files_considered={report.total_files_considered}", flush=True)
    stage("after get_ranked_tags")
    snap = tracemalloc.take_snapshot()

    # Top allocations so far
    for st in snap.statistics('lineno')[:8]:
        print("   ", st, flush=True)

    # Stage 2: build the map tree (to_tree) -- this is where output string is assembled
    t0 = time.time()
    ntok = 0
    # emulate full_map path
    if full:
        chat_rel = set()
        from importance import filter_important_files
        imp = filter_important_files([t.get_rel_fname(f) for f in other])
        tree = t.to_tree(ranked_tags, chat_rel, imp)
        print(f"[to_tree full] {time.time()-t0:.1f}s chars={len(tree)} tokens={count_tokens(tree)}", flush=True)
    stage("after to_tree")
    snap = tracemalloc.take_snapshot()
    for st in snap.statistics('lineno')[:8]:
        print("   TRACE:", st, flush=True)

    tracemalloc.stop()

if __name__ == "__main__":
    main()