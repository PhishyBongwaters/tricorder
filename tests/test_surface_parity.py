"""Parity tests for CLI, MCP, and plugin scan plumbing."""
import importlib
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path

sys.path.insert(0, '.')

from utils import discover_src_files, repo_budget
from tricorder import find_src_files as cli_find_src_files
from tricorder_server import find_src_files as mcp_find_src_files


class TestSurfaceParity(unittest.TestCase):
    def _fixture(self):
        tmp = tempfile.mkdtemp()
        rels = {
            'src/main.cpp': 'int main() {}\n',
            'src/util.hpp': 'class Util {};\n',
            'vendor/glm/vec.hpp': 'class Vec {};\n',
            'README.md': '# hi\n',
        }
        for rel, content in rels.items():
            p = os.path.join(tmp, rel)
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, 'w', encoding='utf-8') as f:
                f.write(content)
        return tmp

    def test_cli_and_mcp_share_discovery(self):
        tmp = self._fixture()
        expected = discover_src_files(tmp, use_gitignore=True, exclude_globs=['vendor/**'])
        self.assertEqual(expected, cli_find_src_files(tmp, exclude_globs=['vendor/**']))
        self.assertEqual(expected, mcp_find_src_files(tmp, exclude_globs=['vendor/**']))

    def test_plugin_reads_same_exclude_globs(self):
        fake_cfg = {
            'plugins': {
                'entries': {
                    'tricorder': {
                        'exclude_globs': ['vendor/**', 'third_party/**'],
                    }
                }
            }
        }
        fake_mod = types.SimpleNamespace(load_config=lambda: fake_cfg)
        fake_home = types.SimpleNamespace(get_hermes_home=lambda: Path(tempfile.mkdtemp()))
        old_cfg = sys.modules.get('hermes_cli.config')
        old_home = sys.modules.get('hermes_constants')
        sys.modules['hermes_cli.config'] = fake_mod
        sys.modules['hermes_constants'] = fake_home
        try:
            plugin = importlib.import_module('plugins.tricorder')
            self.assertEqual(plugin._exclude_globs(), ['vendor/**', 'third_party/**'])
        finally:
            if old_cfg is None:
                sys.modules.pop('hermes_cli.config', None)
            else:
                sys.modules['hermes_cli.config'] = old_cfg
            if old_home is None:
                sys.modules.pop('hermes_constants', None)
            else:
                sys.modules['hermes_constants'] = old_home

    def _plugin_module(self):
        """Import plugins.tricorder with config/mocks isolated, return (module, teardown)."""
        fake_cfg = {'plugins': {'entries': {'tricorder': {}}}}
        fake_mod = types.SimpleNamespace(load_config=lambda: fake_cfg)
        fake_home = types.SimpleNamespace(get_hermes_home=lambda: Path(tempfile.mkdtemp()))
        old_cfg = sys.modules.get('hermes_cli.config')
        old_home = sys.modules.get('hermes_constants')
        sys.modules['hermes_cli.config'] = fake_mod
        sys.modules['hermes_constants'] = fake_home
        plugin = importlib.import_module('plugins.tricorder')

        def teardown():
            if old_cfg is None:
                sys.modules.pop('hermes_cli.config', None)
            else:
                sys.modules['hermes_cli.config'] = old_cfg
            if old_home is None:
                sys.modules.pop('hermes_constants', None)
            else:
                sys.modules['hermes_constants'] = old_home
        return plugin, teardown

    def test_plugin_build_map_passes_lean_token_budget(self):
        """The tier-0 scaffold must go to file with the lean token budget, not the
        CLI's 8192 default — the reference/depth path lives in MCP tools, so the
        map is a navigation scaffold, not a full-repo dump."""
        import unittest.mock as um
        plugin, teardown = self._plugin_module()
        try:
            captured = {}
            out = Path(tempfile.mkdtemp()) / "x.map"

            def fake_run(cmd, *a, **k):
                if "--init" in cmd:
                    # _canonical_db_path round-trip: hand back a cache DB path.
                    return types.SimpleNamespace(returncode=0, stdout="/tmp/x.db\n",
                                                 stderr="")
                captured['cmd'] = cmd
                return types.SimpleNamespace(returncode=0, stdout="", stderr="")
            plugin._TRICORDER_CLI = "tricorder"
            plugin._cache_file = lambda root: out

            with um.patch.object(plugin.subprocess, 'run', side_effect=fake_run):
                plugin.build_map("/fake/project")

            cmd = captured['cmd']
            self.assertIn('--tier', cmd)
            self.assertEqual(cmd[cmd.index('--tier') + 1], '0')
            self.assertIn('--map-tokens', cmd)
            self.assertEqual(cmd[cmd.index('--map-tokens') + 1], '2048')
            self.assertIn('--output', cmd)
        finally:
            teardown()


class TestPluginDbCollisionGuard(unittest.TestCase):
    """Same folder name, different repos: the turn-0 plugin's shared-cache
    DB lookup must not serve repo A's index for repo B."""

    def _plugin(self):
        fake_cfg = {'plugins': {'entries': {'tricorder': {}}}}
        fake_mod = types.SimpleNamespace(load_config=lambda: fake_cfg)
        fake_home = types.SimpleNamespace(get_hermes_home=lambda: Path(tempfile.mkdtemp()))
        old_cfg = sys.modules.get('hermes_cli.config')
        old_home = sys.modules.get('hermes_constants')
        sys.modules['hermes_cli.config'] = fake_mod
        sys.modules['hermes_constants'] = fake_home
        plugin = importlib.import_module('plugins.tricorder')
        self.addCleanup(self._restore, old_cfg, old_home)
        return plugin

    @staticmethod
    def _restore(old_cfg, old_home):
        if old_cfg is None:
            sys.modules.pop('hermes_cli.config', None)
        else:
            sys.modules['hermes_cli.config'] = old_cfg
        if old_home is None:
            sys.modules.pop('hermes_constants', None)
        else:
            sys.modules['hermes_constants'] = old_home

    def test_plugin_db_for_rejects_collision(self):
        from database import DBStore
        tmp = Path(tempfile.mkdtemp(prefix="plugdb_"))
        self.addCleanup(lambda: __import__("shutil").rmtree(tmp, ignore_errors=True))
        repo_a = (tmp / "a" / "proj").resolve()
        repo_b = (tmp / "b" / "proj").resolve()
        repo_a.mkdir(parents=True)
        repo_b.mkdir(parents=True)
        cache = Path(tempfile.mkdtemp(prefix="plugcache_"))
        self.addCleanup(lambda: __import__("shutil").rmtree(cache, ignore_errors=True))
        db_path = cache / "db" / "proj.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        db = DBStore(str(db_path))
        db.set_meta(str(repo_a), "sig")
        db.set_file_state("a.py", 100, 1234567890)
        db.insert_tags([("a.py", "a.py", 1, "alpha", "def")])
        db.conn.commit()
        db.conn.close()
        old_env = os.environ.get("TRICORDER_CACHE_HOME")
        os.environ["TRICORDER_CACHE_HOME"] = str(cache)
        self.addCleanup(lambda: (os.environ.pop("TRICORDER_CACHE_HOME", None)
                                 if old_env is None
                                 else os.environ.update({"TRICORDER_CACHE_HOME": old_env})))
        plugin = self._plugin()
        # repo B must not be told it is mapped from repo A's DB ...
        self.assertIsNone(plugin._tricorder_db_for(str(repo_b)))
        # ... while repo A still resolves to its own DB.
        self.assertEqual(plugin._tricorder_db_for(str(repo_a)), str(db_path))

    def test_plugin_db_for_counts_file_state_not_tags(self):
        # A mapped repo whose files are all tagless (data-only) must still
        # resolve — coverage is file_state rows, never tags-distinct.
        from database import DBStore
        tmp = Path(tempfile.mkdtemp(prefix="plugdb_tagless_"))
        self.addCleanup(lambda: __import__("shutil").rmtree(tmp, ignore_errors=True))
        repo = (tmp / "proj").resolve()
        repo.mkdir(parents=True)
        cache = Path(tempfile.mkdtemp(prefix="plugcache_tagless_"))
        self.addCleanup(lambda: __import__("shutil").rmtree(cache, ignore_errors=True))
        db_path = cache / "db" / "proj.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        db = DBStore(str(db_path))
        db.set_meta(str(repo), "sig")
        db.set_file_state("data.json", 42, 1234567890)
        db.conn.commit()
        db.conn.close()
        old_env = os.environ.get("TRICORDER_CACHE_HOME")
        os.environ["TRICORDER_CACHE_HOME"] = str(cache)
        self.addCleanup(lambda: (os.environ.pop("TRICORDER_CACHE_HOME", None)
                                 if old_env is None
                                 else os.environ.update({"TRICORDER_CACHE_HOME": old_env})))
        plugin = self._plugin()
        self.assertEqual(plugin._tricorder_db_for(str(repo)), str(db_path))
        line = plugin._db_coverage_line(str(db_path), str(repo))
        self.assertIn("1 files, 0 tags", line)


if __name__ == "__main__":
    unittest.main()
