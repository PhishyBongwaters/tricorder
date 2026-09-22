# Benchmarks

> **Historical snapshot (Gen 2, pre-db-map pipeline).** These numbers were
> measured against a previous pipeline version and are kept for methodology
> reference only — do not quote them for the current code. Current,
> committable savings numbers live in
> [comparison runs 2026-09-21](../eval/comparison-runs/2026-09-21/README.md)
> (−76.3% combined response-payload tokens vs baseline tools).

Tricorder's whole point is token savings: a compact map steers an agent to
the right code without reading the entire repo.

## Methodology

Efficacy is measured with `bench/bench_validity.py` (CLI) and
`bench/bench_validity_mcp.py` (MCP). Each task poses a realistic agent
question; the task's `ground_truth` identifiers must appear in the map for a
PASS.

**RESULT: ALL TASKS PASS (15 repos × 2 surfaces).**

| Repo | Tasks | Suite | Map Tokens | Full Repo | Savings |
|------|-------|-------|------------|-----------|---------|
| projectm | 2/2 | bench_validity.py | 2,048 | 642,428 | 99.7% |
| projectm | 2/2 | bench_validity_mcp.py | 221 / 1,358 | 642,428 | 100.0% / 99.8% |
| vaultwarden | 2/2 | bench_validity.py | 32,563 | 755,518 | 95.7% |
| vaultwarden | 2/2 | bench_validity_mcp.py | 1,173 / 2,695 | 755,518 | 99.8% / 99.6% |
| linux | 1/1 | bench_validity.py | 39,936 | 50,352,437 | 99.9% |
| linux | 1/1 | bench_validity_mcp.py | 5,500 | 50,352,437 | 100.0% (pre-indexed) |
| bitburner | 1/1 | bench_validity.py | 65,024 | 1,504,232 | 95.7% |
| bitburner | 1/1 | bench_validity_mcp.py | 205 | 1,504,232 | 100.0% |
| librechat | 1/1 | bench_validity.py | 65,024 | 6,316,980 | 99.0% |
| librechat | 1/1 | bench_validity_mcp.py | 1,560 | 6,316,980 | 100.0% |
| elixir | 1/1 | bench_validity.py | 4,096 | 3,060,510 | 99.9% |
| elixir | 1/1 | bench_validity_mcp.py | 6,911 | 3,060,510 | 99.8% |
| otp | 1/1 | bench_validity.py | 102 | 46,463,905 | 100.0% |
| otp | 1/1 | bench_validity_mcp.py | 202 | 46,463,905 | 100.0% |
| go | 1/1 | bench_validity.py | 307 | 36,501,836 | 100.0% |
| go | 1/1 | bench_validity_mcp.py | 19,587 | 36,501,836 | 99.9% |
| kotlin | 1/1 | bench_validity.py | 64,204 | 13,984,544 | 99.5% |
| kotlin | 1/1 | bench_validity_mcp.py | 8,810 | 13,984,544 | 99.9% |
| swift | 1/1 | bench_validity.py | 64,409 | 38,017,250 | 99.8% |
| swift | 1/1 | bench_validity_mcp.py | 5,793 | 38,017,250 | 100.0% |
| rails | 1/1 | bench_validity.py | 64,819 | 5,445,557 | 98.8% |
| rails | 1/1 | bench_validity_mcp.py | 6,601 | 5,445,557 | 99.9% |
| framework | 1/1 | bench_validity.py | 65,024 | 4,218,620 | 98.5% |
| framework | 1/1 | bench_validity_mcp.py | 5,583 | 4,218,620 | 99.9% |
| kong | 1/1 | bench_validity.py | 53,145 | 3,440,558 | 98.5% |
| kong | 1/1 | bench_validity_mcp.py | 97 | 3,440,558 | 100.0% |
| spring-boot | 1/1 | bench_validity.py | 65,024 | 487,802 | 86.7% |
| spring-boot | 1/1 | bench_validity_mcp.py | 448 | 487,802 | 99.9% |
| vue | 1/1 | bench_validity.py | 1,433 | 549,971 | 99.7% |
| vue | 1/1 | bench_validity_mcp.py | 5,738 | 549,971 | 99.0% |

### Per-repo notes

- **projectm** (~5,800 files, ~1.1M lines, C++): ~100% token savings; 2K-token map covers `PCM::AddToBuffer`, `Loudness`, `CurrentRelative`, `AverageRelative`.
- **vaultwarden** (~200 Rust files): ~96–99.8% token savings; 33K-token map covers `generate_invite`, `delete_user`, `admin_page`, `hash_password`, `verify_password_hash`, `routes`, `catchers`.
- **linux** (Linux kernel, ~50M tokens full): With `--pre-index pick_next_task` the map narrows to `kernel/sched/` and ships in **~1.1s** (no full-tree walk), covering `pick_next_task`, `schedule`, `update_curr` at 99.9% savings. Use a *specific* probe symbol.
- **bitburner** (TypeScript): 95.7% savings CLI (65K-token map); `loadAliases`/`addAlias` found in both surfaces.
- **librechat** (TypeScript monorepo, `packages/`): needs 65K-token map to surface `getTenantId`/`configCapability` under whole monorepo; still 99.0% savings.
- **elixir** (`lib/iex`): 99.9% savings; `IEx`, `configure`, `configuration` present in both surfaces.
- **otp** (`lib/compiler`): 100% savings at ~102 (CLI) / 202 (MCP) map tokens.
- **go** (`src/cmp`): 100% savings; `Less`/`Compare`/`Or` present in both surfaces.
- **kotlin** (`core`): 99.5% savings CLI (64K-token map); `Variance`/`TypeSystemCommonBackendContext` present in both surfaces. `computeExpandedTypeForInlineClass` excluded (kotlin-grammar blind spot).
- **swift** (`lib`): 99.8% savings CLI (64K-token map).
- **rails** (`activerecord/lib`): 98.8% savings CLI (65K-token map).
- **framework** (`src`): 98.5% savings CLI (65K-token map).
- **kong** (`kong`): 98.5% savings CLI (53K-token map).
- **spring-boot** (build-plugin): 86.7% savings CLI (65K-token map).
- **vue** (`src/v3/reactivity`): 99.7% savings CLI (1.4K-token map).

**Note on the linux slot:** `--pre-index pick_next_task` (CLI) and
`pre_index="pick_next_task"` (MCP) narrow the 66k-file kernel to
`kernel/sched/*` (~6 files). Without scoping, MCP detect walks all 66k files
and is cold-cache-flaky. With scoping: deterministic — verified 3x
consecutive PASS.

**MCP token shape differs from CLI:** `bench_validity_mcp.py` exercises
`tricorder_detect` (per-file definition records), not a serialized map — MCP
"tokens" scale with result count per identifier. projectm MCP tokens are
smaller than CLI map (1358 vs 2048); vaultwarden's grow to ~2695. Savings
measured against same full-repo estimate in both suites.

**MCP `tricorder_detect` supports `pre_index`** (mirrors CLI `--pre-index`)
— linux MCP slot uses `pre_index="pick_next_task"` to narrow to
`kernel/sched/*`; runtime dropped from ~168s to ~64s, no longer
cold-cache-flaky.

## Reproduce

- **Repos:** projectm (C++), vaultwarden (Rust), Linux kernel, bitburner (`bitburner-src`, TS), LibreChat (`LibreChat`, TS), elixir (`lib/iex`), otp (`lib/compiler`), go (`src/cmp`), kotlin (`core`), swift (`lib`), rails (`activerecord/lib`), framework (`src`), kong (`kong`), spring-boot (build-plugin), vue (`src/v3/reactivity`).

```bash
# from tricorder repo root, in its venv
python bench/bench_validity.py               # CLI surface (all 15 repos)
python bench/bench_validity_mcp.py           # MCP surface
python bench/bench_validity.py linux         # linux fast-path only
python bench/bench_validity.py bitburner     # single repo by name
python bench/bench_validity.py --root /path/to/your/repos  # custom checkouts
```

Note: `rg` must be on `PATH` for `--pre-index` fast path (linux slot). Task
definitions live in `bench/bench_validity*.py`. No CI bench machinery — run
locally; numbers reproducible on same public repos.

## A/B agent harness (`bench_agent_eval.py`)

End-to-end agent benchmark: Variant A (Tricorder MCP) vs Variant B (baseline
tools) on the same relationship task, with real session telemetry from each
variant's profile `state.db`. Normal legs are telemetry-only — the overseeing
agent grades the A/B comparison itself from the saved reports + `state.db`.

```bash
python bench/bench_agent_eval.py projectm --variant both
python bench/bench_agent_eval.py projectm --judge-only report_<sid>-A.md report_<sid>-B.md
python bench/bench_agent_eval.py vaultwarden --variant both --max-turns 20
```

**`--max-turns`** (hard cap, default 10) caps model API turns per leg.
`--run-budget` is only a soft prompt nudge; the real guard is `--max-turns`.

**Judge semantics:** the fast path is **fail-fast only** — cheap FAIL when the
final answer names none of the expected ground-truth identifiers. Every
non-trivial answer then hits a **deterministic grounding gate** (no model
call): template-arg literals the answer asserts must appear verbatim in the
session's retrieved source, else immediate `FAIL(deterministic-grounding)`.
Only then does the semantic LLM judge run, given the session's **full
retrieved source** as authority — any asserted specific (template args, line
numbers, step ordering) must appear there or it fails as hallucinated detail.
Rationale prefixes: `PASS:`, `FAIL(fast):`,
`FAIL(deterministic-grounding):`, `SEMANTIC PASS/FAIL:`, `no final answer:`,
`Judge Error:`.
