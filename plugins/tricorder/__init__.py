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
import shutil
import subprocess
import sys
import fnmatch
import functools as ft
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Where the plugin keeps its on-disk cache (maps it produces).
# Same layout as Hermes' own HERMES_HOME/ state dirs.
from hermes_constants import get_hermes_home

@ft.lru_cache(maxsize=1)
def _cache_dir() -> Path:
    """On-disk cache dir (maps the plugin produces). Lazily created on first
    use so importing the plugin has no side effects. Same layout as Hermes'
    HERMES_HOME/state dirs."""
    d = get_hermes_home() / "tricorder"
    d.mkdir(parents=True, exist_ok=True)
    return d

# Path to the tricorder CLI in its own venv. Lazy-initialized on first use.
_TRICORDER_CLI: Optional[str] = None


def _find_tricorder_cli() -> Optional[str]:
    """Discover tricorder CLI executable using multiple strategies.

    Priority order:
    1. PATH lookup (works if installed globally or venv activated)
    2. Hermes config override (plugins.entries.tricorder.cli_path)
    3. Relative to this plugin file (.venv, venv, env)
    4. Relative to tricorder package (editable install)
    5. Relative to sys.executable (if running in tricorder's venv)
    """
    # 1. PATH lookup (works if installed globally or venv activated)
    cli = shutil.which("tricorder")
    if cli:
        return cli

    # 2. Hermes config override
    try:
        cli_path = _config_entry().get("cli_path")
        if cli_path and Path(cli_path).exists():
            return cli_path
    except Exception:
        pass

    # 3. Relative to this plugin file
    plugin_dir = Path(__file__).resolve().parent
    for venv_name in (".venv", "venv", "env"):
        venv_path = plugin_dir / venv_name
        if sys.platform == "win32":
            candidates = [venv_path / "Scripts" / "tricorder.exe"]
        else:
            candidates = [venv_path / "bin" / "tricorder"]
        for c in candidates:
            if c.exists():
                return str(c)

    # 4. Relative to tricorder package (editable install)
    try:
        import tricorder
        pkg_dir = Path(tricorder.__file__).resolve().parent
        for venv_name in (".venv", "venv", "env"):
            venv_path = pkg_dir / venv_name
            if sys.platform == "win32":
                candidates = [venv_path / "Scripts" / "tricorder.exe"]
            else:
                candidates = [venv_path / "bin" / "tricorder"]
            for c in candidates:
                if c.exists():
                    return str(c)
    except Exception:
        pass

    # 5. Relative to sys.executable (if running in tricorder's venv)
    try:
        exe_dir = Path(sys.executable).resolve().parent
        if sys.platform == "win32":
            candidate = exe_dir / "tricorder.exe"
        else:
            candidate = exe_dir / "tricorder"
        if candidate.exists():
            return str(candidate)
    except Exception:
        pass

    return None


def _get_tricorder_cli() -> Optional[str]:
    """Get tricorder CLI path, initializing on first call."""
    global _TRICORDER_CLI
    if _TRICORDER_CLI is None:
        _TRICORDER_CLI = _find_tricorder_cli()
    return _TRICORDER_CLI


# ---------------------------------------------------------------------------
# Config access — "control, not assume": the active project is declared, never
# sniffed from cwd/messages.
# ---------------------------------------------------------------------------

# Lean default token budget for the tier-0 navigation scaffold. The map goes to
# file (not context) and the reference/depth path lives in the MCP tools, so
# the scaffold only needs the top definitions, not the whole repo. Bump via
# config if a project genuinely needs a fat scaffold (ponytail: constant, not
# config knob — raise when a real project overflows 2048).
_MAP_TOKENS = 2048  # default; overridable via config plugins.entries.tricorder.map_tokens
_MAX_FILES = 1000   # default; overridable via config plugins.entries.tricorder.max_files


def _map_tokens() -> int:
    """Map token budget, overridable via config. Kept as a function so the
    plugin can be reconfigured at runtime without an import-time read."""
    val = _config_entry().get("map_tokens")
    if isinstance(val, int) and val > 0:
        return val
    return _MAP_TOKENS


def _max_files() -> int:
    """Max files to parse, overridable via config."""
    val = _config_entry().get("max_files")
    if isinstance(val, int) and val > 0:
        return val
    return _MAX_FILES


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


def _config_entry() -> dict:
    """The tricorder entry from Hermes config (plugins.entries.tricorder), or {}."""
    try:
        from hermes_cli.config import load_config
        cfg = load_config() or {}
        return ((cfg.get("plugins") or {}).get("entries") or {}).get("tricorder") or {}
    except Exception:
        return {}


def _exclude_globs() -> list:
    """Return the configured exclude_globs list (vendor/third-party patterns), or []."""
    try:
        entry = _config_entry()
        val = entry.get("exclude_globs")
        if isinstance(val, list):
            return [str(g) for g in val if g]
        if isinstance(val, str) and val.strip():
            # config set may store a JSON list as a string; recover it.
            import json as _j
            try:
                parsed = _j.loads(val)
                if isinstance(parsed, list):
                    return [str(g) for g in parsed if g]
            except (ValueError, TypeError):
                pass
    except Exception as exc:  # pragma: no cover
        logger.debug("tricorder: could not read exclude_globs: %s", exc)
    return []


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
    return _cache_dir() / f"{digest}.map"


def _meta_file(project_root: str) -> Path:
    return _cache_file(project_root).with_suffix(".json")


def _read_meta(project_root: str) -> dict:
    """Read cached meta JSON, return {} if missing/corrupt."""
    m = _meta_file(project_root)
    try:
        return json.loads(m.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _project_signature(project_root: str) -> str:
    """Shell to CLI for the stat-hash. Returns 16 hex chars or '' on failure."""
    cli = _get_tricorder_cli()
    if not cli:
        return ""
    cmd = [cli, "--root", project_root, "--signature-only", "."]
    globs = _exclude_globs()
    if globs:
        cmd += ["--exclude-globs"] + globs
    try:
        r = subprocess.run(cmd, capture_output=True, text=True,
                           timeout=30, check=False)
        return r.stdout.strip()[:16]
    except Exception:
        return ""


def _cli_budget(project_root: str, map_file) -> dict:
    """Budget fields {token_estimate, full_repo_estimate, savings_pct} for a
    cached map, shelled from the CLI (--stats-only). The plugin runs in Hermes'
    Python without tricorder deps (tiktoken), so it delegates the estimate to
    the CLI's own venv. Returns {} on any failure — callers fall back."""
    cli = _get_tricorder_cli()
    if not cli:
        return {}
    cmd = [cli, "--root", project_root, "--stats-only", str(map_file)]
    globs = _exclude_globs()
    if globs:
        cmd += ["--exclude-globs"] + globs
    try:
        r = subprocess.run(cmd, capture_output=True, text=True,
                           timeout=60, check=False)
        if r.returncode != 0:
            return {}
        parsed = json.loads(r.stdout.strip())
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass
    return {}


def _is_cache_valid(project_root: str) -> bool:
    """Cache is valid if meta exists and stored signature matches current."""
    meta = _read_meta(project_root)
    cached_sig = meta.get("project_sig")
    if not cached_sig:
        return False  # no signature → rebuild
    return cached_sig == _project_signature(project_root)


def _cache_age_str(project_root: str) -> str:
    """Human-readable age of cached map: '2m', '1h', '3d', or 'unknown'."""
    m = _meta_file(project_root)
    if not m.exists():
        return "unknown"
    import time as _t
    secs = int(_t.time() - m.stat().st_mtime)
    if secs < 60:
        return f"{secs}s"
    if secs < 3600:
        return f"{secs // 60}m"
    if secs < 86400:
        return f"{secs // 3600}h"
    return f"{secs // 86400}d"


def _list_cached_projects() -> list:
    """List all cached projects (path, age_str, lines) excluding active."""
    root = _active_project()
    result = []
    for meta_file in _cache_dir().glob("*.json"):
        try:
            info = json.loads(meta_file.read_text(encoding="utf-8"))
            proj = info.get("project_root", "")
            if proj and proj != root:
                import time as _t
                secs = int(_t.time() - meta_file.stat().st_mtime)
                age = (f"{secs}s" if secs < 60 else
                       f"{secs // 60}m" if secs < 3600 else
                       f"{secs // 3600}h" if secs < 86400 else
                       f"{secs // 86400}d")
                result.append((proj, age, info.get("lines", 0)))
        except Exception:
            continue
    return result


# ---------------------------------------------------------------------------
# Core: produce the map
# ---------------------------------------------------------------------------

def build_map(project_root: str) -> Optional[dict]:
    """Run tricorder scan for project_root into the cache. Returns meta dict
    (map_file, token_estimate, symbol counts) or None on failure. Best-effort,
    never raises."""
    # Always rebuild on explicit scan - cache is for auto lifecycle only
    cli = _get_tricorder_cli()
    if not cli:
        logger.debug("tricorder: CLI not found; skipping map")
        return None
    out = _cache_file(project_root)
    cmd = [
        cli, "--root", project_root,
        "--tier", "0",
        "--map-tokens", str(_map_tokens()),
        "--exclude-untagged",
        "--output", str(out),
        ".",
    ]
    globs = _exclude_globs()
    if globs:
        cmd += ["--exclude-globs"] + globs
    max_files = _max_files()
    if max_files:
        cmd += ["--max-files", str(max_files)]
    try:
        # The CLI needs at least one paths positional; resolve against --root.
        subprocess.run(
            cmd,
            capture_output=True, text=True, timeout=300,
            check=False,
        )
    except Exception as exc:
        logger.debug("tricorder: scan failed for %s: %s", project_root, exc)
        return None

    if not out.exists() or out.stat().st_size == 0:
        logger.debug("tricorder: empty map for %s", project_root)
        return None

    # Best-effort stats for the digest.
    map_text = out.read_text(encoding="utf-8", errors="replace")
    n_lines = map_text.count("\n")
    # Count unique files surfaced in the map (lines ending with " (N lines)" pattern)
    map_files = len(set(
        line.split(" (")[0] for line in map_text.splitlines()
        if " (" in line and line.endswith(" lines)")
    ))
    budget = _cli_budget(project_root, out)
    meta = {
        "project_root": project_root,
        "map_file": str(out),
        "lines": n_lines,
        "tokens_approx": budget.get("token_estimate", int(n_lines * 14)),
        "full_repo_estimate": budget.get("full_repo_estimate", 0),
        "savings_pct": budget.get("savings_pct", 0.0),
        "project_sig": _project_signature(project_root),
        "map_files": map_files,
    }
    _meta_file(project_root).write_text(
        json.dumps(meta), encoding="utf-8"
    )
    return meta


# ---------------------------------------------------------------------------
# Hooks
# ---------------------------------------------------------------------------

def _probe_digest_cli(root: str) -> str:
    """Emit the unified turn-0 probe digest via the tricorder CLI.

    The CLI (--probe-digest) is the single source of truth shared with DSH, so
    Hermes and DSH inject byte-identical turn-0 content. Cheap os.walk tally —
    no map build, no token budget; safe on huge repos. Returns '' when the repo
    is empty/tiny/non-code or the CLI is unavailable.
    """
    cli = _get_tricorder_cli()
    if not cli:
        return ""
    try:
        r = subprocess.run(
            [cli, "--root", root, "--probe-digest"],
            capture_output=True, text=True, timeout=30,
            check=False,
        )
    except Exception as exc:
        logger.debug("tricorder: probe-digest failed for %s: %s", root, exc)
        return ""
    return r.stdout.strip()


def _on_session_start(session_id: str = "", **_: Any) -> None:
    """Turn 0 is a cheap navigation probe only. Never build the full map at
    session start — on a kernel-scale repo that would block/timeout. Maps are
    built on demand via /tricorder scan or the MCP tools."""
    root = _active_project()
    if not root:
        return
    logger.debug("tricorder: turn-0 probe-only (no map build) for %s", root)


def _on_pre_llm_call(
    session_id: str = "",
    is_first_turn: bool = False,
    user_message: str = "",
    **_: Any,
) -> Optional[str]:
    """Return the unified turn-0 probe digest to inject into the user message.

    Same text the CLI --probe-digest emits and DSH injects. Navigation-only:
    cheap os.walk tally + pointer to MCP tools for depth. First turn only;
    later turns stay silent. Never triggers a full map build on turn 0.
    """
    root = _active_project()
    if not root:
        return None
    if not is_first_turn:
        # Only the first turn carries the digest; later turns stay quiet.
        return None
    digest = _probe_digest_cli(root)
    if not digest:
        return None
    return f"[tricorder] {root} — {digest}"


# ---------------------------------------------------------------------------
# Slash commands
# ---------------------------------------------------------------------------

_HELP = """\
/tricorder — codebase intelligence (map lifecycle + active project)

  /tricorder root <path>     Set active project (persisted to config)
  /tricorder scan [path]     Generate a repo map (default: active project)
  /tricorder status          Show active project + cache state + all cached projects
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
        if _is_cache_valid(str(p)):
            meta = _read_meta(str(p))
            age = _cache_age_str(str(p))
            return (
                f"Active project set to {p}.\n"
                f"  Cache: valid ({meta.get('lines', '?')} lines, "
                f"~{meta.get('tokens_approx', '?')} tokens, {age} old)."
            )
        # Stale or missing — auto-rebuild
        meta = build_map(str(p))
        if meta:
            return (
                f"Active project set to {p}.\n"
                f"  Map rebuilt ({meta['lines']} lines, "
                f"~{meta['tokens_approx']} tokens)."
            )
        return f"Active project set to {p}.\n  Scan failed — run /tricorder scan."

    if cmd == "scan":
        if len(argv) > 1 and not argv[1].startswith("-"):
            target = str(Path(argv[1]).resolve())
        elif root:
            target = root
        else:
            return "No active project. Use /tricorder root <path> first, or pass a path."
        # Force fresh map by deleting cache
        for p in [_cache_file(target), _meta_file(target)]:
            try: p.unlink()
            except: pass
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
            cache = _cache_file(root)
            if cache.exists():
                meta = _read_meta(root)
                age = _cache_age_str(root)
                valid = _is_cache_valid(root)
                state = "valid" if valid else "stale (files changed)"
                lines.append(
                    f"  cache: {state} ({meta.get('lines', '?')} lines, "
                    f"~{meta.get('tokens_approx', '?')} tokens, "
                    f"{meta.get('map_files', '?')} files, {age} old)"
                )
                if meta.get("full_repo_estimate"):
                    savings = meta.get("savings_pct", 0.0)
                    repo_tok = meta.get("full_repo_estimate")
                    lines.append(
                        f"  budget: map ~{meta.get('tokens_approx', '?')} tokens "
                        f"vs ~{repo_tok} full-repo (~{savings}% saved)"
                    )
            else:
                lines.append("  cache: (not built)")
            # Live code-file tally via the shared CLI probe-digest
            digest = _probe_digest_cli(root)
            if digest:
                lines.append(f"  probe: {digest}")
        others = _list_cached_projects()
        if others:
            lines.append(f"  other cached maps ({len(others)}):")
            for proj_path, age, n_lines in others:
                lines.append(f"    {proj_path} — {n_lines} lines, {age} old")
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
        description="Codebase intelligence: map lifecycle + active project.",
        args_hint="<root|scan|status>",
    )

    # NOTE: the tricorder skill is already installed globally at
    # ~/.hermes/skills/ (independent of this plugin), so no register_skill here.


if __name__ == "__main__":  # pragma: no cover — manual smoke test
    import sys
    demo_root = sys.argv[1] if len(sys.argv) > 1 else "."
    meta = build_map(demo_root)
    print(json.dumps(meta, indent=2) if meta else "no map")