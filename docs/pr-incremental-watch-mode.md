# PR Spec: Incremental File-Watch Mode (`tricorder --watch`)

**Milestone**: M1.4 (Scale & Usability, P1)  
**Branch**: `feature/m1.4-watch-mode`  
**Target**: tricorder CLI + cache layer (no MCP tool changes)

---

## Problem Statement

The current cache invalidation uses a **stat-based project signature** (`--signature-only`): sha256 of `{path}:{size}:{mtime}` per source file. This works perfectly for session-start rebuilds but requires a full re-scan on every change. For active development (edit → test → edit), users wait for the full parse each time.

**Goal**: Near-instant incremental updates on file save, using the existing per-file tag cache (`diskcache` in `.repomap.tags.cache.v1/`). No git dependence — works on any directory.

---

## Non-Goals

- Git diff / VCS integration (explicitly out of scope per ROADMAP)
- Multi-repo watch (single project root only)
- LSP server (separate PR)
- Push notifications to editors (CLI-only; LSP PR covers editor integration)

---

## Design

### 1. CLI Interface

```bash
# Foreground watch (blocks, prints updates)
tricorder . --watch --map-tokens 2048

# Background daemon (detached, writes cache)
tricorder . --watch --daemon --map-tokens 2048

# Stop background daemon
tricorder . --watch --stop
```

### 2. Watch Implementation

| Component | Library | Rationale |
|-----------|---------|-----------|
| Filesystem events | `watchdog` (cross-platform, pure Python fallback) | Mature, handles Windows/Linux/macOS, supports recursive dir watch |
| Event debouncing | Custom (50–100ms) | Coalesce rapid saves (e.g., editor atomic writes) |
| Incremental parse | Existing `Tricorder.get_tags()` + `TAGS_CACHE` | Reuses per-file mtime cache; only changed files re-parsed |
| Map rebuild | Existing `Tricorder.get_repo_map()` | Re-ranks only affected subgraph |

### 3. Cache Invalidation Logic

**Current (session-start)**:
```
signature = sha256(sorted({path}:{size}:{mtime} for each file))
if signature != cached_signature: full_rebuild()
```

**Watch mode (incremental)**:
```
on file_event(path):
    if path not in watched_extensions: return
    if event.type in {modified, created}:
        # Invalidate single-file cache entry
        TAGS_CACHE[path] = None  # or delete key
        # Mark map as dirty
        dirty_files.add(path)
    elif event.type == deleted:
        TAGS_CACHE.pop(path, None)
        dirty_files.add(path)
    
    debounce(100ms):
        if dirty_files:
            # Re-parse only dirty files
            for f in dirty_files:
                Tricorder.get_tags(f, rel_fname)  # populates cache
            # Rebuild map from cached tags (fast)
            rebuild_map()
            dirty_files.clear()
```

**Key insight**: The `TAGS_CACHE` is already keyed by absolute path with mtime. On file change, we simply evict that key. Next `get_tags()` call re-parses and caches. `get_repo_map()` reads from cache — no full walk needed.

### 4. Watchdog Integration

```python
# tricorder.py additions
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

class TricorderEventHandler(FileSystemEventHandler):
    def __init__(self, tricorder: Tricorder, root: Path, map_tokens: int, ...):
        self.tricorder = tricorder
        self.root = root
        self.map_tokens = map_tokens
        self.dirty = set()
        self.debounce_timer = None
    
    def on_modified(self, event):
        if event.is_directory: return
        if not self._should_watch(event.src_path): return
        self._mark_dirty(event.src_path)
    
    def on_created(self, event):
        self.on_modified(event)
    
    def on_deleted(self, event):
        if event.is_directory: return
        self._mark_dirty(event.src_path)
        # Also remove from cache
        self.tricorder.TAGS_CACHE.pop(event.src_path, None)
    
    def _should_watch(self, path: str) -> bool:
        # Reuse existing language detection + exclude_globs
        return detect_lang(path) is not None and not self._excluded(path)
    
    def _mark_dirty(self, path: str):
        self.dirty.add(path)
        if self.debounce_timer:
            self.debounce_timer.cancel()
        self.debounce_timer = threading.Timer(0.1, self._rebuild)
        self.debounce_timer.start()
    
    def _rebuild(self):
        if not self.dirty:
            return
        # Re-parse dirty files (populates TAGS_CACHE)
        for f in self.dirty:
            rel = self.tricorder.get_rel_fname(f)
            self.tricorder.get_tags(f, rel)
        # Regenerate map
        self.tricorder.get_repo_map(...)  # uses cached tags
        self.dirty.clear()
```

### 5. Daemon Mode

```python
def run_watch_daemon(root: str, map_tokens: int, ...):
    # Double-fork for true background on Unix; on Windows use subprocess.DETACHED_PROCESS
    pid_file = Path(root) / ".tricorder" / "watch.pid"
    if pid_file.exists():
        # Check if process alive
        try:
            os.kill(int(pid_file.read_text()), 0)
            print("Watch daemon already running")
            return
        except ProcessLookupError:
            pass  # stale pid, continue
    
    # Start observer in background thread
    observer = Observer()
    observer.schedule(handler, root, recursive=True)
    observer.start()
    
    # Write pid
    pid_file.parent.mkdir(exist_ok=True)
    pid_file.write_text(str(os.getpid()))
    
    # Keep alive
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()
```

---

## Validation Gates

| Test | Command | Expected |
|------|---------|----------|
| Basic watch | `tricorder . --watch --map-tokens 2048` (bg) → edit file → map cache updated | Cache valid within 2s |
| Debounce | Rapid saves (3 in 50ms) → single rebuild | Only 1 rebuild triggered |
| Exclude globs | `tricorder . --watch --exclude-globs vendor/**` → edit vendor/file.py | No rebuild, no cache update |
| New file | Create `new_module.py` with symbols → appears in map | Detected, parsed, ranked |
| Deleted file | Delete `old_module.py` → removed from map | Cache entry gone, map updated |
| Daemon stop | `tricorder . --watch --stop` → process exits, pid file removed | Clean shutdown |
| Cache persistence | Kill watch → restart tricorder (no --watch) → map valid | Session-start uses watch-updated cache |

**Automated test**: `tests/test_watch_mode.py` (see ROADMAP M1.4)

---

## Files to Modify

| File | Changes |
|------|---------|
| `tricorder.py` | `--watch`, `--daemon`, `--stop` args; `run_watch()` / `run_daemon()` / `stop_daemon()` |
| `core.py` | No changes (uses existing `TAGS_CACHE` + `get_tags`/`get_repo_map`) |
| `requirements.txt` | Add `watchdog>=3.0` |
| `tests/test_watch_mode.py` | New test file (pytest-asyncio for observer lifecycle) |

---

## Backward Compatibility

- No changes to existing CLI flags, MCP tools, or plugin
- `--watch` is additive; default behavior unchanged
- Cache format unchanged (same `.repomap.tags.cache.v1/`)

---

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| Watchdog not installed | Optional dependency; `--watch` prints friendly error + `pip install watchdog` hint |
| High-frequency events (build outputs) | Debounce + `exclude_globs` + extension filter |
| Windows file locking | `watchdog` uses `ReadDirectoryChangesW`; test on Windows |
| Memory growth in long-running daemon | `TAGS_CACHE` is disk-backed (`diskcache`); in-memory `dirty` set bounded by files changed per debounce window |
| Symlink loops | `watchdog` follows symlinks by default; add `follow_symlinks=False` to observer |

---

## Future Extensions (Out of Scope)

- `--watch --lsp` → bridge to LSP server (separate PR)
- WebSocket push for editor plugins
- Per-file change notifications via MCP `notifications/resources/updated`

---

## Definition of Done

- [ ] `tricorder --watch` runs foreground, updates cache on file save
- [ ] `tricorder --watch --daemon` runs background, survives terminal close
- [ ] `tricorder --watch --stop` cleanly stops daemon
- [ ] All validation gates pass
- [ ] `pytest tests/test_watch_mode.py -v` green
- [ ] SPEC.md updated with watch mode docs
- [ ] CHANGELOG entry

---

## Estimated Effort

- Core watch logic: ~200 lines
- Daemon management: ~100 lines
- Tests: ~150 lines
- **Total**: ~450 lines, 2–3 days