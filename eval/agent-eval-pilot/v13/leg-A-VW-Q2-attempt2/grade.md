# Leg A-VW-Q2 attempt 2 — GRADE

## Verdict: PASS (answer correct) — **Ladder compliance: FAIL**

Ground truth cited correctly, but agent violated "stop at the first
rung that answers."

## Tokens

| Step | Tokens | Note |
|---|---|---|
| MAP 2048 | 2,040 | generic hits |
| detect ×2 | 2,148 | right area |
| read admin.rs FULL | 10,349 | **over-read; should have stopped at TIER 1** |
| read auth.rs range | 482 | confirmatory |
| **Total** | **15,019** | **2.5× attempt 1 (6,074)** |

## Compliance

- Ladder order: MAP → DETECT → DETECT → READ (full) → READ
- **Violation**: did not stop at first rung that answered.
  - DETECT #3 found `AdminToken`/`validate_token` → next rung should be
    TIER 1 on `admin.rs:857` (which in attempt 1 answered at 2,054 tok).
  - Instead: read entire admin.rs (10,349 tok).
- Zero NL; exact-first on detects. Citation discipline clean.

## Findings

1. **Agent compliance is the variable** — same prompt, same model,
   different behavior. Attempt 1 stopped at TIER 1 (6,074 tok);
   attempt 2 over-read (15,019 tok).
2. **Ladder enforcement needed in grading** — a PASS answer with ladder
   violation should be flagged; the cap exists to force discipline.
3. **Tone of prompt matters** — "STOP AT THE FIRST RUNG THAT ANSWERS"
   in bold did not override the model's tendency to over-read.

## Model Tracking

| Leg | Model | Provider |
|---|---|---|
| A-VW-Q2 attempt 1 | Nemotron 3 Ultra Free | opencode |
| A-VW-Q2 attempt 2 | Nemotron 3 Ultra Free | opencode |
| B-VW-Q2 | Nemotron 3 Ultra Free | opencode |
| All prior v1.3 legs | Nemotron 3 Ultra Free | opencode |

All v1.3 legs to date have used the **default model (Nemotron 3 Ultra
Free / opencode)** — no external model calls.