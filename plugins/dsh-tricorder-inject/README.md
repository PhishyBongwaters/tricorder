# @deepseek-ai/dsh-tricorder-inject

Turn-0 **probe-digest** injection for DeepSeek Harness (dsh).

## What it does

When a new session is created, this plugin runs the shared tricorder
`--probe-digest` CLI flag and injects a short, cheap **navigation digest**
(language tally + rough line count + pointer to the MCP tools) as a
plugin-sourced `user/message` **before the first turn starts**.

This is a *navigation item*, not a deep dive. On any repo — including
kernel-scale trees with tens of thousands of files — turn 0 runs a fast
`os.walk` tally and **never builds the full repo map**. Building the map at
turn 0 would block/timeout on large repos; maps are produced on demand via
`/tricorder scan` or the MCP tools.

The digest text is owned by the tricorder CLI, so the Hermes plugin
(`plugins/tricorder`) and this DSH plugin inject **byte-identical** turn-0
content from the same code path.

## Installation

```bash
pnpm add @deepseek-ai/dsh-tricorder-inject
```

Requires tricorder CLI with the `--probe-digest` flag:
```bash
pip install -e D:/Projects/tricorder  # or wherever tricorder is cloned
```

## Configuration

Add to your profile's `cordis.patch.yml`:

```yaml
- insert:
    - id: tricorder-inject
      name: '@deepseek-ai/dsh-tricorder-inject'
      config:
        tricorderExe: 'C:/path/to/tricorder.exe'  # Optional: explicit path
        verbose: false              # Debug logging
```

## How it works

1. **Session created** → `session/created` event fires (global listener).
2. **Only if turn 0** (no `turn/start` event yet) and the session has a `cwd`:
   runs `tricorder --root <cwd> --probe-digest`.
3. If the digest is empty (tiny/empty/non-code repo, or CLI unavailable),
   skips silently — injection is best-effort.
4. Otherwise injects `[tricorder] <cwd> — <digest>` into the model surface.

## Behavior notes

- **Never runs a full map scan on turn 0** — that is the point. The old
  behavior (full `--tier 0` map + `--stats-only` token count on every session)
  could block for minutes on large repos; it is gone.
- **Single source of truth**: the digest text lives in the tricorder CLI
  (`--probe-digest`, implemented via `utils.probe_project` /
  `utils.format_probe_digest`). Both Hermes and DSH shell out to it, so the
  two surfaces can't drift.
- Turn 0 is the only injected message; later turns stay quiet (the digest is
  context-economy aware, same policy as the Hermes plugin).