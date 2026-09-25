# Leg A-VW-Q1 — GRADE (Qwen model)

## Verdict: PASS — compliant with minor v1.4 exceedance

Ground truth (`validate_totp_code`,
`src/api/core/two_factor/authenticator.rs:115`) cited with line +
verified body; wrapper (`:101`) and caller (`identity.rs:828`) confirm
the chain. 5/15 calls.

## Tokens (agent-visible result payloads, `meter_leg.py`, tiktoken cl100k)

| Step | Tokens | Note |
|---|---|---|
| 1 probe-digest | 36 | 423 code files |
| 2 smart-map | 45 | generic error.rs symbols, no TOTP hit → MAP path declined correctly |
| 3 detect `totp` --max-results 5 | 140 | exact hit `validate_totp_code_str` :101 + caller ref :828 |
| 4 read authenticator.rs | 289 | full file 219 lines — see compliance note |
| 5 read identity.rs 810–859 | 124 | caller dispatch verified |
| **Total** | **634** | |

## Compliance

- Ladder: probe → smart-map → detect → read → read. Exact-first obeyed
  (first substantive query the identifier guess `totp` at --max-results 5).
- v1.7 rung 1 obeyed: `--smart-map` ran probe + one exact detect, no
  exact hit → MAP correctly not paid (45 tok vs 2,040 MAP rung in v13 att-1).
- Minor v1.4 exceedance: step 4 read the full 219-line file instead of
  one ≤120-line body window. No chained windows; answer was in hand.
  Tagged, not failed.

## Findings

1. **VW-Q1 collapses under v1.7**: 634 tok vs v13 attempt-1's 5,541
   (0.11×). Drivers: smart-map declined the 2k MAP rung on a miss
   (was: MAP paid blind), exact-first detect at cap 5, Qwen stopping at
   first answer. The thin VW DB (93 ranked files) did not hurt: the
   answer came via detect, not MAP.
2. Smart-map miss path works as designed: 45 tokens to learn "MAP has
   nothing," then down the ladder.

## Model tracking

- Vehicle: `llamacpp/Qwen` (`Qwen3.6-35B-A3B-UD-Q4_K_M.gguf`), 5/15 calls.
