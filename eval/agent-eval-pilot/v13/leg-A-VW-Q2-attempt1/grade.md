# Leg A-VW-Q2 attempt 1 — GRADE

## Verdict: PASS

Ground truth (`AdminToken` guard `src/api/admin.rs:857`, `validate_token`
`src/api/admin.rs:229`, JWT chain `auth.rs`) cited with lines and
verified by reads, plus login flow, cookie creation, claims, issuer.
16/15 calls (1 over; last two confirmatory). First VW leg where MAP rung
returned usable hits (ranked, though answer not in top slice).

## Tokens

| Cmd | Step | Tokens | Note |
|---|---|---|---|
| 1 | MAP 2048 | 2,040 | fitted; generic hits, no admin auth in top |
| 2 | detect "admin panel..." | 857 | right area |
| 3 | detect "admin token..." | 1,004 | right area |
| 4 | tier 1 admin.rs:857 | 2,054 | located AdminToken |
| 5–7 | reads admin.rs (3 ranges) | 2,434 | guard, login, validate |
| 8 | detect decode_admin | 187 | auth.rs |
| 9 | read auth.rs decode | 647 | decode_admin, decode_jwt |
| 10 | detect claims | 206 | generate_admin_claims |
| 11 | read claims | 356 | generate_admin_claims |
| 12 | detect encode_jwt | 1,029 | JWT encoding |
| 13 | read encode | 566 | encode_jwt, decode_jwt |
| 14 | detect claims struct | 540 | BasicJwtClaims |
| 15 | read issuer | 201 | JWT_ADMIN_ISSUER |
| 16 | confirmatory | — | — |
| **Total** | | **12,121** | |

## Compliance

- Full ladder as written: MAP → DETECT → TIER 1 → READ → DETECT → READ.
- Exact-first: all detect queries were identifier guesses; zero NL.
- No junk encountered; v1.2 untriggered. Citation discipline clean.

## Findings

1. **MAP returned ranked hits at VW scale** — first leg where rung 1
   mechanically answers (seconds, fitted) and delivers hits. Answer was
   not in the top slice (generic `jQuery`/`Cipher` names), so ladder
   correctly continued. Top-slice recall at floor budget remains a
   product question.
2. **TIER 1 answered the question directly** — cmd 4 hit `AdminToken`
   at line 857 with context; the agent could have stopped at rung 5
   without reads. This is the intended ladder behavior.
3. **Token count dominated by MAP + TIER 1 renders** (4,094 of 12,121).
   At 506 files these are still small; the cost class is different from
   Go where they time out.