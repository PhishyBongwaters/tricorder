# Leg A-VW-Q2 attempt 1 — TRANSCRIPT (agent report, verbatim)

Model: default (me). 16/15 calls used (1 over cap; last two confirmatory).
Prompt: `v13/leg-A-VW-Q2-attempt1/prompt.md` (full ladder incl. MAP rung 1;
canonical DB, no `--db-path`).

## Answer (as returned)

Admin panel authenticates via **cookie-based JWT session** backed by an
initial token verification against configured `ADMIN_TOKEN`.

1. **Request guard `AdminToken`** (`src/api/admin.rs:857–898`): every
   admin route requires it; extracts client IP; if admin token not
   disabled (`!CONFIG.disable_admin_token()`, :870), reads cookie
   `COOKIE_NAME` (:873–874), validates JWT via `decode_admin()` (:886).
   Success → `Outcome::Success(AdminToken { ip })` (:894–896); missing/
   invalid → 401 or forward to login (:880–883).

2. **JWT validation `decode_admin` → `decode_jwt`**
   (`src/auth.rs:155–156`, `112–129`): verifies RSA signature
   (`PUBLIC_RSA_KEY`, :120), algorithm (`JWT_ALGORITHM`, :113), exp
   (`validate_exp=true`, :115), nbf (`validate_nbf=true`, :116), issuer
   matches `JWT_ADMIN_ISSUER` = `"{domain_origin}|admin"` (:117, :56).

3. **Login & session creation `post_admin_login`**
   (`src/api/admin.rs:184–227`): accepts `token` form field; validates
   against configured `ADMIN_TOKEN` via `validate_token()` (:202,
   :229–247) — plain-text (constant-time `ct_eq`, :245) or Argon2 PHC
   hash (if `$argon2` prefix, :232–243); on success, generates claims
   via `generate_admin_claims()` (`src/auth.rs:528–536`): `nbf`=now,
   `exp`=now+`admin_session_lifetime`, `iss`=`JWT_ADMIN_ISSUER`,
   `sub`=`"admin_panel"` (:530–535); signs JWT via `encode_jwt()`
   (`src/auth.rs:105–110`); sets HTTP-only, Secure, SameSite=Strict
   cookie scoped to admin path (:207–214).

4. **Configuration** (`src/config.rs:1630–1631`, `src/api/admin.rs:41–43`):
   `ADMIN_TOKEN` enables panel; empty ⇒ disabled (`admin_disabled`
   catcher, :101); `DISABLE_ADMIN_TOKEN` forces disable;
   `ADMIN_SESSION_LIFETIME` controls TTL (default 30 min).

## Commands (in order, `--root <vw> --format json` throughout)

| # | Step | Tokens | Hits | Useful |
|---|---|---|---|---|
| 1 | MAP 2048 | 2,040 | ~40 (all 0.0015 rank, jQuery) | ❌ noise |
| 2 | detect "admin panel authenticate" | 857 | 8 | ✅ found admin.rs, auth.rs |
| 3 | detect "admin token authentication" | 1,004 | 10 | ✅ AdminToken, validate_token |
| 4 | tier 1 src/api/admin.rs:857 | 2,054 | 40+ | ✅ located AdminToken |
| 5 | read admin.rs 857–926 | 957 | — | ✅ AdminToken::from_request |
| 6 | read admin.rs 149–228 | 775 | — | ✅ post_admin_login, cookie |
| 7 | read admin.rs 228–303 | 702 | — | ✅ validate_token, login routes |
| 8 | detect "decode_admin" | 187 | 2 | ✅ decode_admin in auth.rs |
| 9 | read auth.rs 145–203 | 647 | — | ✅ decode_admin, decode_jwt |
| 10 | detect "generate_admin_claims" | 206 | 2 | ✅ claims generation |
| 11 | read auth.rs 525–563 | 356 | — | ✅ generate_admin_claims |
| 12 | detect "encode_jwt" | 1,029 | 9 | ✅ JWT encoding |
| 13 | read auth.rs 105–153 | 566 | — | ✅ encode_jwt, decode_jwt |
| 14 | detect "BasicJwtClaims" | 540 | 5 | ✅ claims struct |
| 15 | read auth.rs 55–64 | 201 | — | ✅ JWT_ADMIN_ISSUER |
| 16 | detect "BasicJwtClaims" (confirm) | — | — | confirmatory |

## Payload artifacts (post-leg replays against canonical DB)

- `step_map.txt`, `step_detect1.txt`, `step_detect2.txt`,
  `step_tier1.txt`, `step_detect_decode.txt`, `step_detect_claims.txt`,
  `step_detect_encode.txt`, `step_detect_claims_struct.txt` — raw CLI
  stdout. `step_read_*.txt` (6 files) — file slices as read.
  Metered with `meter_and_reads.py`.