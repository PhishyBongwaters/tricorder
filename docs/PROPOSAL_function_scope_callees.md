# Proposal: Function-Scope Callers/Callees in `get_symbol_detail`

## Problem

`get_symbol_detail` (core.py L1296-1302) builds the `callees` list by scanning **all** tree-sitter reference captures in the file, not just those inside the target symbol's body. This produces false positives:

**Example from bench run:**
- `PCM::GetFrameAudioData` (lines 76-97 in PCM.cpp)
- tricorder reports callees including `CopyNewWaveformData` at line 57, `UpdateSpectrum` at line 62, `Align` at line 66
- These lines are inside `UpdateFrameAudioData` (lines 52-74), NOT inside `GetFrameAudioData`
- The model inferred that `GetFrameAudioData` calls `CopyNewWaveformData` — **wrong**

Root cause: `end_line` is set to the signature line (L570: `end_line = parent.end_point[0] + 1`), which for single-line signatures equals `start_line`. The callee filter at L1299-1302 has no line-range check.

## Is this crippling?

**No.** This is an enhancement to `get_symbol_detail` only. The following are unaffected:
- `get_symbols` — returns symbol list with correct line ranges
- `get_ranked_tags` — PageRank tagging, no callers/callees
- `tricorder_detect` — identifier search, no callers/callees
- `tricorder_symbols` — symbol search, no callers/callees
- `build_call_graph` — graph traversal uses `get_symbols` + `get_all_references`, not `get_symbol_detail`
- Tier-0 auto-injection — uses `get_symbols`, not `get_symbol_detail`

Only `tricorder_detail` (MCP tool) is affected, and it currently returns noisy data. Fixing it makes the tool **more correct**, not less.

## Proposed Change

### 1. Fix `end_line` in `get_symbols` (core.py L569-570)

Currently:
```python
start_line = parent.start_point[0] + 1
end_line = parent.end_point[0] + 1
```

For multi-line functions, `end_point[0]` is the last line of the function body. This should already be correct — the issue is that for some languages/syntaxes, tree-sitter may return the declarator's end line rather than the body's closing brace. Verify with a quick test on the projectM file.

If `end_line` is already correct, skip this step. If not, the fix is:
```python
# For function/method defs, extend end_line to the closing brace/endif
if sym_type in ("function", "method") and parent.type in (
    "function_definition", "function_declarator", "method_declaration",
    "method_definition", "class_declaration", "struct_declaration"
):
    # Walk to find the closing delimiter
    for child in parent.descendants_in_range(
        (parent.end_point[0], 0), (parent.end_point[0] + 100, 0)
    ):
        if child.type in ("}", "endif", "end"):
            end_line = child.start_point[0] + 1
            break
```

**Ponytail:** If `end_line` is already correct (verify first), skip this entirely.

### 2. Add function-scope filter to callers/callees (core.py L1296-1302)

Current:
```python
# In-file callees: unique symbols this file's code calls (excluding self)
callees = []
seen = set()
for ref in file_refs:
    if ref["name"] != symbol_name and ref["name"] not in seen:
        seen.add(ref["name"])
        callees.append({...})
```

Proposed:
```python
# In-file callees: unique symbols called WITHIN this symbol's body
callees = []
seen = set()
for ref in file_refs:
    if ref["name"] == symbol_name:
        continue
    if ref["name"] in seen:
        continue
    # Function-scope guard: only include refs within the symbol's line range
    if ref["line"] < target.line or ref["line"] > target.end_line:
        continue
    seen.add(ref["name"])
    callees.append({...})
```

Same guard for callers (L1292-1294):
```python
for ref in file_refs:
    if ref["name"] == symbol_name:
        if ref["line"] >= target.line and ref["line"] <= target.end_line:
            callers.append({...})
```

### 3. Add `scope` field to callers/callees entries

Add `"scope": "in-file"` or `"scope": "cross-file"` to each entry for clarity. Not strictly necessary but helps consumers distinguish.

## Validation Gates

### Gate 1: Unit test — function-scope isolation

Add to `tests/test_get_symbol_details.py`:

```python
def test_function_scope_callees(self):
    """Callees must only include references within the target function's body.
    
    PCM.cpp has two adjacent functions:
    - UpdateFrameAudioData (L52-74): calls CopyNewWaveformData, UpdateSpectrum, Align, Update
    - GetFrameAudioData (L76-97): calls copy, CurrentRelative, AverageRelative, TimeToFrequencyDomain
    
    GetFrameAudioData's callees must NOT include CopyNewWaveformData (L57),
    UpdateSpectrum (L62), Align (L66), or Update (L72) — those are in the
    preceding function.
    """
    import os
    pcm_cpp = r"D:\Projects\projectm\src\libprojectM\Audio\PCM.cpp"
    if not os.path.isfile(pcm_cpp):
        self.skipTest(f"PCM.cpp not found: {pcm_cpp}")
    
    result = asyncio.run(tricorder_detail(
        project_root=r"D:\Projects\projectm",
        file=r"src\libprojectM\Audio\PCM.cpp",
        name="GetFrameAudioData"
    ))
    self.assertNotIn("error", result)
    sym = result["symbol"]
    
    # These are called from UpdateFrameAudioData (L52-74), NOT GetFrameAudioData (L76-97)
    false_callees = {"CopyNewWaveformData", "UpdateSpectrum", "Align"}
    callee_names = {c["name"] for c in sym["callees"] if not c.get("cross_file")}
    
    for fc in false_callees:
        self.assertNotIn(fc, callee_names,
            f"{fc} is a callee of GetFrameAudioData but only exists in UpdateFrameAudioData")
    
    # These ARE called from GetFrameAudioData
    true_callees = {"copy", "CurrentRelative", "AverageRelative"}
    for tc in true_callees:
        self.assertIn(tc, callee_names,
            f"{tc} should be a callee of GetFrameAudioData")
```

### Gate 2: Existing tests still pass

Run `python -m pytest tests/test_get_symbol_details.py` — all existing tests must pass. The `test_callers_callees_populated` and `test_cross_file_callees` tests may need adjustment if they relied on file-scope behavior.

### Gate 3: Benchmark regression check

Re-run `bench_agent_eval.py projectm` with the fix. Variant A should now correctly identify:
- Loudness computation in `UpdateFrameAudioData` (not `GetFrameAudioData`)
- `AddToBuffer` as a pure buffer write (no downstream calls)
- `UpdateFrameAudioData` as the processing hub

### Gate 4: Performance

Single `get_symbol_detail` call must still return in <1s (existing test). The line-range filter is O(n) where n = file refs — same complexity as current code, just with one extra integer comparison per ref.

## Files Changed

- `core.py` — `get_symbol_detail` method (L1296-1302 for callees, L1292-1294 for callers)
- `tests/test_get_symbol_details.py` — new test + any existing test adjustments

## Risk Assessment

| Risk | Severity | Mitigation |
|------|----------|------------|
| `end_line` is wrong for some symbols | Medium | Verify first; if wrong, fix in `get_symbols` |
| Nested functions share line ranges | Low | Tree-sitter gives correct ranges for nested defs |
| Existing tests break | Low | Only if they relied on file-scope behavior |
| Cross-file callees unaffected | None | Cross-file logic (L1317-1330) is separate |

## Implementation Order

1. Verify `end_line` correctness on projectM's PCM.cpp (quick check)
2. Add the line-range filter to callers/callees in `get_symbol_detail`
3. Add Gate 1 unit test
4. Run Gate 2 (existing tests)
5. Run Gate 3 (benchmark)
