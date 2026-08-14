"""Parity tests for CLI, MCP, and plugin scan plumbing."""
import importlib
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path

sys.path.insert(0, '.')

from utils import discover_src_files
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


if __name__ == '__main__':
    unittest.main()
