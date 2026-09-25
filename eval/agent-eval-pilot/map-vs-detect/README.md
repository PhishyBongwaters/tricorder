# MAP-first vs detect-first on Go-G5 (ad-hoc experiment, NOT a round)

Ordered 2026-09-25 to test v1.8's only behavioral change (5000+ repos
skip rung-1 MAP) before any new round folder exists. Same question, same
model, same cap — isolates rung-1 order and nothing else.

- Question: Go-G5 (SSA build entry; GT in `../QUESTIONS.md`).
- Model: `llamacpp/Qwen` both arms. Cap 20. Repo + warm canonical DB
  as stated in each prompt.
- Arm M (v1.7 behavior): mandatory plain-MAP rung 1
  (`--map-tokens 2048`), then the ladder as written.
- Arm D (v1.8 behavior): skip rung-1 MAP, open at rung 2 (detect);
  MAP allowed only as fallback rung 5.5.
- Metering: harness session rows (`opencode.db`), input+output primary,
  cache alongside. Agents save nothing (no step files, no transcript) —
  audit from the session log.
- Operator records subagent session IDs here at launch; numbers after
  both arms complete. No verdict from the operator — findings to user.
- EXCLUDED: `ses_f26e92b71ffe1FfKZzCRde7K1d` (first arm-M launch,
  aborted; prompt lacked mandatory `--root`, agent burned 11 calls on
  wrong-repo defaults before abort — contaminated, never counted).
