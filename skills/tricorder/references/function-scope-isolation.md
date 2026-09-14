# Function-Scope Isolation in `get_symbol_detail`

## Bug: Cross-file callees leak sibling function references

### Symptom
`tricorder_detail` for a C++ function (e.g., `GetFrameAudioData` in `PCM.cpp`) returns callees from sibling functions (`UpdateSpectrum`, `Align`, `CopyNewWaveformData`) that are defined in the same file but belong to different functions.

### Root Cause
`get_symbol_detail` in `core.py` has three sections that build callers/callees:

1. **In-file callers** (L1297-1303) — has line-range guard ✅
2. **In-file callees** (L1305-1317) — has line-range guard ✅
3. **Cross-file callees** (L1327-1345) — **NO line-range guard** ❌

The cross-file callees section iterates over ALL `file_refs` and resolves them to cross-file definitions. Since `file_refs` contains references from the entire file (not just the target function's body), sibling function callees get resolved and added as cross-file callees.

### Fix
Add the same line-range guard to the cross-file callees loop:

```python
# ponytail: function-scope guard for cross-file callees too
for ref in file_refs:
    ref_name = ref["name"]
    if ref_name == symbol_name:
        continue
    # Exclude refs outside this function's body
    if ref["line"] < target.line or ref["line"] > target.end_line:
        continue
    # ... rest of resolution logic
```

### Verification
Run the unit test:
```bash
python tests/test_get_symbol_details.py TestGetSymbolDetails.test_function_scope_isolation -v
```

The test queries `GetFrameAudioData` in `PCM.cpp` and asserts that `CopyNewWaveformData`, `UpdateSpectrum`, and `Align` (sibling function callees) do NOT appear in the result.

### Related Fixes
- **`end_line` for C++ functions** (L569-577): Tree-sitter queries capture `function_declarator` (signature only) instead of `function_definition` (full body). Walk up to `function_definition` to get the correct `end_line`.
- **In-file caller/callee guards** (L1297-1317): Filter references by `target.line` to `target.end_line`.

### Debugging Tip
When `get_symbol_detail` returns unexpected callees, check:
1. Is it an in-file callee? → verify line-range guard in L1314
2. Is it a cross-file callee? → verify line-range guard in cross-file loop (L1332+)
3. Is `end_line` wrong? → verify `function_declarator` → `function_definition` walk in `get_symbols` (L569-577)
