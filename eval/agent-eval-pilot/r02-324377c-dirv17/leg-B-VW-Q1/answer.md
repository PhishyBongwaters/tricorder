# Final Answer: Where is TOTP two-factor code verification implemented?

## Primary Implementation

**File:** `D:\Projects\Tricorder-Testing-Repos\vaultwarden\src\api\core\two_factor\authenticator.rs`

### Core Verification Function

**`validate_totp_code`** — `src/api/core/two_factor/authenticator.rs:115-181`
- `pub async fn validate_totp_code(user_id, totp_code, secret, ip, conn)`
- Uses the `totp_lite` crate (dependency: `totp-lite = "2.0.1"` in `Cargo.toml:148`)
- Decodes the base32-encoded secret (line 124)
- Computes TOTP codes using `totp_custom::<Sha1>(30, 6, &decoded_secret, time)` (line 149)
  - 30-second time step, 6-digit codes, SHA-1 HMAC
- Iterates ±time-drift steps (line 143) to handle clock skew
- Enforces replay protection via `twofactor.last_used` (line 152, 160)
- Returns `Ok(())` on match, errors on mismatch (lines 165-180)

**`validate_totp_code_str`** — `src/api/core/two_factor/authenticator.rs:101-113`
- `pub async fn validate_totp_code_str(user_id, totp_code, secret, ip, conn)`
- Public wrapper that validates the code is all-numeric, then delegates to `validate_totp_code`

### TOTP Setup/Activation

**`activate_authenticator`** — `src/api/core/two_factor/authenticator.rs:56-94`
- `POST /two-factor/authenticator`
- Validates user credentials via `PasswordOrOtpData::validate()` (line 68)
- Validates the base32 key is 20 bytes (lines 72-80)
- Calls `validate_totp_code()` at line 83 to verify the user-entered TOTP code
- Saves the 2FA provider to the database

**`generate_authenticator`** — `src/api/core/two_factor/authenticator.rs:22-45`
- `POST /two-factor/get-authenticator`
- Generates a random 20-byte base32-encoded TOTP secret (line 33)
- Returns the secret key for the user to scan with their authenticator app

### TOTP Disable

**`disable_authenticator`** — `src/api/core/two_factor/authenticator.rs:191-219`
- `DELETE /two-factor/authenticator`
- Verifies master password, then deletes the TwoFactor record

## Module Structure

**`src/api/core/two_factor/mod.rs`** — aggregates all 2FA providers:
- `pub mod authenticator;` (line 27)
- `routes()` (line 71-88) includes `authenticator::routes()` (line 80)
- `is_twofactor_provider_usable()` (line 39-69) — `TwoFactorType::Authenticator` always returns true (line 48)

## Configuration

**`src/config.rs:720-722`** — `authenticator_disable_time_drift` config flag controls whether TOTP codes from adjacent 30-second windows are accepted.

## External Dependency

**`Cargo.toml:148`** — `totp-lite = "2.0.1"` — the TOTP computation library providing `totp_custom::<Sha1>()`.

## Summary

TOTP two-factor code verification in Vaultwarden is implemented in a single dedicated module at `src/api/core/two_factor/authenticator.rs`. The core verification logic is in the `validate_totp_code` function (line 115), which uses the `totp-lite` crate to compute expected TOTP codes from a base32-encoded secret and compares them against user-supplied codes, with time-drift tolerance and replay protection.
