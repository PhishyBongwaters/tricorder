# Leg A-VW-Q3 attempt 1 — GRADE (Qwen model)

## Verdict: PASS — **Ladder compliant, exact-first, zero NL**

Ground truth (`Collection::can_access_collection`, `collection.rs:155`)
cited with lines and verified by reads, plus supporting functions in
`collection.rs` and `group.rs`. 6/15 calls.

## Tokens

| Step | Tokens | Note |
|---|---|---|
| MAP 2048 | 2,040 | noise |
| symbols "org_collection_access" | 1,681 | key symbols |
| symbols "can_access_collection" | 307 | confirmed |
| reads (3 ranges) | 610 | verified |
| **Total** | **4,638** | |

## Compliance

- Full ladder: MAP → SYMBOLS → SYMBOLS → READ → READ → READ
- **Stopped at first rung that answered** (READ rung)
- Exact-first on both symbol queries; zero NL
- Zero junk encountered; citation discipline clean

## Model Tracking

| Leg | Model | Provider |
|---|---|---|
| A-VW-Q3 attempt 1 | **Qwen** | **llamacpp** |
| All prior v1.3 legs | Nemotron 3 Ultra Free | opencode |

## Findings

1. **Qwen worked cleanly** — no tool loops, no hallucinations, followed ladder exactly. First external-model leg to pass without issues.
2. **Smallest VW A-leg yet** — 4,638 tokens vs 12,121 (Q2 attempt 1) / 15,019 (Q2 attempt 2). Exact-first symbol queries on a small repo with good name matches = very efficient.
3. **MAP still noise** — at 506 files MAP rung works mechanically but returns generic hits; exact-first symbols bypassed it cleanly.

## Comparison (VW A-legs)

| Leg | Model | Calls | Tokens | Ladder |
|---|---|---|---|---|
| Q1 | Nemotron | 6 | 5,541 | PASS |
| Q2 attempt 1 | Nemotron | 16 | 12,121 | Over cap, over-read |
| Q2 attempt 2 | Nemotron | 5 | 15,019 | Compliance fail |
| **Q3** | **Qwen** | **6** | **4,638** | **PASS, compliant** |