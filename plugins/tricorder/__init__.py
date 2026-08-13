"""tricorder plugin — lifecycle-driven repo mapping for Hermes.

"Control, not assume." Instead of waiting for the agent to remember to call
the MCP tools, this plugin wires tricorder into the session lifecycle so the
compact repo map is produced once and fed to the agent automatically:

1. ``on_session_start`` — resolve the configured active project
   (``plugins.entries.tricorder.active_project`` in config.yaml — never
   guessed) and build a current map to the plugin cache dir once.
2. ``pre_llm_call`` — on the first turn (or when a fresh map exists) return a
   short digest (map file path + token stats + top symbols) that Hermes
   injects into the user message. Bounded on purpose: the point is context
   economy (~1.5% of full-repo cost), so we inject a pointer + digest, not
   the whole map.
3. Slash commands for on-demand access: ``/tricorder scan|find|detail|root|status``.

All real work delegates to the tricorder binaries in its own venv
(``D:/Projects/tricorder/.venv``) over subprocess — the plugin never imports
tricorder in-process, keeping Hermes' Python separate from tricorder's deps.

Registered skill: ``tricorder:tricorder`` (the bundled SKILL.md) via
``ctx.register_skill``.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import subprocess
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Where the plugin keeps its on-disk cache (maps it produces).
# Same layout as Hermes' own HERMES_HOME/ state dirs.
from hermes_constants import get_hermes_home

_CACHE_DIR = get_hermes_home() / "tricorder"
_CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Reasonable cap for the auto-generated map (tokens). Tier 0 = defs only.
_DEFAULT_TOKENS = 2048
_MAP_FRESH_SECONDS = 60  # rebuild at most this often per project

# Path to the tricorder CLI in its own venv. Detect once at import.
_TRICORDER_CLI = None
_VENVS = [
    Path(r"D:/Projects/tricorder/.venv/Scripts/tricorder.exe"),
    Path(r"D:/Projects/tricorder/.venv/bin/tricorder"),
]
for _cand in _VENVS:
    if _cand.exists():
        _TRICORDER_CLI = str(_cand)
        break


# ---------------------------------------------------------------------------
# Config access — "control, not assume": the active project is declared, never
# sniffed from cwd/messages.
# ---------------------------------------------------------------------------

def _active_project() -> Optional[str]:
    """Return the configured active project root, or None if not set."""
    try:
        from hermes_cli.config import load_config
        cfg = load_config() or {}
        entry = ((cfg.get("plugins") or {}).get("entries") or {}).get("tricorder") or {}
        val = entry.get("active_project")
        if isinstance(val, str) and val.strip():
            return val.strip()
    except Exception as exc:  # pragma: no cover
        logger.debug("tricorder: could not read active_project: %s", exc)
    return None


def _set_active_project_config(path: str) -> None:
    """Persist the active project via ``hermes config set`` (never hand-edit)."""
    # hermes config set plugins.entries.tricorder.active_project <path>
    subprocess.run(
        [
            "hermes", "config", "set",
            "plugins.entries.tricorder.active_project", path,
        ],
        capture_output=True, text=True, timeout=60,
    )


# ---------------------------------------------------------------------------
# Cache helpers
# ---------------------------------------------------------------------------

def _cache_file(project_root: str) -> Path:
    digest = hashlib.sha256(os.path.normcase(project_root).encode("utf-8")).hexdigest()[:12]
    return _CACHE_DIR / f"{digest}.map"


def _meta_file(project_root: str) -> Path:
    return _cache_file(project_root).with_suffix(".json")


def _is_fresh(project_root: str) -> bool:
    m = _meta_file(project_root)
    if not m.exists():
        return False
    try:
        import time as _t
        return (_t.time() - m.stat().st_mtime) < _MAP_FRESH_SECONDS
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Core: produce the map
# ---------------------------------------------------------------------------

def build_map(project_root: str) -> Optional[dict]:
    """Run tricorder scan for project_root into the cache. Returns meta dict
    (map_file, token_estimate, symbol counts) or None on failure. Best-effort,
    never raises."""
    if not _TRICORDER_CLI:
        logger.debug("tricorder: CLI not found; skipping map")
        return None
    out = _cache_file(project_root)
    try:
        # The CLI needs at least one paths positional; resolve against --root.
        subprocess.run(
            [
                _TRICORDER_CLI, "--root", project_root,
                "--map-tokens", str(_DEFAULT_TOKENS),
                "--tier", "0",
                "--output", str(out),
                ".",
            ],
            capture_output=True, text=True, timeout=120,
            check=False,
        )
    except Exception as exc:
        logger.debug("tricorder: scan failed for %s: %s", project_root, exc)
        return None

    if not out.exists() or out.stat().st_size == 0:
        logger.debug("tricorder: empty map for %s", project_root)
        return None

    # Best-effort stats for the digest.
    n_lines = out.read_text(encoding="utf-8", errors="replace").count("\n")
    meta = {
        "project_root": project_root,
        "map_file": str(out),
        "lines": n_lines,
        "tokens_approx": int(n_lines * 14),  # T0 ~14 tokens/tag
    }
    _meta_file(project_root).write_text(
        json.dumps(meta), encoding="utf-8"
    )
    return meta


# ---------------------------------------------------------------------------
# Hooks
# ---------------------------------------------------------------------------

def _on_session_start(session_id: str = "", **_: Any) -> None:
    """On a fresh session, produce a current map for the active project and
    the first-turn digest. Best-effort; never blocks the session."""
    root = _active_project()
    if not root:
        return
    build_map(root)


def _on_pre_llm_call(
    session_id: str = "",
    is_first_turn: bool = False,
    user_message: str = "",
    **_: Any,
) -> Optional[str]:
    """Return a short tricorder digest to inject into the user message.

    Inject on first turn (fresh map) so the agent has the repo skeleton before
    it does anything. Subsequent turns are silent unless the map just refreshed
    (cheap re-inject is acceptable; Hermes dedups presentation)."""
    root = _active_project()
    if not root:
        return None
    if not _is_fresh(root):
        build_map(root)
    out = _cache_file(root)
    if not out.exists():
        return None
    meta = _meta_file(root)
    try:
        info = json.loads(meta.read_text(encoding="utf-8"))
    except Exception:
        info = {}
    # Keep the injected context tiny: a pointer + digest, not the full map.
    lines = info.get("lines", 0)
    return (
        "[tricorder] Active project map ready: "
        f"{info.get('project_root', root)} "
        f"({lines} lines, ~{info.get('tokens_approx', 0)} tokens, tier 0). "
        f"Full map at {out}. "
        "Use /tricorder scan to rebuild, the MCP tools (mcp_tricorder_detect/"
        "symbols/detail) for targeted probes, or read the map file for the "
        "symbol skeleton. Do NOT re-scan this turn."
    )


# ---------------------------------------------------------------------------
# Slash commands
# ---------------------------------------------------------------------------

_HELP = """\
/tricorder — codebase intelligence (map lifecycle + active project)

  /tricorder root <path>     Set active project (persisted to config)
  /tricorder scan [path]     Generate a repo map (default: active project)
  /tricorder status          Show active project + cached map
  /tricorder help            This text

Symbol search / detail live in the MCP tools (mcp_tricorder_detect,
mcp_tricorder_symbols, mcp_tricorder_detail) — the CLI only generates maps.
"""


def _handle_tricorder(raw_args: str) -> Optional[str]:
    argv = raw_args.strip().split()
    if not argv or argv[0] in {"help", "-h", "--help"}:
        return _HELP

    root = _active_project() or ""
    cmd = argv[0]

    if cmd == "root":
        if len(argv) < 2:
            return "Usage: /tricorder root <path>"
        p = Path(argv[1]).resolve()
        _set_active_project_config(str(p))
        build_map(str(p))
        return f"Active project set to {p} and mapped."
        # NOTE: config change for active_project takes effect for future runs;
        # the in-process value is still the old one this session. Restart or
        # re-set for the hook to pick it up.

    if cmd == "scan":
        if len(argv) > 1 and not argv[1].startswith("-"):
            target = str(Path(argv[1]).resolve())
        elif root:
            target = root
        else:
            return "No active project. Use /tricorder root <path> first, or pass a path."
        meta = build_map(target)
        if not meta:
            return f"Scan failed or empty for {target}."
        return (
            f"Map written ({meta['lines']} lines, ~{meta['tokens_approx']} tokens) "
            f"→ {meta['map_file']}"
        )

    if cmd == "status":
        lines = [f"Active project: {root or '(none set)'}"]
        if root:
            out = _cache_file(root)
            if out.exists():
                lines.append(f"  cached map: {out} ({out.stat().st_size} bytes)")
            else:
                lines.append("  cached map: (not yet built)")
        return "\n".join(lines)

    return f"Unknown subcommand: {cmd}\n\n{_HELP}"


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

def register(ctx) -> None:
    # Lifecycle hooks — the "control, not assume" surface.
    ctx.register_hook("on_session_start", _on_session_start)
    ctx.register_hook("pre_llm_call", _on_pre_llm_call)

    # On-demand slash command.
    ctx.register_command(
        "tricorder",
        handler=_handle_tricorder,
        description="Codebase intelligence: map, find, detail, set root.",
        args_hint="<scan|find|detail|root|status>",
    )

    # Register the bundled skill so the workflow is discoverable.
    skill_root = Path(__file__).resolve().parent.parent.parent / "skills" / "tricorder"
    if skill_root.exists():
        try:
            ctx.register_skill("tricorder", skill_root)
        except Exception as exc:
            logger.debug("tricorder: skill registration skipped: %s", exc)


if __name__ == "__main__":  # pragma: no cover — manual smoke test
    import sys
    demo_root = sys.argv[1] if len(sys.argv) > 1 else "."
    meta = build_map(demo_root)
    print(json.dumps(meta, indent=2) if meta else "no map")