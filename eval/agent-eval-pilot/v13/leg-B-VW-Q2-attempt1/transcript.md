# Leg B-VW-Q2 attempt 1 — TRANSCRIPT (agent report, verbatim)

Model: default (me — same model both sides). 5/20 calls used. Prompt:
`v13/leg-B-VW-Q2-attempt1/prompt.md` (baseline tools only).

## Answer (as returned)

Admin panel uses **cookie-based JWT session** with initial **admin token login**:

1. **AdminToken guard** (`src/api/admin.rs:857–898`): every protected route requires it; extracts IP; if admin token not disabled, reads `VW_ADMIN` cookie (:873–874), validates via `decode_admin()` (:886); missing/invalid → 401 or forward to login (:880–883); success → `AdminToken { ip }` (:894–896).

2. **JWT validation `decode_admin` → `decode_jwt`** (`src/auth.rs:155–156`, `112–129`): verifies RSA signature (`PUBLIC_RSA_KEY`, :120), algorithm (`JWT_ALGORITHM`, :113), exp (`validate_exp=true`, :115), nbf (`validate_nbf=true`, :116), issuer matches `JWT_ADMIN_ISSUER` = `"{domain_origin}|admin"` (:117, :56).

3. **Login `post_admin_login`** (`src/api/admin.rs:184–227`): accepts `token` form field; validates against `ADMIN_TOKEN` via `validate_token()` (:202, :229–247) — plain-text (`ct_eq`, :245) or Argon2 PHC hash (if `$argon2` prefix, :232–243); on success generates claims via `generate_admin_claims()` (`src/auth.rs:528–536`): `nbf`=now, `exp`=now+`admin_session_lifetime`, `iss`=`JWT_ADMIN_ISSUER`, `sub`=`"admin_panel"` (:530–535); signs JWT via `encode_jwt()` (`src/auth.rs:105–110`); sets HTTP-only, Secure, SameSite=Strict cookie scoped to `/admin` (:207–214).

4. **Configuration**: `ADMIN_TOKEN` enables panel; empty ⇒ disabled (`admin_disabled` catcher, :101); `DISABLE_ADMIN_TOKEN` forces disable; `ADMIN_SESSION_LIFETIME` controls TTL.

## Commands (in order, relative to VW repo)

1. read repo root (29 entries incl `src/`)
2. read `src` (incl `api/`)
3. read `src/api` (incl `admin.rs`, `auth.rs`)
4. read `src/api/admin.rs` full (927 lines — guard, login, validate_token, routes)
5. read `src/auth.rs` full (1341 lines — JWT, decode_admin, claims, RSA)

## Payload artifacts

`step*.txt` reproduced post-leg from disk by `meter.py`, plus `meter.json`. No tricorder command anywhere — baseline-only audit clean.