# Leg A-VW-Q3 attempt 3 — GRADE (Qwen model)

## Verdict: PASS — **compliant, MAP skipped via --smart-map (v1.6 tool feature)**

Correct answer: `is_coll_manageable_by_user` (collection.rs:570), 5-path SQL,
auth.rs enforcement at :888/:970, wrapper :629. Exact citations throughout.
6/15 calls, **2,834 tokens**.

## Tokens

| Step | Tokens | Note |
|---|---|---|
| --smart-map | 598 | probe + detect + MAP-skip in one call |
| detect (confirm) | 598 | redundant but cheap |
| reads 3 × | 1,313 | targeted bodies |
| symbols | 325 | range confirm |
| **Total** | **2,834** | **0.33× att.2 (8,708)** |

## Compliance

- v1.6 obeyed perfectly: `--smart-map` ran probe + one exact detect → exact
  hit → MAP skipped. All first passes capped at 5. Reads ≤120 lines,
  one window per file. Ladder: probe → detect → reads → symbols → answer.
- Zero ladder violations. Agent used the v1.6 tool feature exactly as
  designed.

## Attempts 1 → 2 → 3 (Smart-map)

| | Att.1 (Nemotron, map-first) | Att.2 (Qwen, v1.6 manual) | **Att.3 (Qwen, --smart-map)** |
|---|---|---|---|
| Calls | 6 | 15 (cap) | **6** |
| Tokens | **4,638** | 8,708 | **2,834** |
| MAP | paid | skipped (manual) | skipped (tool) |
| Ratio vs B | 0.33× | 0.62× | **0.20×** |

**Smart-map RECOVERS the map-first advantage** while keeping v1.6
ladder compliance. Tokens drop from 8,708 → 2,834 (0.32×) vs manual
v1.6, beating even the original map-first 4,638. The tool now makes
the right decision automatically.

## Model Tracking

| Leg | Model | Provider |
|---|---|---|
| A-VW-Q3 att.3 | **Qwen** | **llamacpp** |
| A-VW-Q1/2 att.2, B-VW-Q1/2 att.2 | Qwen | llamacpp |
| A-VW-Q3/4 att.1 | Nemotron | opencode |
| Rest of Qwen-everywhere program | Qwen | llamacpp |

## Findings

1. **--smart-map is the v1.6 solution**: Tool now makes the
   probe→detect→conditional MAP decision internally. Agent uses one
   flag instead of 3+ commands.
2. **Token explosion solved**: 2,834 vs 8,708 manual v1.6, and beats
   map-first 4,638. Smart-map + Qwen = best of both worlds.
3. **Agent simplicity**: 6 commands vs 15+ manual. Agent just guesses
   the exact symbol and runs one command.