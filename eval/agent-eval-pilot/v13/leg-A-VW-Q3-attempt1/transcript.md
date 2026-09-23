# Leg A-VW-Q3 attempt 1 — TRANSCRIPT (Qwen model)

Model: `llamacpp/Qwen` (local llama.cpp). 6/15 calls used.
Prompt: `v13/leg-A-VW-Q3-attempt1/prompt.md` (strict ladder).

## Answer (as returned)

Collection access permissions checked in **`src/db/models/collection.rs:155`**:

- **`Collection::can_access_collection`** (lines 155–162): central gate — checks confirmed membership → full org access → direct user assignment (`CollectionUser::has_access_to_collection_by_user` at `collection.rs:901`) → group-based access (`GroupUser::has_access_to_collection_by_member` at `group.rs:571`, `GroupUser::has_full_access_by_member` at `group.rs:596`).

Supporting functions:
| Symbol | File | Line | Purpose |
|---|---|---|---|
| `CollectionUser::has_access_to_collection_by_user` | `collection.rs` | 901 | Direct user-to-collection assignment |
| `GroupUser::has_access_to_collection_by_member` | `group.rs` | 571 | Group → collection access via SQL join |
| `GroupUser::has_full_access_by_member` | `group.rs` | 596 | Group has full org access |

## Commands (in order)

| # | Step | Tokens | Hits | Useful? |
|---|---|---|---|---|
| 1 | MAP 2048 | 2,040 | 30 (jQuery) | ❌ noise |
| 2 | symbols "organization_collection_access" | 1,681 | 10 | ✅ found key symbols |
| 3 | symbols "can_access_collection" | 307 | 2 | ✅ confirmed primary |
| 4 | read collection.rs 150–168 | 235 | — | ✅ core function |
| 5 | read collection.rs 896–904 | 89 | — | ✅ supporting function |
| 6 | read group.rs 566–594 | 286 | — | ✅ group access |

**Total: 6 calls, 4,638 tokens**

## Compliance

- MAP rung 1: noise, correctly continued
- Exact-first: both symbol guesses hit directly
- Ladder: MAP → SYMBOLS → SYMBOLS → READ → READ → READ
- **Stopped at first rung that answered**: READ found the answer; agent didn't escalate further
- Zero NL; zero junk; citation discipline clean