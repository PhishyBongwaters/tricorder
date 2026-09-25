| # | cmd | result summary |
|---|-----|----------------|
| 1 | `Get-ChildItem` vaultwarden root dirs | Found .github, .repomap.tags.cache.v1, .tricorder, docker, macros, migrations, playwright, resources, src, tools |
| 2 | `Select-String -Pattern "TOTP"` case-sensitive | 1 hit in config.rs:720 (comment about time drift) |
| 3 | `Select-String -Pattern "totp"` case-insensitive | 2 hits in config.rs:720-722 (comments about authenticator time drift) |
| 4 | `Select-String -Pattern "totp|two.?factor|authenticator|otp"` case-insensitive | 15 hits across auth.rs, config.rs, mail.rs, main.rs |
| 5 | `Get-ChildItem` src/*.rs | 14 source files in src/ |
| 6 | `Get-ChildItem -Recurse` all *.rs | 62 total .rs files; found src/api/core/two_factor/ directory with authenticator.rs, duo.rs, duo_oidc.rs, email.rs, mod.rs, protected_actions.rs, webauthn.rs, yubikey.rs |
| 7 | Read authenticator.rs | 219 lines; core TOTP implementation with generate_authenticator, activate_authenticator, validate_totp_code, validate_totp_code_str, disable_authenticator |
| 8 | Read two_factor/mod.rs | 302 lines; module aggregator, routes, TwoFactorType enum usage, enforce_2fa_policy |
| 9 | `Select-String` api/web.rs for totp/otp | 3 hits (config flags, not TOTP logic) |
| 10 | `Select-String` api/core/accounts.rs for totp/otp | 10 hits (PasswordOrOtpData usage in various endpoints) |
| 11 | `Select-String` auth.rs for totp/otp/2fa | 5 hits (2FA remember JWT claims) |
| 12 | `grep` PasswordOrOtpData across src | 53 matches across api/mod.rs, accounts.rs, ciphers.rs, organizations.rs, all 2FA provider modules |
| 13 | Read api/mod.rs lines 45-77 | PasswordOrOtpData struct and validate() method; delegates OTP to validate_protected_action_otp |
| 14 | Read protected_actions.rs | 158 lines; email OTP validation (not TOTP), used during login flow |
| 15 | `Select-String` Cargo.toml for totp | totp-lite = "2.0.1" at line 148 |
