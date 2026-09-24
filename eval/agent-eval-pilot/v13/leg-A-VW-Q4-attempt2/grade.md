# Leg A-VW-Q4 attempt 2 — GRADE (Qwen model)

## Verdict: PASS — **compliant, MAP skipped via --smart-map**

Correct answer: dual-channel notifications (WebSocket + Push), orchestrated
by `send_cipher_update` (notifications.rs:430–477) calling `create_update`
(notifications.rs:627, MessagePack), `send_update` (notifications.rs:354,
WS broadcast), `push_cipher_update` (push.rs:160, non-org only). Called
from ciphers.rs:567/842/922. 11/15 calls, 3,305 tokens. All citations exact.

## Tokens

| Step | Tokens | Note |
|---|---|---|
| --smart-map | 441 | probe + detect + MAP-skip in one call |
| detect (confirm) | 441 | redundant but cheap |
| symbols | 389 | range confirm |
| reads 8 × | 2,034 | targeted bodies |
| **Total** | **3,305** | |

## Compliance

- v1.6 obeyed perfectly: `--smart-map` ran probe + one exact detect → exact
  hit → MAP skipped. All first passes capped at 5. Reads ≤30 lines,
  one window per file. Ladder: smart-map → targeted reads → answer.
- Zero ladder violations. Agent used the v1.6 tool feature exactly as
  designed.

## Attempts 1 → 2 (Smart-map)

| | Att.1 (Nemotron, map-first) | Att.2 (Qwen, --smart-map) |
|---|---|---|
| Calls | 9 | 11 |
| Tokens | 6,449 | **3,305** |
| MAP | paid | skipped (tool) |
| Citations | exact | exact |

**Smart-map cuts tokens in half** (6,449 → 3,305, 0.51×) while keeping
exact citations. Tool absorbs the protocol logic; agent just guesses
the symbol and runs one command.

## Model Tracking

| Leg | Model | Provider |
|---|---|---|
| A-VW-Q4 att.2 | **Qwen** | **llamacpp** |
| A-VW-Q1/2/3 att.2, B-VW-Q1/2/3 att.2 | Qwen | llamacpp |
| A-VW-Q4 att.1 | Nemotron | opencode |
| Rest of Qwen-everywhere program | Qwen | llamacpp |

## Findings

1. **--smart-map is the v1.6 solution realized**: One flag replaces
   probe+detect+conditional MAP logic. Agent: "guess symbol, run
   smart-map, done."
2. **Token efficiency**: 3,305 vs 6,449 (0.51×) — cuts the original
   map-first cost in half while keeping MAP-skip discipline.
3. **Agent simplicity**: 11 commands vs 9 original — agent just
   guesses symbol, runs smart-map, reads targeted bodies.