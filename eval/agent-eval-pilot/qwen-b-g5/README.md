# Qwen B-Go-G5 (ad-hoc, NOT a round leg)

Ordered 2026-09-25: Qwen failed Go-G5 three times on the tricorder arm
(v13 att1, r02 leg 3, map-vs-detect loop). Can the same model run the
grep-only baseline cleanly on the identical question? Same question,
same cap (20), same repo as r03 legs 1–2; vehicle is the ONLY variable.

- Prompt: `prompt.md` (committed before launch).
- Metering: harness session row. Agent saves nothing.
- Result: `grade.md` after.
