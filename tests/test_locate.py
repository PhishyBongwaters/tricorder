"""Tests for the tricorder_locate auto-escalation tool."""
import asyncio
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tricorder_server import tricorder_locate
from utils import count_tokens


def _project():
    tmp = Path(tempfile.mkdtemp(prefix="locate_"))
    (tmp / "src").mkdir()
    (tmp / "src" / "auth.py").write_text(
        "def authenticate(user, password):\n    return user == 'admin'\n",
        encoding="utf-8",
    )
    (tmp / "src" / "main.py").write_text(
        "from auth import authenticate\n\ndef run():\n    authenticate('admin', 'x')\n",
        encoding="utf-8",
    )
    (tmp / "src" / "other.py").write_text(
        "from auth import authenticate\n\ndef helper():\n    return authenticate('a', 'b')\n",
        encoding="utf-8",
    )
    (tmp / "src" / "big.py").write_text(
        "def big_function():\n" + "\n".join(
            f"    x{i} = {i} * 2  # filler line to force budget trimming"
            for i in range(200)
        ) + "\n    return 0\n",
        encoding="utf-8",
    )
    return tmp


class TestLocate(unittest.TestCase):
    def setUp(self):
        self.tmp = _project()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def _locate(self, **kw):
        kw.setdefault("project_root", str(self.tmp))
        return asyncio.run(tricorder_locate(**kw))

    def test_best_match_is_definition(self):
        r = self._locate(query="authenticate")
        self.assertNotIn("error", r)
        m = r["match"]
        self.assertIsNotNone(m)
        self.assertEqual(m["name"], "authenticate")
        self.assertTrue(m["file"].replace("\\", "/").endswith("src/auth.py"),
                        f"best match should be the definition, got {m['file']}")
        self.assertIn("body", m)
        self.assertIn("callers", m)

    def test_alternatives_listed_and_capped(self):
        r = self._locate(query="authenticate", max_alternatives=2)
        alts = r["alternatives"]
        self.assertLessEqual(len(alts), 2)
        self.assertTrue(alts)
        for a in alts:
            for k in ("name", "file", "line", "kind", "quality"):
                self.assertIn(k, a)
        # Best match itself is not among the alternatives.
        m = r["match"]
        m_abs = Path(m["file"]).as_posix()
        for a in alts:
            is_best = (a["name"] == m["name"] and a["line"] == m["line"]
                       and m_abs.endswith(a["file"].replace("\\", "/")))
            self.assertFalse(is_best, f"best match leaked into alternatives: {a}")

    def test_no_match(self):
        r = self._locate(query="zz_no_such_symbol_zz")
        self.assertIsNone(r["match"])
        self.assertEqual(r["alternatives"], [])
        self.assertIn("note", r)

    def test_max_tokens_budget(self):
        r = self._locate(query="big_function", max_tokens=300)
        self.assertNotIn("error", r)
        self.assertIsNotNone(r["match"])
        self.assertTrue(r.get("truncated"))
        self.assertLessEqual(count_tokens(json.dumps(r), "gpt-4"), 300)

    def test_fuzzy_query_still_locates(self):
        r = self._locate(query="authentcate")  # typo -> rescue
        self.assertIsNotNone(r["match"])
        self.assertEqual(r["match"]["name"], "authenticate")

    def test_invalid_root(self):
        r = self._locate(project_root="/nonexistent/path", query="x")
        self.assertIn("error", r)


if __name__ == "__main__":
    unittest.main()
