#!/usr/bin/env python3
"""bench_accuracy.py — issue #41 accuracy benchmark.

Does the map actually help an agent? We can't ship a live LLM agent in CI, so
this is a reproducible *proxy* of the killer metric:

  blind agent      -> must open every source file and read full_repo tokens
  with Tricorder   -> opens only the files the map steers it to (files_in_map)
                      and reads only map_tokens

For each task we assert the map narrows BOTH the file set and the token set,
and that the ground-truth identifiers are present in the map (answerable).
That is the measurable "steering" signal without a live agent.

Usage:
  python bench_accuracy.py            # all repos in bench_validity.REPOS
  python bench_accuracy.py go         # one repo
  python bench_accuracy.py --root X   # override repo parent
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
# reuse the same repo specs + stats() as the validity bench
from bench_validity import REPOS, ROOT, run, TRICORDER_EXE  # noqa: E402
from utils import discover_src_files  # noqa: E402


def blind_cost(root, scan_path, exclude_globs):
    """What a blind agent pays: every discoverable source file + all tokens."""
    files = discover_src_files(root, use_gitignore=True, exclude_globs=exclude_globs)
    # token cost of reading all of them
    total = 0
    for f in files:
        try:
            txt = open(f, encoding="utf-8", errors="replace").read()
            if txt:
                total += __import__("utils").count_tokens(txt)
        except Exception:
            continue
    return len(files), total


def main():
    p = argparse.ArgumentParser(description="tricorder accuracy (blind vs with) benchmark")
    p.add_argument("repo", nargs="?", default=None)
    p.add_argument("--root", default=None)
    args = p.parse_args()
    root_override = Path(args.root) if args.root else ROOT

    rows = []
    all_ok = True
    for repo in REPOS:
        if args.repo and args.repo != repo["name"]:
            continue
        if repo.get("monster"):
            continue  # need multi-GB checkouts; out of scope for this harness
        r = dict(repo)
        if repo["name"] == "projectm":
            r["root"] = Path(r"D:\Projects\projectm")
        elif repo["name"] == "bitburner":
            r["root"] = root_override / "bitburner-src"
        else:
            r["root"] = root_override / repo["name"]
        if not r["root"].is_dir():
            print(f"skip {repo['name']}: not present (pass --root)")
            continue

        blind_files, blind_tokens = blind_cost(str(r["root"]), r["scan_path"],
                                               r.get("exclude_globs"))
        import tempfile
        td = tempfile.mkdtemp(prefix=f"acc_{repo['name']}_")
        map_file = Path(td) / "map.txt"
        stats_args = ["--root", str(r["root"]), "--map-tokens", str(r["map_tokens"]),
                      "--exclude-untagged", "--quiet", "--output", str(map_file),
                      r["scan_path"]]
        if r.get("exclude_globs"):
            stats_args += ["--exclude-globs", *r["exclude_globs"]]
        if r.get("pre_index"):
            stats_args += ["--pre-index", r["pre_index"]]
        run(TRICORDER_EXE, stats_args)
        map_text = map_file.read_text(encoding="utf-8", errors="replace") if map_file.exists() else ""
        map_files = len({ln for ln in map_text.splitlines()
                         if ln.strip().endswith(" lines)")})
        map_tokens = __import__("utils").count_tokens(map_text) if map_text else 0

        # ground truth present?
        from bench_validity import norm
        missing = []
        for t in repo["tasks"]:
            for ident in t["ground_truth"]:
                if norm(ident) not in norm(map_text):
                    missing.append(ident)
        answerable = not missing
        files_narrow = map_files < blind_files
        tokens_narrow = map_tokens < blind_tokens
        ok = answerable and files_narrow and tokens_narrow
        all_ok = all_ok and ok
        rows.append({
            "repo": repo["name"],
            "blind_files": blind_files, "with_files": map_files,
            "blind_tokens": blind_tokens, "with_tokens": map_tokens,
            "answerable": answerable, "files_narrow": files_narrow,
            "tokens_narrow": tokens_narrow, "ok": ok,
        })
        print(f"{repo['name']:<12} files {blind_files}->{map_files}  "
              f"tokens {blind_tokens}->{map_tokens}  answerable={answerable} ok={ok}")
        import shutil
        shutil.rmtree(td, ignore_errors=True)

    print()
    print(json.dumps(rows, indent=2))
    print("RESULT:", "ALL NARROW + ANSWERABLE" if all_ok else "SOME FAIL")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
