"""Probe digest: neutral tail + counter parity with discovery.

2026-09-25 findings (Go-G5 loop autopsy + Rails probe review):
1. format_probe_digest ended with plugin copy ("Use the MCP tools ...",
   "/tricorder scan", "Do not deep-scan this turn") — correct only for
   turn-0 plugin injection. In CLI eval legs there are no MCP tools, no
   slash commands, no turns: an agent can only waste calls on it. The
   digest reports scale, nothing else; navigation belongs to the
   ladder/prompt. Byte-identical across surfaces is preserved (one
   function), the content is just neutral.
2. probe_project counted files discover_src_files drops (minified
   `a.min.js`, dotfiles, `.db`) and vice versa — two "code file"
   counts for the v1.8 5000-branch. Probe now applies discovery's file
   rules (shared constants). Residual drift, documented in code:
   gitignore trees / oversize files / TC-002 envelopes (probe is
   uncapped by design) — errs toward detect-first (conservative).
"""
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from utils import (probe_project, format_probe_digest, discover_src_files,
                   CODE_EXTENSIONS)


def _project():
    tmp = Path(tempfile.mkdtemp(prefix="probe_"))
    (tmp / "a.py").write_text("def a():\n    pass\n", encoding="utf-8")
    (tmp / "b.rb").write_text("def b\nend\n", encoding="utf-8")
    (tmp / "c.sql").write_text("SELECT 1;\n", encoding="utf-8")
    sub = tmp / "sub"
    sub.mkdir()
    (sub / "d.py").write_text("x = 1\n", encoding="utf-8")
    # Discovery-dropped files the probe must not count either:
    (tmp / "a.min.js").write_text("var x=1;\n", encoding="utf-8")
    (tmp / ".hidden.py").write_text("y = 2\n", encoding="utf-8")
    (tmp / "data.db").write_text("notadb", encoding="utf-8")
    (tmp / "notes.md").write_text("# hi\n", encoding="utf-8")
    return tmp


class TestProbeDigestNeutral(unittest.TestCase):
    def test_tail_has_no_harness_pointers(self):
        probe = probe_project(str(_project_with_cleanup(self)))
        digest = format_probe_digest(probe, "root")
        self.assertIn("code files", digest)
        for banned in ("mcp", "MCP", "/tricorder", "turn", "deep-scan",
                       "on demand"):
            self.assertNotIn(banned, digest,
                             f"harness-specific copy leaked: {banned}")

    def test_empty_repo_stays_empty(self):
        tmp = Path(tempfile.mkdtemp(prefix="probe_empty_"))
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        probe = probe_project(str(tmp))
        self.assertEqual(probe["total_files"], 0)
        self.assertEqual(format_probe_digest(probe, str(tmp)), "")


class TestProbeMatchesDiscovery(unittest.TestCase):
    def test_probe_counts_discovery_mappable_set(self):
        tmp = _project()
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        probe = probe_project(str(tmp))
        discovered = discover_src_files(str(tmp), use_gitignore=False)
        expected = sum(
            1 for f in discovered
            if Path(f).suffix.lower() in CODE_EXTENSIONS
            and not Path(f).name.startswith(".")
        )
        self.assertEqual(probe["total_files"], expected)
        self.assertEqual(probe["total_files"], 4)  # a,b,c,sub/d only
        self.assertEqual(probe["lang_counts"].get("python"), 2)


def _project_with_cleanup(tc):
    tmp = _project()
    tc.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
    return tmp


if __name__ == "__main__":
    unittest.main()
