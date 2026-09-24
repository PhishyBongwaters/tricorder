# Leg B-VW-Q1 attempt 2 — GRADE (Qwen model)

## Verdict: PASS — at cap (15/15), citations verified, no integrity flag

Baseline found the file via listings+greps (830 tok finding) then read
4 whole files. Self-count confabulation in preamble noted, record stands
on the enumerated 15.

## Tokens

| Step | Tokens | Note |
|---|---|---|
| listings 5 × + greps 5 × | 843 | finding under 1k |
| reads 5 × (100–whole) | 10,365 | 92% of leg |
| **Total** | **11,208** | |

## VW-Q1 pair, Qwen/Qwen (frozen directive)

| | Calls | Tokens |
|---|---|---|
| **A attempt 2** | **7** | **4,538** |
| B attempt 2 | 15 | 11,208 |
| **A/B** | **0.47×** | **0.40×** |
| (old: A att.1 Nemotron 6/5,541 vs B att.1 11/13,967 → 0.40×) | | |

Pair holds at 0.40× across models and directive versions — the most
stable number in the program so far. A-side: MAP-skip + 85-line reads.
B-side: whole-file reads dominate identically in both attempts.

## Model Tracking

| Leg | Model | Provider |
|---|---|---|
| A/B-VW-Q1 att.2 | **Qwen** | **llamacpp** |
| A-VW-Q1 att.1, B-VW-Q1 att.1 | Nemotron/default | opencode |
| Rest of Qwen-everywhere program | Qwen | llamacpp |
