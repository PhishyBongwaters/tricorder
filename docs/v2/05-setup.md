# Setup — fresh system to working tricorder (Hermes or DSH)

## 1. Prereqs

- Python ≥3.11, `rg` (ripgrep) on PATH — required for `--pre-index`
  narrowing. `ctags` optional (index fallback only).
- Node ≥22 + pnpm — only for the DSH plugin build.

## 2. Install

```bash
git clone <tricorder> && cd tricorder
python -m venv .venv && .venv/Scripts/pip install -e .   # Windows
# provides: tricorder, tricorder-mcp console scripts
```

`pip install -e .` is authoritative (pyproject). `requirements.txt`
pins the same set for CI. No scipy/numpy — ranking is SQL, not scipy.

## 3. Verify (no config, no repos)

```bash
tricorder --probe-digest --root .          # language tally, cheap
tricorder --help | grep -c "db-coverage"   # 1+
.venv/Scripts/python.exe -m pytest tests/ -q -p no:cacheprovider
```

## 4. Map your first repo

```bash
tricorder --init --root /path/to/repo
python chunk_resume.py /path/to/repo       # to DONE
```

Details: `00-scan-first.md`.

## 5. Agent harnesses — TBD (not ported)

The MCP server (`tricorder-mcp`) and the Hermes/DSH turn-0 plugins
(`tricorder_inject.py`, `tricorder_client.py`, `plugins/`) are
**unported on this branch**. Intended flow once ported: mapped repo →
one-line DB coverage + steering with no walk; unmapped → cheap probe
digest marked not-pre-mapped; MCP tools attach the same DB over
stdio. No usage docs for this section until the port lands and is
verified live.

## 6. One surface or both

CLI covers everything alone (scan, retrieve, verify). MCP is TBD on
this branch — once ported, it serves interactive agents with cheaper
per-query tokens (capped record sets vs full-map dumps); keep
CI/bench on CLI (no daemon). Both read the same sqlite — switching
surfaces changes nothing about the data.
