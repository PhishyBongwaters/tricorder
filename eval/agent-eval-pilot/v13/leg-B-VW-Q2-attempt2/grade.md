# Leg B-VW-Q2 attempt 2 — GRADE (Qwen model)

## Verdict: PASS — 6/15, correct, no flags

Clean baseline: 2 listings + 1 grep found everything (716 tok finding),
2 whole-file reads answered (18,549 tok). Counted correctly.

## Tokens

| Step | Tokens | Note |
|---|---|---|
| listings + greps | 982 | finding under 1k |
| reads 2 whole files | 18,549 | 95% of leg |
| **Total** | **19,531** | |

## VW-Q2 pair, Qwen/Qwen (frozen directive)

| | Calls | Tokens |
|---|---|---|
| **A attempt 3** | **19 (claimed 15)** | **7,943** |
| B attempt 2 | 6 | 19,531 |
| **A/B** | **3.2× calls** | **0.41× tokens** |

Fewest-call B-leg in the program (6) is also among the priciest (19.5k):
calls and tokens point opposite ways here — more evidence for the RUNLOG
grading principle. Old Nemotron A (~12–15k) vs old B (5 calls, 18,721)
was 0.65–0.80×; Qwen A/B lands 0.41×.

## Model Tracking

| Leg | Model | Provider |
|---|---|---|
| A/B-VW-Q2 att.3/att.2 | **Qwen** | **llamacpp** |
| A-VW-Q2 att.1/2, B-VW-Q2 att.1 | Nemotron/default | opencode |
| Rest of Qwen-everywhere program | Qwen | llamacpp |
