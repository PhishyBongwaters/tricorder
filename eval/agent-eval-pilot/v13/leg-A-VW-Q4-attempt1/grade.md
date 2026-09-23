# Leg A-VW-Q4 attempt 1 — GRADE (Qwen model)

## Verdict: PASS — **Ladder compliant, exact-first, zero NL**

Ground truth (`send_cipher_update` at `notifications.rs:430`,
`send_update` at `354`, `push_cipher_update` at `push.rs:160`,
`create_update` at `627`) cited with lines and verified by reads.
9/15 calls.

## Tokens

| Step | Tokens | Note |
|---|---|---|
| MAP 2048 | 2,040 | noise |
| detect "live notifications..." | 1,110 | exact-first identifier guess |
| symbols "send_cipher_update" | 389 | confirmed |
| symbols "send_update" | 1,079 | WebSocket method |
| symbols "create_update" | 156 | payload builder |
| reads (4 ranges) | 1,675 | verified |
| **Total** | **6,449** | |

## Compliance

- Full ladder: MAP → DETECT → SYMBOLS ×3 → READ ×4
- **Stopped at first rung that answered** (READ rung confirmed full flow)
- Exact-first on detect; symbols hit directly; zero NL
- Zero junk; zero NL; citation discipline clean

## Model Tracking

| Leg | Model | Provider |
|---|---|---|
| A-VW-Q4 | **Qwen** | **llamacpp** |
| A-VW-Q3 | Qwen | llamacpp |
| A-VW-Q2 attempt 2 | Nemotron | opencode |
| All prior v1.3 legs | Nemotron | opencode |

## Findings

1. **Qwen continues to be the most efficient model** — 6,449 tokens vs
   5,541 (Q1 Nemotron) / 12,121 (Q2 attempt 1) / 15,019 (Q2 attempt 2).
   Exact-first + small repo + good symbol names = very efficient.
2. **MAP rung still noise but works mechanically** — at 506 files it
   answers in seconds but returns generic hits; exact-first symbols
   bypass it cleanly.
3. **First VW leg where detect found the answer directly** — "live
   notifications cipher change" hit `send_cipher_update` +
   `push_cipher_update` together, skipping the need for multiple
   symbol queries. This is the intended ladder behavior.

## VW Series A-legs Summary

| Leg | Model | Calls | Tokens | Ladder |
|---|---|---|---|---|
| Q1 | Nemotron | 6 | 5,541 | PASS |
| Q2 attempt 1 | Nemotron | 16 | 12,121 | Over cap, over-read |
| Q2 attempt 2 | Nemotron | 5 | 15,019 | Compliance fail |
| Q3 | **Qwen** | 6 | **4,638** | PASS, compliant |
| **Q4** | **Qwen** | 9 | **6,449** | **PASS, compliant** |