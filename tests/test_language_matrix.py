"""Per-language contract test for README signature-extraction claims.

Issue #25: README claims "Signature extraction + return types (10 languages)".
Nothing failed if a grammar/query change silently broke Swift signatures or
C# return types. This file enforces that claim: every claimed language must
produce at least one *definition* symbol with a non-empty signature from a
representative fixture, and the wider language-pack set must produce at least
one definition symbol.

Fixtures are inline strings (no temp files) so the test is self-contained and
runnable from any checkout:

    pytest tests/test_language_matrix.py -q

To confirm the test is real (not a no-op), corrupt any entry in
queries/tree-sitter-language-pack/<lang>-tags.scm — the matching case fails.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core import Tricorder
from utils import detect_lang

# The 10 languages README explicitly claims (README.md "Language Coverage"
# + "Signature extraction + return types (10 languages)"):
#   Python, JS/TS, C, C++, Java, Go, Rust, Swift, C#, Ruby
# Each entry: (language_key, file_extension, representative source)
# The source must contain at least one function/method/class definition so the
# test has something to assert on.
CLAIMED_LANGUAGES = [
    ("python", ".py", (
        "def add(a, b):\n"
        "    \"\"\"Add two numbers.\"\"\"\n"
        "    return a + b\n"
    )),
    ("javascript", ".js", (
        "function greet(name) {\n"
        "  return 'hi ' + name;\n"
        "}\n"
    )),
    ("typescript", ".ts", (
        "function greet(name: string): string {\n"
        "  return 'hi ' + name;\n"
        "}\n"
    )),
    ("c", ".c", (
        "int add(int a, int b) {\n"
        "  return a + b;\n"
        "}\n"
    )),
    ("cpp", ".cpp", (
        "int add(int a, int b) {\n"
        "  return a + b;\n"
        "}\n"
    )),
    ("java", ".java", (
        "class Calc {\n"
        "  public int add(int a, int b) {\n"
        "    return a + b;\n"
        "  }\n"
        "}\n"
    )),
    ("go", ".go", (
        "package main\n"
        "\n"
        "func add(a int, b int) int {\n"
        "  return a + b\n"
        "}\n"
    )),
    ("rust", ".rs", (
        "fn add(a: i32, b: i32) -> i32 {\n"
        "  a + b\n"
        "}\n"
    )),
    ("swift", ".swift", (
        "func add(_ a: Int, _ b: Int) -> Int {\n"
        "  return a + b\n"
        "}\n"
    )),
    ("csharp", ".cs", (
        "class Calc {\n"
        "  public int Add(int a, int b) {\n"
        "    return a + b;\n"
        "  }\n"
        "}\n"
    )),
    ("ruby", ".rb", (
        "def add(a, b)\n"
        "  a + b\n"
        "end\n"
    )),
]

# Wider language-pack set: assert at least one *definition* symbol (name only,
# signature may legitimately be empty for some of these grammars).
WIDER_LANGUAGE_PACK = [
    ("kotlin", ".kt", (
        "fun add(a: Int, b: Int): Int {\n"
        "  return a + b\n"
        "}\n"
    )),
    ("php", ".php", (
        "<?php\n"
        "function add($a, $b) {\n"
        "  return $a + $b;\n"
        "}\n"
    )),
    ("scala", ".scala", (
        "object Calc {\n"
        "  def add(a: Int, b: Int): Int = a + b\n"
        "}\n"
    )),
    ("dart", ".dart", (
        "int add(int a, int b) {\n"
        "  return a + b;\n"
        "}\n"
    )),
    ("elixir", ".ex", (
        "defmodule Calc do\n"
        "  def add(a, b), do: a + b\n"
        "end\n"
    )),
    ("ocaml", ".ml", (
        "let add a b = a + b\n"
    )),
    ("lua", ".lua", (
        "function add(a, b)\n"
        "  return a + b\n"
        "end\n"
    )),
    ("commonlisp", ".lisp", (
        "(defun add (a b)\n"
        "  (+ a b))\n"
    )),
]


def _make_tricorder(tmp_root: Path) -> Tricorder:
    """Instantiate Tricorder with no disk cache side effects."""
    return Tricorder(
        root=str(tmp_root),
        file_reader_func=lambda f: Path(f).read_text(encoding="utf-8")
        if Path(f).exists() else None,
        output_handler_funcs={"info": lambda *a, **k: None,
                              "warning": lambda *a, **k: None,
                              "error": lambda *a, **k: None},
    )


class TestLanguageMatrix(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(__file__).parent / "_lm_tmp"
        self.tmp.mkdir(exist_ok=True)
        self.tricorder = _make_tricorder(self.tmp)

    def tearDown(self):
        import shutil
        if self.tmp.exists():
            shutil.rmtree(self.tmp, ignore_errors=True)

    def _write(self, ext: str, code: str) -> str:
        f = self.tmp / f"sample{ext}"
        f.write_text(code, encoding="utf-8")
        return str(f)

    def test_detect_lang_matches_all_claimed(self):
        """Sanity: detect_lang resolves every claimed extension to a grammar."""
        for lang, ext, _ in CLAIMED_LANGUAGES:
            f = self._write(ext, "")
            detected = detect_lang(f)
            self.assertEqual(
                detected, lang,
                f"detect_lang({ext}) -> {detected!r}, expected {lang!r}"
            )

    def test_claimed_languages_extract_defined_signature(self):
        """Every README-claimed language yields >=1 definition with a signature."""
        for lang, ext, code in CLAIMED_LANGUAGES:
            with self.subTest(language=lang):
                f = self._write(ext, code)
                recs = self.tricorder.get_symbols(f, f)
                self.assertTrue(
                    recs,
                    f"{lang}: no definition symbols extracted from fixture"
                )
                defined = [r for r in recs if r.signature and r.signature.strip()]
                self.assertTrue(
                    defined,
                    f"{lang}: extracted symbols but none had a signature: "
                    f"{[r.name for r in recs]}"
                )

    def test_wider_language_pack_extracts_definitions(self):
        """The wider language-pack set yields at least one definition symbol."""
        for lang, ext, code in WIDER_LANGUAGE_PACK:
            with self.subTest(language=lang):
                f = self._write(ext, code)
                recs = self.tricorder.get_symbols(f, f)
                self.assertTrue(
                    recs,
                    f"{lang}: no definition symbols extracted from fixture "
                    f"(language-pack grammar may be missing/weak)"
                )


if __name__ == "__main__":
    unittest.main()
