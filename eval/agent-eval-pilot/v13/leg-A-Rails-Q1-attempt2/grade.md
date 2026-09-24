# Leg A-Rails-Q1 attempt 2 — GRADE (Qwen model)

## Verdict: PASS — **compliant (v1.6 tool feature used correctly)**

Correct answer: `has_many` at `associations.rb:1426` → `Builder::HasMany.build()` 
→ `Association.build()` creates `HasManyReflection`, registers via
`Reflection.add_reflection()`. Builder defines readers/writers for
`#{name}`, `#{name}=`, `#{name}_ids`, `#{name}_ids=`, plus callbacks.
Runtime: `CollectionAssociation#reader()` returns `CollectionProxy` which
delegates `create`/`build`/`<<`/`delete`/`find`/`where`/`size`/`empty?`/etc.
`HasManyAssociation` handles `:dependent` strategies, counter cache, delete.
`HasManyReflection` returns `HasManyAssociation` or
`HasManyThroughAssociation`. All citations exact.

## Tokens

| Step | Tokens | Note |
|---|---|---|
| --smart-map | 681 | probe + detect + MAP-skip in one call |
| detects 7 × (5) | 3,541 | capped at 5, mixed exact/fuzzy |
| symbols 1 × | 1,428 | range confirm |
| reads 12 × | 13,602 | targeted bodies |
| **Total** | **19,165** | MAP skipped via --smart-map |

## Compliance

- v1.6 obeyed perfectly: `--smart-map "has_many"` ran probe + one exact
  detect → exact hit → MAP skipped. All first passes capped at 5 (amended
  v1.3). Reads targeted, no chained windows. Ladder: smart-map → reads →
  answer.
- Minor: 2 detects returned fuzzy test-class noise (steps 4–5); agent
  pivoted to grep instead of reading — correct v1.2 discipline.
- Smart-map worked as designed: Rails (4,470 files < 5000 threshold) got
  probe + exact detect → exact hit → MAP skipped.

## Tokens vs prior attempts

| | Att.1 (Nemotron, v1–v1.3, map-first) | Att.2 (Qwen, v1–v1.6 + smart-map) |
|---|---|---|
| Calls | 7 | 10 CLI + 12 reads |
| Tokens | 8,014 (post-fix replay) | 19,165 |
| MAP | paid | skipped |

**Note:** Higher token count than att.1 because att.2 reads 12 targeted
files (13,602 tok) vs att.1's 4 reads (1,948 tok). att.1 was map-first
and stopped early. Smart-map trades read depth for MAP-skip — correct
tradeoff for complex questions needing multiple file reads.

## Model Tracking

| Leg | Model | Provider |
|---|---|---|
| A-Rails-Q1 att.2 | **Qwen** | **llamacpp** |
| A-Rails-Q1 att.1 | Nemotron | opencode |
| A/B VW-Q1–Q4 | Qwen | llamacpp |
| A/B Elixir-Q1, Vue-Q1 | Qwen | llamacpp |
| All other v1.3 A-legs | Nemotron | opencode |

## Findings

1. **Smart-map absorbed the protocol**: Agent used one flag instead of
   probe+detect+MAP manually. 10 CLI calls vs ~15 manual.
2. **Rails answer is diffuse**: 6 files needed for complete answer
   (associations.rb, has_many.rb, association.rb, collection_association.rb,
   has_many_association.rb, collection_proxy.rb, reflection.rb). Smart-map
   skipped the 2k MAP but agent still needed to read 6 files.
3. **Smart-map threshold works**: 5000-file limit correctly included Rails
   (4,470 files) but excludes Go (12,850).