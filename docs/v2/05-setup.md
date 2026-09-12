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

## 5a. Hermes harness

Enable the `tricorder` plugin and set the active project:

```yaml
# config.yaml
plugins:
  enabled: [tricorder]
  entries:
    tricorder:
      active_project: /path/to/repo
```

Or `/tricorder root /path/to/repo` in-session (persisted to config).
Turn-0 behavior: mapped repo → one-line DB coverage + steering, no
walk; unmapped → cheap probe digest marked not-pre-mapped; later
turns silent. MCP tools (`tricorder-mcp` server over stdio: scan,
detect, symbols, detail, query) attach the same DB automatically.

## 5b. DSH harness

```bash
pnpm add @deepseek-ai/dsh-tricorder-inject   # from the dsh workspace
```

```yaml
# cordis.patch.yml
- insert:
    - id: tricorder-inject
      name: '@deepseek-ai/dsh-tricorder-inject'
      config:
        tricorderExe: 'C:/path/to/.venv/Scripts/tricorder.exe'
        verbose: false
```

Same turn-0 contract as Hermes, same bytes: `--db-coverage` when
mapped (DB-first), `--probe-digest` fallback when not. If
`tricorderExe` is omitted the plugin tries the checkout default,
then `tricorder` on PATH.

## 6. One surface or both

CLI covers everything alone (scan, retrieve, verify). Add MCP on
interactive agents for cheaper per-query tokens (capped record sets
vs full-map dumps); keep CI/bench on CLI (no daemon). Both read the
same sqlite — switching surfaces changes nothing about the data.
