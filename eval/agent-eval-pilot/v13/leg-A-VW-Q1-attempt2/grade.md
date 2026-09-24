# Leg A-VW-Q1 attempt 2 — GRADE (Qwen model)

## Verdict: PASS — **compliant (minor: read-counting, T1 junk)**

Exact ground-truth citation (file + :115 + symbol). 7/15 calls.

## Tokens

| Step | Tokens | Note |
|---|---|---|
| probe | 64 | held |
| MAP | 0 | skipped (4th leg running) |
| detects 2 × + symbols | 1,405 | all capped at 5, all hits |
| T1 (junk jQuery) | 2,040 | 45% of leg, unread |
| reads 2 × (85 + 20 ln) | 1,029 | bodies + caller |
| **Total** | **4,538** | **0.82× att.1 (5,541)** |

## Compliance

- Probe → exact detect → MAP skip → symbols → targeted reads: ladder
  textbook. v1.2 discipline on the T1 junk (unread, moved to reads).
- Minor: agent counts 5 calls (reads "via file tool, not counted") —
  harness counts every invocation; true 7/15, in cap regardless.
- **New finding — T1 has no junk defense.** v1.2 guards detect (retry
  exact guess, never read junk) but T1 fires on prior context and
  delivered 2,040 tok of vendored jQuery with no gate. Without step 5
  this leg meters 2,498 (0.45× att.1). Candidate for a future rule;
  logged, NOT imposed (directive frozen for the program).

## VW-Q1 across attempts

| | Att.1 (Nemotron, v1–v1.3) | Att.2 (Qwen, frozen) |
|---|---|---|
| Calls | 6 | 7 |
| Tokens | 5,541 | 4,538 (0.82×) |
| MAP | paid (map-first era) | skipped |

## Model Tracking

| Leg | Model | Provider |
|---|---|---|
| A-VW-Q1 att.2 | **Qwen** | **llamacpp** |
| A-VW-Q1 att.1 | Nemotron | opencode |
| Rest of Qwen-everywhere program | Qwen | llamacpp |
