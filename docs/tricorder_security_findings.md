# Tricorder Security Review Findings

Repository: PhishyBongwaters/tricorder (projects/tricorder)

Purpose:
Agent-consumable security findings converted into Gitea issues (#29 through #38).

Review Type:
Security architecture review focused on hostile repository handling, MCP boundaries, parser safety, and AI agent integration.

---

# Executive Summary

No critical remote code execution vulnerabilities were identified.

The primary security risks are architectural and relate to the fact that Tricorder processes arbitrary repositories and feeds derived information into AI agent workflows.

Main risk categories:
- AI context poisoning through repository content
- Filesystem boundary enforcement
- Resource exhaustion from hostile repositories
- Parser abuse
- MCP capability boundaries
- Cache trust boundaries

---

# Issues Posted

## TC-001: Repository Content Can Influence Agent Context (#29)
- **Severity:** Medium (Label: `medium`)
- **Category:** Agent Safety / Prompt Injection
- **Description:** Tricorder extracts repo information (files, symbols, source context) for AI agent consumption. Repository content must be treated as untrusted input. A malicious repository could contain instruction-like comments, misleading documentation, or source snippets with prompt injection attempts.
- **Recommendation:** Add explicit trust labeling around injected repo-derived content (e.g. `BEGIN UNTRUSTED REPOSITORY CONTEXT / END`). Avoid injecting large free-form comments by default; separate metadata from source text.

## TC-002: Missing Global Resource Envelope (#30)
- **Severity:** Medium (Label: `medium`)
- **Category:** DoS / Resource Management
- **Description:** Tricorder scans arbitrary repositories. A hostile repo can contain millions of files, oversized source files, deeply nested directories, or generated code explosions.
- **Recommendation:** Implement global scan limits (`MAX_FILES`, `MAX_TOTAL_BYTES`, `MAX_SINGLE_FILE_BYTES`, `MAX_DIRECTORY_DEPTH`, `MAX_SCAN_TIME`). Return a partial result with a warning instead of failing unpredictably.
- **Note on existing guards:** `MAX_SCAN_FILES` (20k cap) and `MAX_SOURCE_FILE_SIZE` (1MB) partially mitigate this, but byte budgets and time limits remain open.

## TC-003: Cache Isolation (#31)
- **Severity:** Low (Label: `low`)
- **Category:** Data Integrity
- **Description:** Repository-local caching (`.tricorder.tags.cache.v1/`) creates a trust relationship between scanned content and stored metadata. A repository should not control security-sensitive cache state.
- **Recommendation:** Move cache storage outside the repository to `~/.tricorder/cache/<repository_hash>/`, keyed by resolved path, repo hash, tricorder version, and config hash.

## TC-004: Parser Resource Exhaustion (#32)
- **Severity:** Medium (Label: `medium`)
- **Category:** Parser Security
- **Description:** Tricorder relies on tree-sitter parsers to analyze source code. Parsers process arbitrary attacker-controlled input (malformed syntax, giant generated files, deeply nested constructs) in-process via `asyncio.to_thread` with no timeout.
- **Recommendation:** Parse in worker processes, enforce a parser timeout, terminate stuck workers, and return graceful skip warnings.

## TC-005: MCP Responses Should Mark Repository Data As Untrusted (#33)
- **Severity:** Medium (Label: `medium`)
- **Category:** MCP / Agent Safety
- **Description:** MCP tools expose repository-derived information directly to AI agents. The agent needs to understand that this information originates from an external codebase.
- **Recommendation:** Add metadata to MCP responses:
  ```json
  { "source": "scanned_repository", "trust": "untrusted_repository_content" }
  ```

## TC-006: File Path Containment Validation (#34)
- **Severity:** Medium (Label: `medium`)
- **Category:** Filesystem Security
- **Description:** Project root validation exists, but every requested file path should be validated after resolution. A caller providing `../../sensitive_file.txt` may escape the repository.
- **Recommendation:** Require `resolved_file.is_relative_to(resolved_project_root)` for all file parameters.

## TC-007: Caller-Controlled Scan Size (#35)
- **Severity:** Low (Label: `low`)
- **Category:** Resource Management
- **Description:** Tool parameters allow callers to influence scan size (`max_files`). Large values (e.g. `999999999`) bypass safety assumptions.
- **Recommendation:** Clamp values server-side: `max_files = min(requested_max_files, MAX_ALLOWED_FILES)`.

## TC-008: Output File Write Boundary (#36)
- **Severity:** Medium (Label: `medium`)
- **Category:** Filesystem Write Safety
- **Description:** The `output_file` feature creates a filesystem write capability with no containment (`out_path = Path(output_file)`). An unrestricted output path allows unintended writes outside the repository.
- **Recommendation:** Restrict output paths to tricorder-managed storage (`~/.tricorder/output/`), validate containment inside `project_root`, or require explicit opt-in.

## TC-009: Dependency Supply Chain Hardening (#37)
- **Severity:** Low (Label: `low`)
- **Category:** Supply Chain Security
- **Description:** Tricorder depends on parsers, MCP libraries, analysis libraries, and tokenization components. A compromised dependency could affect agent environments.
- **Recommendation:** Pin dependency versions, review updates, run vulnerability scanning, and generate inventory reports.

## TC-010: Parser Dependency Fuzz Testing (#38)
- **Severity:** Low (Label: `low`)
- **Category:** Testing / Parser Security
- **Description:** Parser libraries are effectively compiler components and should be tested against hostile inputs.
- **Recommendation:** Add fixtures under `tests/security/` (malformed C/Python, huge files, unicode identifiers, deeply nested syntax, broken source trees) expecting no crashes and bounded resource usage.

---

## Implementation Priority

- **Priority 1 (Critical Gaps):** TC-006 (path containment), TC-008 (output write boundary), TC-004 (parser timeout), TC-003 (cache isolation).
- **Priority 2 (Hardening):** TC-002 (global resource envelope), TC-001 (context injection), TC-005 (MCP trust labeling), TC-007 (param clamping).
- **Priority 3 (Supply Chain & Testing):** TC-009 (dependency pinning), TC-010 (fuzz testing).
