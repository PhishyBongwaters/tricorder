"""Round-17 fresh-eyes review tests (red-first)."""
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import Tricorder
import tricorder_server as srv


def _snapshot_warning():
    """Helper: read the current global scan-report warning (test seam)."""
    return srv._last_scan_report.get("warning")


def test_attach_scan_warning_prefers_snapshot():
    """Concurrent scans must not cross-attach each other's warnings.

    _last_scan_report is a process-global dict: scan A discovers (warning
    W_A), yields at an await, scan B discovers (overwrites with W_B), scan
    A resumes and builds its response. Reading the global at response
    time attaches W_B to A's response. tricorder_scan therefore snapshots
    the warning synchronously right after find_src_files and passes it
    through; _attach_scan_warning must prefer that snapshot.
    """
    srv._last_scan_report.clear()
    try:
        srv._last_scan_report["warning"] = "stale: another root's scan"
        resp = srv._attach_scan_warning({}, warning="fresh: my own scan")
        assert resp.get("scan_warning") == "fresh: my own scan", (
            f"snapshot ignored, got global instead: {resp!r}"
        )
        # Backward compat: no snapshot -> global still works.
        resp2 = srv._attach_scan_warning({})
        assert resp2.get("scan_warning") == "stale: another root's scan"
    finally:
        srv._last_scan_report.clear()


def _tc(root):
    return Tricorder(root=str(root), verbose=False)


def test_mermaid_node_ids_are_unique(tmp_path):
    """Two files whose sanitized mermaid IDs collide must not merge nodes.

    to_mermaid built node IDs as path.replace(".","_").replace("/","_"),
    so 'a.b/c.py' and 'a/b.c.py' both became 'a_b_c_py': one node
    definition overwrote the other and edges collapsed onto one node.
    """
    d1 = tmp_path / "a.b"
    d1.mkdir()
    f1 = d1 / "c.py"
    f1.write_text("def f1():\n    return 1\n", encoding="utf-8")
    d2 = tmp_path / "a"
    d2.mkdir()
    f2 = d2 / "b.c.py"
    f2.write_text("def f2():\n    return 2\n", encoding="utf-8")

    tc = _tc(tmp_path)
    out = tc.to_mermaid(
        chat_fnames=[str(f1)], other_fnames=[str(f1), str(f2)],
    )
    # Normalize separators: Windows renders rel paths with backslashes.
    out = out.replace("\\", "/")
    # Both files must appear as labeled nodes.
    assert "a.b/c.py" in out, "first file missing from mermaid output"
    assert "a/b.c.py" in out, "second file missing from mermaid output"
    node_lines = [ln for ln in out.splitlines() if ln.strip().endswith("]") or ":::" in ln]
    ids = [ln.strip().split("[", 1)[0].strip().split(" ", 1)[0] for ln in node_lines]
    assert len(ids) == len(set(ids)), f"duplicate mermaid node ids: {ids}"


@pytest.mark.skipif(os.name == "nt",
                     reason="double-quote filenames are illegal on Windows")
def test_mermaid_label_escapes_quotes(tmp_path):
    """A double-quote in a filename must not break out of the mermaid label."""
    evil = tmp_path / 'we"].ir.py'
    evil.write_text("def evil():\n    return 1\n", encoding="utf-8")

    tc = _tc(tmp_path)
    out = tc.to_mermaid(chat_fnames=[str(evil)], other_fnames=[str(evil)])
    # The label must not contain a raw '"]' sequence that closes the label.
    for ln in out.splitlines():
        s = ln.strip()
        if s.startswith("graph") or "-->" in s or not s:
            continue
        if '["' in s:
            body = s.split('["', 1)[1].rsplit('"]', 1)[0]
            assert '"' not in body, (
                f"unescaped quote breaks mermaid label: {ln!r}"
            )
