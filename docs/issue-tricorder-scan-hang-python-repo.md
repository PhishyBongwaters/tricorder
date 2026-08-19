# Issue: `tricorder_scan` Hangs on Medium Python Repo

**Status:** Open  
**Labels:** `performance`, `windows`, `python-parser`  
**Priority:** High  
**Created:** 2025-08-19  

---

## Summary

`tricorder_scan` times out (>120s) on a 225-file Python project (~15k LOC, ~40 source files). MCP `initialize` and `tools/list` work correctly; the scan operation itself never returns.

## Environment

| Component | Version |
|-----------|---------|
| tricorder | 0.1.0 (from `tricorder-mcp` console script) |
| fastmcp | 3.4.6 |
| Python | 3.14 |
| tree-sitter | 0.20.0 + language-pack |
| OS | Windows 11 |
| Project | ROOP-PHISHY (face-swap pipeline, pure Python) |

## Reproduction

```bash
# Direct CLI (same as MCP bridge does)
echo -e '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}}}\n{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"tricorder_scan","arguments":{"project_root":"D:\\Projects\\ROOP-PHISHY","tier":0,"token_limit":4096}}}' | tricorder-mcp.exe
```

**Result:** Initialize succeeds, tools/list succeeds, then scan hangs >120s (both CLI and MCP bridge return timeout).

## What Works

- `initialize` → returns server info
- `tools/list` → returns 4 tools: `tricorder_scan`, `tricorder_detect`, `tricorder_symbols`, `tricorder_detail`
- Targeted tools (`detect`, `symbols`, `detail`) — **not tested yet**, but likely fast since they don't full-scan

## What Fails

- `tricorder_scan` at **any tier** (0 or 1), **any token_limit** (tried 4096, 8192)
- Both stdout return mode and `output_file` mode
- Cache doesn't help (first run and `force_refresh=true` both hang)

## Project Characteristics

```
D:\Projects\ROOP-PHISHY\src\roop\*.py          ~15 files, core pipeline
D:\Projects\ROOP-PHISHY\src\roop\processors\*.py  ~12 files, ONNX processors
D:\Projects\ROOP-PHISHY\src\ui\*.py            ~8 files, Gradio UI
D:\Projects\ROOP-PHISHY\src\clip\*.py          ~4 files, CLIP wrapper
Total: ~40 Python source files, ~225 files with __pycache__ + models + configs
```

- Pure Python, no C extensions
- Heavy use of: `onnxruntime`, `insightface`, `cv2`, `torch`, `gradio`, `numpy`
- Some files are large (ProcessMgr.py ~1000 lines, core.py ~400 lines)

## Likely Root Cause Areas

### 1. Tree-sitter Python Parser Performance
**File:** `core.py` → `get_tags_raw()` (lines 190-263)

The parser is instantiated per file and processes each file individually. Python files with:
- Heavy decorators (`@dataclass`, `@property`, custom decorators)
- Complex type hints (nested generics, unions)
- Deeply nested classes/functions
- Large files (1000+ lines)

...may cause the tree-sitter Python parser to take excessive time per file. The `grep-ast` library's `get_parser()` may not be effectively caching parsers across calls.

### 2. Full-Repo Auto-Scan Includes Bytecode
**File:** `utils.py` → `discover_src_files()` (lines 106-146)

While `_BUILTIN_SKIP_DIRS` includes `__pycache__`, the walk still traverses into it before filtering. With 225 total entries vs 40 real source files, the directory walk overhead on Windows could be significant. Additionally, `.pyc` files may not be filtered by extension checks.

### 3. PageRank Computation Quadratic Behavior
**File:** `core.py` → `get_ranked_tags()` (lines 844-994)

- Builds a `MultiDiGraph` with a node per file
- Adds edges for every cross-file reference
- Runs `nx.pagerank()` with personalization

For a project with ~40 files and heavy cross-imports (common in ML pipelines), the graph density could make PageRank computation slow. NetworkX's PageRank is O(E) per iteration but with Python overhead.

### 4. Cross-File Index Building
**File:** `core.py` → `_build_cross_file_index()` (lines 673-716)

- Called from `get_symbol_detail` and potentially other paths
- Iterates all files, parses imports, builds resolver
- May be triggered during scan if symbol detail resolution is attempted

### 5. DiskCache on Windows
**File:** `core.py` → `load_tags_cache()` (lines 92-100)

`diskcache` uses SQLite which can have file locking issues on Windows, especially with concurrent access. The cache directory `.repomap.tags.cache.v1/` creation could block.

## Suggested Debug Steps

1. **Add timing logs** in `tricorder_scan` around:
   - File discovery (`discover_src_files`)
   - Tag extraction (`get_tags` → `get_tags_raw`)
   - Graph building + PageRank (`get_ranked_tags`)
   - Rendering (`to_tree`)

2. **Test with `exclude_globs`** to skip bytecode:
   ```json
   {"exclude_globs": ["**/__pycache__/**", "**/*.pyc"]}
   ```

3. **Test with explicit `other_files`** list (only real `.py` files) to bypass auto-scan entirely.

4. **Profile `Tricorder.get_ranked_tags()` in isolation** with a minimal script.

5. **Check tree-sitter parser caching** — verify `grep_ast.tsl.get_parser()` returns cached instances.

## Workaround Used

Manual code exploration (`glob` + `read`) covered the entire codebase. Targeted MCP tools (`detect`/`symbols`/`detail`) would likely work — the bottleneck is specifically the **full-repo map generation**.

## Code References

- **MCP Tool Entry:** `tricorder_server.py` → `tricorder_scan()` (lines 85-355)
- **Core Logic:** `core.py` → `Tricorder.get_repo_map()` (lines 1293-1349) → `get_ranked_tags_map()` → `get_ranked_tags()`
- **Tag Extraction:** `core.py` → `get_tags()` (lines 156-188) → `get_tags_raw()` (lines 190-263)
- **File Discovery:** `utils.py` → `discover_src_files()` (lines 106-146)
- **Cache:** `core.py` → `load_tags_cache()` (lines 92-100)

## Potential Fixes

1. **Add progress/timeouts** to long-running operations
2. **Parallelize tag extraction** across files (ThreadPoolExecutor)
3. **Optimize file discovery** — use `glob.glob("**/*.py", recursive=True)` with explicit excludes instead of `os.walk`
4. **Cache PageRank results** per repo signature
5. **Add `--max-files` guard** earlier in the pipeline (already exists but may not be respected in all paths)
6. **Skip tree-sitter for known-large files** or add a complexity threshold

---

## Related Files for Investigation

- `core.py` — Main Tricorder class, PageRank, tag extraction
- `tricorder_server.py` — MCP tool wrapper
- `utils.py` — File discovery, token counting
- `import_parser.py` — Import resolution (used in cross-file index)
- `importance.py` — File importance filtering