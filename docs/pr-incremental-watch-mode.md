# PR Spec: Editor-Triggered Incremental Refresh (`tricorder refresh`)

**Milestone**: M1.4 (Scale & Usability, P1) — *Replaces Watch Mode*  
**Branch**: `feature/m1.4-refresh-mode`  
**Target**: tricorder CLI — single-file cache invalidation + map rebuild

---

## Problem Statement

The original `--watch` design (daemon + `watchdog`) has fundamental flaws:

| Flaw | Why It Matters |
|------|----------------|
| **Multiple repos = multiple daemons** | Each project spawns a background process monitoring its tree. 10 repos = 10 daemons = file handle exhaustion, CPU waste. |
| **Always-on polling** | Contradicts tricorder's "on-demand, deterministic" philosophy. User didn't ask for continuous monitoring. |
| **Editor already knows** | When you save a file, the editor *knows* the file changed. A daemon re-detects what the editor already knows. |
| **Battery / laptop hostile** | Background fs polling prevents idle sleep states. |

**Goal**: Near-instant incremental updates **triggered by the editor on save** — no daemon, no background process, no polling.

---

## Solution: `tricorder refresh <file> --root <project>`

```bash
# Editor runs this on file save (async, non-blocking)
tricorder refresh src/auth/login.py --root /home/user/myproject --map-tokens 2048
```

**What it does (sub-second):**
1. **Invalidate** only that file's entry in the per-file tag cache (`.repomap.tags.cache.v1/`)
2. **Re-parse** the single changed file (populates cache via existing mtime logic)
3. **Rebuild map** from cache (reads all cached tags — fast, no full walk)

---

## CLI Interface

```bash
# Refresh a single file (most common)
tricorder refresh path/to/file.py --root /project --map-tokens 2048

# Refresh multiple files (e.g., after git pull / rebase)
tricorder refresh file1.py file2.py --root /project

# Refresh all tracked files (equivalent to full rebuild, but uses cache)
tricorder refresh --all --root /project

# Dry run: show what would be invalidated
tricorder refresh file.py --root /project --dry-run
```

**Flags:**
| Flag | Description |
|------|-------------|
| `--root` | Project root (required unless in git repo — auto-detects) |
| `--map-tokens` | Token limit for regenerated map (default: 2048) |
| `--all` | Refresh all files in cache (post-pull, language pack upgrade) |
| `--dry-run` | List files that would be invalidated, don't actually refresh |
| `--quiet` | Suppress output (for editor async calls) |

---

## Editor Integration (Zero Config for Users)

### VS Code (`.vscode/tasks.json`)
```json
{
  "version": "2.0.0",
  "tasks": [
    {
      "label": "tricorder: refresh on save",
      "type": "shell",
      "command": "tricorder refresh ${file} --root ${workspaceFolder} --quiet",
      "presentation": { "reveal": "silent", "panel": "shared" },
      "runOptions": { "runOn": "folderOpen" },
      "group": { "kind": "build", "isDefault": true },
      "dependsOn": [],
      "problemMatcher": []
    }
  ]
}
```
Add to `settings.json`:
```json
"triggerTaskOnSave": { "tricorder: refresh on save": true }
```
*(Requires "Trigger Task on Save" extension, or use native `files.watcherExclude` + custom task)*

### Neovim (init.lua)
```lua
vim.api.nvim_create_autocmd("BufWritePost", {
  pattern = "*",
  callback = function()
    local root = vim.fn.system("git rev-parse --show-toplevel 2>/dev/null"):gsub("\n", "")
    if root == "" then root = vim.fn.getcwd() end
    local file = vim.fn.expand("%:p")
    -- Async, non-blocking
    vim.fn.jobstart({ "tricorder", "refresh", file, "--root", root, "--quiet" }, { detach = true })
  end,
})
```

### Zed (`.zed/tasks.json`)
```json
{
  "tasks": [
    {
      "label": "tricorder refresh",
      "command": "tricorder refresh {{file}} --root {{project_root}} --quiet",
      "trigger": "on_save"
    }
  ]
}
```

### Shell Alias (any editor / manual)
```bash
# ~/.bashrc / ~/.zshrc
trr() {
  local root=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
  tricorder refresh "$1" --root "$root" --quiet
}
# Usage: trr src/auth/login.py
```

---

## Implementation

### 1. CLI Entry Point (`tricorder.py`)

```python
# New subcommand: refresh
parser.add_argument(
    "refresh_files",
    nargs="*",
    metavar="FILE",
    help="Files to refresh (invalidates cache entry, re-parses, rebuilds map)"
)
parser.add_argument(
    "--refresh-all",
    action="store_true",
    help="Refresh all files currently in cache"
)
parser.add_argument(
    "--refresh-dry-run",
    action="store_true",
    help="Show files that would be refreshed without doing it"
)

# In main():
if args.refresh_files is not None or args.refresh_all:
    run_refresh(
        root=args.root,
        files=args.refresh_files,
        refresh_all=args.refresh_all,
        dry_run=args.refresh_dry_run,
        map_tokens=args.map_tokens,
        quiet=args.quiet,
        ...
    )
    sys.exit(0)
```

### 2. Refresh Logic (`core.py` addition)

```python
# In Tricorder class
def refresh_files(self, file_paths: List[str], map_tokens: int = None) -> dict:
    """Invalidate cache for specific files, re-parse them, rebuild map.
    
    Returns: {"refreshed": [files], "map_tokens": int, "cache_hits": int, "cache_misses": int}
    """
    refreshed = []
    cache_hits = 0
    cache_misses = 0
    
    for file_path in file_paths:
        abs_path = Path(file_path).resolve()
        rel_path = self.get_rel_fname(str(abs_path))
        
        # 1. Invalidate cache entry
        if str(abs_path) in self.TAGS_CACHE:
            del self.TAGS_CACHE[str(abs_path)]
            cache_hits += 1
        else:
            cache_misses += 1
        
        # 2. Re-parse (populates cache via get_tags mtime check)
        if abs_path.exists():
            self.get_tags(str(abs_path), rel_path)
            refreshed.append(str(abs_path))
    
    # 3. Rebuild map from cache (fast — reads cached tags)
    if map_tokens is not None:
        old_tokens = self.map_tokens
        self.map_tokens = map_tokens
    map_content, _ = self.get_repo_map(chat_files=[], other_files=[])
    if map_tokens is not None:
        self.map_tokens = old_tokens
    
    return {
        "refreshed": refreshed,
        "map_tokens": self.token_count(map_content),
        "cache_hits": cache_hits,
        "cache_misses": cache_misses,
    }
```

### 3. `--refresh-all` Implementation

```python
def refresh_all(self, map_tokens: int = None) -> dict:
    """Refresh all files currently in TAGS_CACHE."""
    all_cached = list(self.TAGS_CACHE.keys())
    return self.refresh_files(all_cached, map_tokens)
```

---

## Cache Invalidation Details

**Current cache key**: `TAGS_CACHE[abs_path] = {"mtime": float, "data": [Tag]}`

**Refresh invalidation**:
```python
# Simple deletion — next get_tags() sees mtime mismatch → re-parses
del self.TAGS_CACHE[abs_path]
# OR set mtime to 0 to force re-parse
self.TAGS_CACHE[abs_path] = {"mtime": 0, "data": []}
```

**Why this works**: `get_tags()` already checks `cached_entry.get("mtime") == file_mtime`. Deleting the entry or setting mtime=0 guarantees a re-parse on next map generation.

---

## Validation Gates

| Test | Command | Expected |
|------|---------|----------|
| Single file refresh | `tricorder refresh file.py --root /proj` | Cache entry gone, file re-parsed, map rebuilt |
| Multiple files | `tricorder refresh a.py b.py --root /proj` | Both invalidated, both re-parsed |
| `--all` flag | `tricorder refresh --all --root /proj` | All cached files refreshed |
| Dry run | `tricorder refresh file.py --root /proj --dry-run` | Lists file, no cache changes |
| Non-existent file | `tricorder refresh missing.py --root /proj` | Logs warning, continues |
| Editor integration | Save file in VS Code → map updated | Sub-second, no daemon |
| Git pull simulation | Modify 5 files → `tricorder refresh --all` | All 5 re-parsed, map current |
| Cache sharing | `tricorder refresh` → `tricorder-mcp` sees new data | MCP tools return fresh results |
| Large repo (1500 files) | Refresh 1 file | < 500ms (single parse + cache read) |

**Automated test**: `tests/test_refresh_mode.py`

---

## Files to Modify

| File | Changes |
|------|---------|
| `tricorder.py` | Add `refresh` subcommand + `run_refresh()` |
| `core.py` | Add `Tricorder.refresh_files()` + `refresh_all()` |
| `tests/test_refresh_mode.py` | **New** — integration tests |
| `docs/editor-integration.md` | **New** — VS Code, Neovim, Zed, shell configs |

---

## Backward Compatibility

- Zero impact on existing CLI, MCP, plugin, LSP
- New subcommand only; no flag changes
- Cache format unchanged
- `--watch` **removed from scope** (replaced by this)

---

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| Editor doesn't support on-save tasks | Shell alias `trr` works everywhere; document as fallback |
| User forgets to configure editor | `tricorder refresh --all` catches up (like `git pull` + refresh) |
| Race: two rapid saves | `refresh` is idempotent; second call sees mtime already updated |
| `--root` detection fails | Fallback to `pwd`; document `--root` requirement for non-git dirs |
| Large `--all` refresh | Same cost as full scan; use sparingly (post-pull, not per-save) |

---

## Comparison: Watch vs Refresh

| Aspect | `--watch` (daemon) | `refresh` (editor-triggered) |
|--------|-------------------|------------------------------|
| **Processes** | 1 per repo (always) | 0 (on-demand) |
| **CPU idle** | Polling overhead | Zero |
| **Multi-repo** | Broken (N daemons) | Works (per-save, per-repo) |
| **Editor integration** | None needed | Native (on-save hook) |
| **Battery** | Drains | Neutral |
| **Latency** | ~100ms debounce | ~200ms (parse + map) |
| **Reliability** | Watchdog edge cases | Explicit, deterministic |

---

## Definition of Done

- [ ] `tricorder refresh file.py --root /proj` works (invalidates + re-parses + rebuilds)
- [ ] `tricorder refresh --all --root /proj` refreshes entire cache
- [ ] `tricorder refresh --dry-run` shows files without changes
- [ ] VS Code task + Neovim autocmd + Zed task documented and tested
- [ ] Shell alias `trr` documented
- [ ] `pytest tests/test_refresh_mode.py -v` green
- [ ] SPEC.md updated (replace watch mode section with refresh)
- [ ] ROADMAP.md: M1.4 renamed to "Editor-Triggered Refresh"
- [ ] CHANGELOG entry

---

## Estimated Effort

- CLI subcommand: ~100 lines
- Core `refresh_files()`: ~50 lines
- Editor config docs: ~150 lines
- Tests: ~150 lines
- **Total**: ~450 lines, 2 days

---

## Future Extensions (v2)

- `tricorder refresh --since-git <commit>` — refresh files changed since commit
- MCP tool `tricorder_refresh` — agent can trigger refresh
- LSP notification `workspace/didChangeWatchedFiles` → auto-refresh (editor pushes, no polling)