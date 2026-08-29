# A/B Benchmark Results — projectM (2026-08-29)

## Task
"projectM's PCM audio pipeline feeds multiple renderer backends. Without opening
every file, explain how PCM::AddToBuffer's overloads are dispatched to those
backends and trace the path where loudness-band computation intersects with the
active renderer — naming the dispatch entry and the per-frame callback the
renderers pull from."

## Variants
- **Variant A** — Tricorder MCP enabled (codebase-tricorder skill + bench-tricorder profile)
- **Variant B** — Baseline tools only (bench-baseline profile, no tricorder)
- Model: `hy3-free` / `opencode-free` on both legs
- Judge: same model (hy3-free) via `hermes chat --cli --max-turns 3`

## Judgment Results

| Variant | Grade | Rationale (summary) |
|---------|-------|---------------------|
| A (tricorder) | **PASS** | Names PCM::AddToBuffer overloads + Add() dispatch, PCM::GetFrameAudioData pull callback, Loudness→renderer hook |
| B (baseline) | **FAIL** | Named PCM::Add as dispatch (not AddToBuffer overload), didn't tie Loudness→renderer |

### Detailed Rationale

**A-leg PASS:** "Agent names PCM::Add dispatch overloads into AddToBuffer, the
PCM::GetFrameAudioData per-frame pull callback, and the Loudness band hook via
the m_bass/m_middles/m_treble.Update() calls in UpdateFrameAudioData feeding
the renderer, tracing the full dispatch+consumption path rather than a bare
signature grep."

**B-leg FAIL:** "Named PCM::Add as the dispatch entry instead of the required
PCM::AddToBuffer renderer-dispatch overload, and did not explicitly tie the
loudness computation in PCM::UpdateFrameAudioData to feeding the active
renderer, missing core rubric requirements."

## Token & Telemetry Comparison

| Metric | Variant A (tricorder) | Variant B (baseline) | Delta |
|--------|----------------------|----------------------|-------|
| **Billed input tokens** | 26,282 | 19,307 | +6,975 (+36%) |
| **Cache read tokens** | 130,112 | 183,936 | -53,824 (-29%) |
| **Cache write tokens** | 0 | 0 | — |
| **Output tokens** | 5,642 | 2,911 | +2,731 (+94%) |
| **Raw input sent (billed+cache)** | 156,394 | 203,243 | -46,849 (-23%) |
| **Tool calls** | 17 | 13 | +4 |
| **API calls** | 6 | 12 | -6 (-50%) |
| **Duration** | 104s | 125s | -21s (-17%) |
| **Tricorder MCP calls** | 13 | 0 | — |

## Analysis

**Token consumption is LOWER for Variant A** (156,394 vs 203,243 raw input,
-23%) — the user's expectation that baseline grepping would consume less context
was **not borne out**. Variant A's tricorder calls returned focused symbol
graphs (cache hits on repeated lookups), while Variant B's 12 API calls
accumulated more raw context across broader file reads.

**API calls are halved for Variant A** (6 vs 12) — each tricorder call
consolidates multiple file reads into a single structured response, cutting
round-trips.

**Output tokens are nearly double for A** (5,642 vs 2,911) — A produced a
detailed trace while B's answer was terse and missed key identifiers.

**Verdict: VALID A/B** — both legs graded, A used tricorder (13 calls), B used
none. A/PASS, B/FAIL.

## Files
- A report: report_20260829_161821_993a8c-A.md
- B report: report_20260829_162008_aa1904-B.md
- Sessions: bench-tricorder/20260829_161821_993a8c, bench-baseline/20260829_162008_aa1904
