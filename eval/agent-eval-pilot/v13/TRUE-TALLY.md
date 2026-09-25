# True tally — v13 series re-measured from harness truth (2026-09-25)

Nothing below edits history. Published artifact numbers, grades, and the
RUNLOG stand as written; this file adds the harness-measured layer and
says exactly where the two disagree. Artifact token totals are retired
for all future tallies — direction held, magnitudes did not.

## Method change

- **Before:** `meter_leg.py` over agent-saved `step_*.txt` payloads
  (tiktoken cl100k). Complete only when agents saved everything.
- **Now:** per-session API-reported usage from the harness session store
  (`opencode.db`, `session_v2`: `tokens_input`, `tokens_output`,
  `tokens_reasoning`, `tokens_cache_read/write`), joined to legs by
  session title + tool-call counts from `session_message`. Agent
  compliance is no longer load-bearing for counting.
- **Primary metric:** input + output (non-cached burn). Cache re-reads
  (prefix reprocessing — real compute, usually billed discounted) shown
  alongside, not folded in. Reasoning is 0 throughout (folded into
  output by these providers).
- Repro: the mapping table in §2 + `opencode.db` queries. Analysis
  scripts used: `bench_temp/ocmap.py` (session→leg stats),
  `bench_temp/occtx.py` (fresh/cache/peak split).

## Session→leg mapping (audit for validation)

| Leg | Session (prefix) | Model | Harness tools vs grade calls |
|---|---|---|---|
| A-G5-att2 | `Go A-G5 leg attempt 2` | spark | 7 / 7 |
| B-G5-att1 | `Go B-G5 baseline leg` | spark | 16 / 16 |
| A-G1-att1 | `Go A-G1 leg attempt 1` | spark | 5 / 5 |
| B-G1-att1 | `Go B-G1 baseline leg` | spark | 13 / 10 |
| A-G1-Qwen | `Go G1 Qwen attempt 1` | Qwen | 31 / 8 (grade counted tricorder-only) |
| A-G3-att1 | `Go A-G3 leg attempt 1` | spark | 7 / 6 |
| B-G3-att1 | `Go B-G3 baseline leg` | spark | 8 / 8 |
| A-Q1-att1 | `VW A-Q1 leg attempt 1` | spark | 7 / 6 — RUNLOG tags this row "(Nemotron)" but no Nemotron Q1 session exists; this is the recorded leg |
| B-Q1-att1 | `VW B-Q1 baseline leg` | spark | 11 / 11 |
| A-Q2-att1 | `VW A-Q2 leg attempt 1` | Nemotron | 18 / 16 |
| A-Q2-att2 | `VW A-Q2 re-run strict ladder` | Nemotron | 10 / 5 |
| B-Q2-att1 | `VW B-Q2 baseline leg` | Nemotron | 6 / 5 |
| A-Q3-att1 | `VW A-Q3 Qwen attempt 1` | Qwen | 6 / 6 |
| B-Q3-att1 | `VW B-Q3 baseline leg` | Nemotron | 11 / 8 |
| A-Q4-att1 | `VW A-Q4 Qwen attempt 1` | Qwen | 10 / 9 |
| B-Q4-att1 | `VW B-Q4 baseline leg` | Nemotron | 25 / 20 |

Excluded (not recorded legs): pre-series trials (`Trial tricorder-CLI*`,
`Go A/B-leg G*`), the against-instruction Qwen G5 attempt, the
superseded muse-spark Q2-att1 duplicate (grade names Nemotron), all-zero
provider rows (usage unreported — unmetered, not zero), all Rails /
Elixir / Vue sessions (different rounds), and the voided r02 sessions
(round voided 2026-09-25; sessions persist in the DB but are excluded).

## True tally (harness input+output; artifact figures in parens, retired)

| Pair | A truth (was) | B truth (was) | True A/B (was) |
|---|---|---|---|
| Go G5 | 15,251 (3,068) | 27,454 (4,740) | **0.56×** (0.65×) |
| Go G1 | 15,498 (4,273) | 29,951 (13,882) | **0.52×** (0.31×) |
| Go G3 | 17,834 (4,916) | 18,536 (6,716) | **0.96×** (0.73×) |
| VW Q1 | 34,323 (5,541) | 18,612 (13,967) | **1.84× — INVERSION** (0.40×) |
| VW Q2-att1 | 174,109 (12,121) | 83,497 (18,721) | **2.09× — INVERSION** (0.65×) |
| VW Q2-att2 | 123,583 (15,019) | 83,497 (18,721) | **1.48× — INVERSION** (0.80×) |
| VW Q3 | 14,198 (4,638) | 112,009 (10,713) | **0.13×** (0.43×) |
| VW Q4 | 17,510 (6,449) | 265,849 (12,090) | **0.07×** (0.53×) |
| Go G1-Qwen (unpaired) | 25,499 (8,361) | — | — |
| **Paired aggregate** | **412,306** | **555,908** | **0.74×** (published 0.30×) |

Absolute artifact totals were undercounted ~5–35× (worse on short legs,
where fixed prompt/reasoning costs dominate). Including cache_read moves
the aggregate to ~0.80× and flips G3 to 1.05× — verdicts robust except
G3, which is parity either way.

Found while mapping: RUNLOG's aggregate line ("16,628 A-tokens") does
not match its own per-leg table (sums to 64,386). The published
arithmetic was broken before truth entered it. Noted, not repaired —
history stands.

## Context differential (what the window actually holds)

Per-leg fresh input vs cache re-reads vs output, plus peak context in
any single call (the 16GB-VRAM number — decides OOM, not totals):

| Leg | Fresh in | Cache re-read | Output | Peak ctx/call | Cache share |
|---|---|---|---|---|---|
| A-G5 | 13,724 | 67,223 | 1,527 | 13,281 | 83% |
| B-G5 | 24,051 | 229,136 | 3,403 | 23,280 | 91% |
| A-G1 | 14,095 | 36,804 | 1,403 | 13,712 | 72% |
| B-G1 | 27,494 | 158,826 | 2,457 | 26,712 | 85% |
| A-G3 | 16,056 | 80,663 | 1,778 | 15,620 | 83% |
| B-G3 | 16,769 | 75,302 | 1,767 | 16,443 | 82% |
| A-Q1 | 32,706 | 178,967 | 1,617 | 32,343 | 85% |
| B-Q1 | 16,587 | 104,042 | 2,025 | 15,774 | 86% |
| A-Q2a1 | 171,202 | 207,360 | 2,907 | 28,352 | 55% |
| A-Q2a2 | 121,860 | 120,960 | 1,723 | 30,149 | 50% |
| B-Q2 | 82,094 | 21,600 | 1,403 | 42,723 | 21% |
| A-Q3 | 12,731 | 65,070 | 1,467 | 13,213 | 84% |
| B-Q3 | 110,147 | 95,040 | 1,862 | 24,718 | 46% |
| A-Q4 | 15,306 | 112,775 | 2,204 | 15,961 | 88% |
| B-Q4 | 260,874 | 371,520 | 4,975 | 43,764 | 59% |

Context is 50–94% re-reads: the window fills with accumulation, not
answers. Fresh information per leg is 13–170k; re-reading history is
65–370k. Peak single-call context runs 13–44k.

## Reading (documented reality, not rewritten history)

- Overall **0.74×** true (was: published 0.30×). A real saving with a
  defined shape, not the headline that was claimed.
- Inversions (Q1, both Q2s) are where the answer is single-file and
  greppable: tricorder's fixed overhead — directive-in-context plus
  MAP/T1 renders, repaid every subsequent call — exceeds a short grep
  chain. Expected economics, now measured.
- Wins (Q3 0.13×, Q4 0.07×, Go 0.5–1.0×) are where search is scattered
  across files or trees: B-side history balloons instead (B-Q4 peaked
  43.7k over 25 calls).
- Conservation levers, ranked by this data: (a) fewer calls — each one
  re-pays the entire accumulated context at peak price; (b) lighter
  prompt prefix — the directive rides every call's cache; (c) smaller
  payloads in history — MAP/T1 renders linger after serving their purpose.
- Citation/compliance grades are unaffected by this file (they never
  measured tokens). Artifact token tables remain in place, retired for
  future tallies.
