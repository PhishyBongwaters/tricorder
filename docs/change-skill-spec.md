# Change Skill Spec: tricorder-codebase-understanding

**Target Skill:** `tricorder-codebase-understanding`
**Goal:** Align documentation with actual implementation, focusing on the Tiered Escalation Ladder and conservative context usage.

## 1. Orientation: The Turn 0 Digest
Every session starts with an **Injected Digest** (via Hermes/DSH).
- **Action:** Always consult the Turn 0 digest before calling any `tricorder` tools. It provides immediate context and often negates the need for a full scan.

## 2. The Escalation Ladder (Navigation Depth)
Navigate using the minimum necessary context to prevent token bloat and "blind" file pulls.

| Rung | Mode | Tools | Purpose |
| :--- | :--- | :--- | :--- |
| **Rung 1** | **Topology** | `tricorder_scan` | High-level structure. **Mandatory:** Pull from disk cache if available. |
| **Rung 2** | **Discovery** | `tricorder_symbols`, `tricorder_detect` | Locate specific symbols or identifiers within the topology. |
| **Rung 3** | **Minimal Detail (T0)** | `tricorder_detail` (T0) | View definitions/signatures without implementation bloat. |
| **Rung 4** | **Deep Analysis (T1)** | `tricorder_detail` (T1), `tricorder_query` | Full implementation logic and graph traversal (callers/callees). |

## 3. Anti-Loop & Recovery (Escalation Logic)
If a tool call fails to provide sufficient information, follow this escalation path:

1. **Truncation/Budget Hit:** If a tool returns a `tier_hint` or warning about truncation:
   - **Narrow:** Refine the query or target path to a smaller scope.
   - **Escalate:** Increase the **Tier** (e.g., T0 $\rightarrow$ T1) if the current tier is too sparse.
2. **MCP/Tool Overhead:** If MCP tools are too slow, heavy, or failing:
   - **Fallback:** Use native terminal tools (`rg`, `grep`, `ls`) to perform direct, low-level discovery.

## 4. Tool Registry
| Tool | Purpose |
| :--- | :--- |
| `tricorder_scan` | Map generation/retrieval (Cache-first). |
| `tricorder_detect` | Identifier/Definition search. |
| `tricorder_symbols` | File/Module symbol listing. |
| `tricorder_detail` | Symbol definition at requested **Tier**. |
| `tricorder_query` | Graph traversal/relationships via DSL. |
