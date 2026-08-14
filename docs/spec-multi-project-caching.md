# SPEC: Multi-Project Caching & Signature-Based Cache Validation

**Date:** 2026-08-14
**Status:** LOCKED — all decisions finalized
**Scope:** Plugin cache lifecycle changes for multi-project workflows

---

## Problem

Most users work on multiple projects. The plugin locks to one `active_project`
in config, `on_session_start` always rebuilds (even if nothing changed),
and `/tricorder root` auto-scans with no awareness of existing cache.

## Goal

1. Config is the single source of truth for "active project" (no in-memory
   divergence — one project, one config key, no confusion).
2. Caches persist per-project (already true via hash-keyed files).
3. Cache validity is **content-aware** (stat-based signature), not time-based
   (mtime TTL). A map is valid until the project actually changes.
4. `on_session_start` skips rebuild if signature matches.
5. `/tricorder root <path>` writes config, checks cache. Auto-rebuilds if
   stale/missing. Reports "cache ready" if valid.
6. `/tricorder scan` forces rebuild (ignores signature).
7. `/tricorder status` shows active project + cache state + all cached projects.

---

## Decisions (locked)

### D1: File list source for signature
Use `discover_src_files` from utils.py with current `exclude_globs` from config.
Same file list the scan sees. If globs change → different file set → different
signature → rebuild. Transparent, no special handling needed.

### D2: When signature is computed
`on_session_start`, `pre_llm_call` first turn, `/tricorder root`, `/tricorder
status`. One stat-walk per check (~5-10ms for any realistic repo). stat is a
syscall, not a file read — cheap.

### D3: Meta JSON shape
Add `project_sig` field. Keep meta file mtime for age display in `/tricorder
status`. Drop `_MAP_FRESH_SECONDS` entirely — no mtime TTL, no
`cache_ttl_seconds` config knob. The signature replaces all of that.

```json
{
  "project_root": "D:/Projects/tricorder",
  "map_file": "C:\\Users\\macdo\\AppData\\Local\\hermes\\tricorder\\c09c29b32c48.map",
  "lines": 200,
  "tokens_approx": 2800,
  "project_sig": "a1b2c3d4e5f6a1b2"
}
```

### D4: `pre_llm_call` behavior
Signature matches → inject from cache (no rebuild). Signature differs or
cache missing → rebuild + inject. Same first-turn-only injection policy.

### D5: `/tricorder root` behavior
Write config → compute signature → if valid: "cache ready (N lines, age)."
If stale/missing: **auto-rebuild** → "rebuilt (N lines)." User-initiated
action — they expect the map to be ready. `/tricorder scan` is for force
rebuilds when they explicitly want fresh.

### D6: `exclude_globs` change invalidation
Signature always uses current config globs. Different globs → different file
set → different signature → rebuild happens automatically on next access.
No explicit invalidation needed.

---

## Cache Validation Design

### Stat-based signature

The stat-hash lives in the CLI (`tricorder.py`), not the plugin. The plugin
shells to `tricorder.exe --signature-only` and reads the hex from stdout.

**CLI side (`tricorder.py`) — the actual implementation:**

```python
# In tricorder.py, reuses discover_src_files from utils.py:
def compute_signature(root: str, exclude_globs: list) -> str:
    """Stat-based signature: path + size + mtime per source file, sha256'd.

    ponytail: stat-based (path+size+mtime), not content hash.
    Misses: content changed but size+mtime unchanged (practically never
    on real filesystems). Upgrade path: content hash if this ever bites.
    """
    h = hashlib.sha256()
    files = sorted(discover_src_files(root, use_gitignore=True,
                                       exclude_globs=exclude_globs))
    for fpath in files:
        try:
            st = os.stat(fpath)
            h.update(f"{fpath}:{st.st_size}:{int(st.st_mtime)}".encode())
        except OSError:
            continue
    return h.hexdigest()[:16]
```

```python
# tricorder.py argparse + handler for --signature-only:
if args.signature_only:
    sig = compute_signature(args.root, args.exclude_globs)
    print(sig)
    sys.exit(0)
```

**Plugin side (`__init__.py`) — thin subprocess wrapper:**

```python
def _project_signature(project_root: str) -> str:
    """Shell to CLI for the stat-hash. Returns 16 hex chars or '' on failure."""
    cmd = [_TRICORDER_CLI, "--root", project_root, "--signature-only", "."]
    globs = _exclude_globs()
    if globs:
        cmd += ["--exclude-globs"] + globs
    try:
        r = subprocess.run(cmd, capture_output=True, text=True,
                           timeout=30, check=False)
        return r.stdout.strip()[:16]
    except Exception:
        return ""
```

### Cache validity check

```python
def _is_cache_valid(project_root: str) -> bool:
    """Cache is valid if meta exists and stored signature matches current."""
    meta = _read_meta(project_root)
    cached_sig = meta.get("project_sig")
    if not cached_sig:
        return False  # no signature → rebuild
    return cached_sig == _project_signature(project_root)
```

Replaces `_is_fresh()` entirely. No mtime TTL. No arbitrary threshold.

---

## Current State (what exists today)

### Cache layout
```
~/.hermes/tricorder/
  <sha256[:12]>.map    # the T0 map text
  <sha256[:12]>.json   # meta: {project_root, map_file, lines, tokens_approx}
```

### Freshness (current — to be replaced)
```python
_MAP_FRESH_SECONDS = 60  # REJECTED — replaced by signature

def _is_fresh(project_root: str) -> bool:  # DELETED
    # meta file mtime < 60s ago → fresh
```

### Flow today vs. proposed

| Touch point | Today | Proposed |
|-------------|-------|----------|
| `on_session_start` | Always `build_map(root)` | If `_is_cache_valid(root)` → skip. Else rebuild. |
| `pre_llm_call` first turn | If `_is_fresh(root)` → skip. Else rebuild + inject. | If `_is_cache_valid(root)` → inject from cache. Else rebuild + inject. |
| `/tricorder root <path>` | Write config + `build_map()` (always scans) | Write config → check signature. Valid → "cache ready." Stale/missing → auto-rebuild → "rebuilt." |
| `/tricorder scan` | Force rebuild | Unchanged. Force rebuild. |
| `/tricorder status` | Active project + active map file size | Active project + cache state (valid/stale/missing) + age + all cached projects |

---

## Code Changes

### `__init__.py` — existing functions to modify

**`build_map(project_root)` — add signature to meta:**
```python
meta = {
    "project_root": project_root,
    "map_file": str(out),
    "lines": n_lines,
    "tokens_approx": int(n_lines * 14),
    "project_sig": _project_signature(project_root),  # NEW
}
```

**`_is_fresh()` → delete. Replace with `_is_cache_valid()`.**

**`_on_session_start()` — add validity guard:**
```python
def _on_session_start(session_id="", **_):
    root = _active_project()
    if not root:
        return
    if _is_cache_valid(root):
        logger.debug("tricorder: cache valid for %s, skipping rebuild", root)
        return
    build_map(root)
```

**`_on_pre_llm_call()` — replace `_is_fresh` with `_is_cache_valid`:**
```python
if not _is_cache_valid(root):
    build_map(root)
```

**`_handle_tricorder()` root subcommand — check + auto-rebuild on stale:**
```python
if cmd == "root":
    if len(argv) < 2:
        return "Usage: /tricorder root <path>"
    p = Path(argv[1]).resolve()
    _set_active_project_config(str(p))
    if _is_cache_valid(str(p)):
        meta = _read_meta(str(p))
        age = _cache_age_str(str(p))
        return (
            f"Active project set to {p}.\n"
            f"  Cache: valid ({meta.get('lines', '?')} lines, "
            f"~{meta.get('tokens_approx', '?')} tokens, {age} old)."
        )
    # Stale or missing — auto-rebuild
    meta = build_map(str(p))
    if meta:
        return (
            f"Active project set to {p}.\n"
            f"  Map rebuilt ({meta['lines']} lines, "
            f"~{meta['tokens_approx']} tokens)."
        )
    return f"Active project set to {p}.\n  Scan failed — run /tricorder scan."
```

**`_handle_tricorder()` status subcommand — show all cached projects:**
```python
if cmd == "status":
    lines = [f"Active project: {root or '(none set)'}"]
    if root:
        cache = _cache_file(root)
        if cache.exists():
            meta = _read_meta(root)
            age = _cache_age_str(root)
            valid = _is_cache_valid(root)
            state = "valid" if valid else "stale (files changed)"
            lines.append(
                f"  cache: {state} ({meta.get('lines', '?')} lines, "
                f"~{meta.get('tokens_approx', '?')} tokens, {age} old)"
            )
        else:
            lines.append("  cache: (not built)")
    others = _list_cached_projects()
    if others:
        lines.append(f"  other cached maps ({len(others)}):")
        for proj_path, age, n_lines in others:
            lines.append(f"    {proj_path} — {n_lines} lines, {age} old")
    return "\n".join(lines)
```

### `__init__.py` — new helpers

```python
def _read_meta(project_root: str) -> dict:
    """Read cached meta JSON, return {} if missing/corrupt."""
    m = _meta_file(project_root)
    try:
        return json.loads(m.read_text(encoding="utf-8"))
    except Exception:
        return {}

def _cache_age_str(project_root: str) -> str:
    """Human-readable age of cached map: '2m', '1h', '3d', or 'unknown'."""
    m = _meta_file(project_root)
    if not m.exists():
        return "unknown"
    import time as _t
    secs = int(_t.time() - m.stat().st_mtime)
    if secs < 60:
        return f"{secs}s"
    if secs < 3600:
        return f"{secs // 60}m"
    if secs < 86400:
        return f"{secs // 3600}h"
    return f"{secs // 86400}d"

def _list_cached_projects() -> list:
    """List all cached projects (path, age_str, lines) excluding active."""
    root = _active_project()
    result = []
    for meta_file in _CACHE_DIR.glob("*.json"):
        try:
            info = json.loads(meta_file.read_text(encoding="utf-8"))
            proj = info.get("project_root", "")
            if proj and proj != root:
                import time as _t
                secs = int(_t.time() - meta_file.stat().st_mtime)
                age = (f"{secs}s" if secs < 60 else
                       f"{secs // 60}m" if secs < 3600 else
                       f"{secs // 3600}h" if secs < 86400 else
                       f"{secs // 86400}d")
                result.append((proj, age, info.get("lines", 0)))
        except Exception:
            continue
    return result
```

### Imports
`discover_src_files` needs to be importable from the plugin. Currently the
plugin shells to the CLI — it doesn't import utils.py. Two options:
- **a)** Import `discover_src_files` from utils.py directly (plugin runs in
  Hermes Python, but utils.py lives in the tricorder repo — needs sys.path).
  Fragile but works.
- **b)** Shell to CLI for the signature too — add a `--signature-only` flag
  to tricorder.py that prints the stat-hash and exits without building a map.
  Clean separation, no import dependency, but another subprocess call.

**Decision: (b)** — CLI `--signature-only` flag. Plugin shells to
`tricorder.exe --root <project> --exclude-globs <globs> --signature-only .`,
reads 16 hex chars from stdout. No import dependency, same pattern as
existing scan subprocess. ~30ms.

The CLI `--signature-only` path reuses `discover_src_files` from utils.py
(the same function scans + MCP already use). The stat-hash loop is ~10 lines
that call that function. One file walker, one hasher, no duplication. The
plugin doesn't reimplement any file discovery — it shells to the CLI for
both scans and signatures.

### Constants to remove
- `_MAP_FRESH_SECONDS = 60` — deleted

### `SPEC.md` and `SKILL.md` updates
- SPEC.md: update Plugin config table (remove `cache_ttl_seconds` if it was
  documented, note signature replaces TTL)
- SKILL.md: document multi-project workflow, cache behavior, `/tricorder root`
  auto-rebuild on stale

---

## What we're NOT building (YAGNI)

- Cache eviction — maps are ~10KB text files, 100 projects = 1MB
- File watchers / git diff / content hashing — stat signature is enough
- In-memory project switching — config is the single source of truth
- Pinned project list — one active project, switch via `/tricorder root`
- LRU or access tracking — not worth the code
- `cache_ttl_seconds` config knob — signature replaces TTL entirely

---

## Summary

| What | Change |
|------|--------|
| Cache validity | mtime TTL → stat-based signature (path+size+mtime per file) |
| `on_session_start` | Always rebuild → skip if signature matches |
| `/tricorder root` | Always scan → check + auto-rebuild only if stale/missing |
| `/tricorder status` | Active only → active + all cached projects with state |
| `pre_llm_call` | Same logic, better trigger (signature instead of TTL) |
| Constants | `_MAP_FRESH_SECONDS` deleted |
| New helpers | `_project_signature`, `_is_cache_valid`, `_read_meta`, `_cache_age_str`, `_list_cached_projects` |
| CLI | Add `--signature-only` flag (prints stat-hash, no map build) |

**Net:** ~90-120 lines changed. No new files, no new dependencies, no git
requirement. Cache becomes correct (changes invalidate) instead of arbitrary
(time invalidates).
