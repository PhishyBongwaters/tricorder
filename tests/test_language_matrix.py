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
    ("erlang", ".erl", (
        "-module(calc).\n"
        "-export([add/2]).\n"
        "add(A, B) -> A + B.\n"
    )),
    ("arduino", ".ino", (
        "void setup() {}\n"
        "void loop() {}\n"
    )),
    ("chatito", ".chatito", (
        "%[greet]\n"
        "    ~[hi]\n"
    )),
    ("d", ".d", (
        "int add(int a, int b) {\n"
        "  return a + b;\n"
        "}\n"
    )),
    ("elisp", ".el", (
        "(defun add (a b)\n"
        "  (+ a b))\n"
    )),
    ("elm", ".elm", (
        "add a b = a + b\n"
    )),
    ("gleam", ".gleam", (
        "fn add(a: Int, b: Int) -> Int { a + b }\n"
    )),
    ("ocaml_interface", ".mli", (
        "val add : int -> int -> int\n"
    )),
    ("pony", ".pony", (
        "actor Main\n"
        "  new create(env: Env) => None\n"
    )),
    ("r", ".r", (
        "add <- function(a, b) a + b\n"
    )),
    ("racket", ".rkt", (
        "#lang racket\n"
        "(define (add a b) (+ a b))\n"
    )),
    ("solidity", ".sol", (
        "contract C {\n"
        "  function add(uint a, uint b) public returns (uint) {\n"
        "    return a + b;\n"
        "  }\n"
        "}\n"
    )),
    ("bash", ".sh", (
        "greet() {\n"
        "  echo hi\n"
        "}\n"
    )),
    ("powershell", ".ps1", (
        "function Add($a, $b) {\n"
        "  return $a + $b\n"
        "}\n"
    )),
    ("perl", ".pl", (
        "sub add {\n"
        "  my ($a, $b) = @_;\n"
        "  return $a + $b;\n"
        "}\n"
    )),
    ("haskell", ".hs", (
        "add a b = a + b\n"
    )),
    ("julia", ".jl", (
        "function add(a, b)\n"
        "  return a + b\n"
        "end\n"
    )),
    ("zig", ".zig", (
        "fn add(a: i32, b: i32) i32 {\n"
        "  return a + b;\n"
        "}\n"
    )),
    ("verilog", ".v", (
        "module adder(input [31:0] a, output [31:0] s);\n"
        "  assign s = a + 1;\n"
        "endmodule\n"
    )),
    ("groovy", ".groovy", (
        "def add(a, b) {\n"
        "  return a + b\n"
        "}\n"
    )),
    ("hack", ".hack", (
        "function add(int $a, int $b): int {\n"
        "  return $a + $b;\n"
        "}\n"
    )),
    ("pascal", ".pas", (
        "function Add(a, b: Integer): Integer;\n"
        "begin\n"
        "  Add := a + b;\n"
        "end;\n"
    )),
    ("matlab", ".m", (
        "function s = add(a, b)\n"
        "  s = a + b;\n"
        "end\n"
    )),
    ("fortran", ".f90", (
        "function add(a, b)\n"
        "  integer :: add, a, b\n"
        "  add = a + b\n"
        "end function add\n"
    )),
    ("clojure", ".clj", (
        "(ns calc)\n"
        "(defn add [a b]\n"
        "  (+ a b))\n"
    )),
    ("gdscript", ".gd", (
        "func add(a, b):\n"
        "  return a + b\n"
    )),
    ("cairo", ".cairo", (
        "fn add(a: u32, b: u32) -> u32 {\n"
        "  a + b\n"
        "}\n"
    )),
    ("sql", ".sql", (
        "CREATE PROCEDURE addem(a INT, b INT)\n"
        "BEGIN\n"
        "  SELECT a + b;\n"
        "END;\n"
    )),
    ("proto", ".proto", (
        "syntax = \"proto3\";\n"
        "message Calc {\n"
        "  int32 a = 1;\n"
        "}\n"
    )),
    ("make", ".mk", (
        "build: main.o\n"
        "\tgcc -o app main.o\n"
    )),
    ("cmake", ".cmake", (
        "function(build target)\n"
        "  add_executable(${target} main.cpp)\n"
        "endfunction()\n"
    )),
    ("glsl", ".glsl", (
        "void main() {\n"
        "  gl_FragColor = vec4(1.0);\n"
        "}\n"
    )),
    ("func", ".fc", (
        "() recv_internal(int x) {\n"
        "  return x + 1;\n"
        "}\n"
    )),
    ("tsx", ".tsx", (
        "function add(a: number, b: number): number {\n"
        "  return a + b;\n"
        "}\n"
    )),
    ("uxntal", ".tal", (
        "@add ( a b -- c )\n"
        "  + JMP2r\n"
    )),
    ("llvm", ".ll", (
        "define i32 @add(i32 %a, i32 %b) {\n"
        "entry:\n"
        "  ret i32 %a\n"
        "}\n"
    )),
    ("tablegen", ".td", (
        "class Calc {\n"
        "  int A = 1;\n"
        "}\n"
    )),
    ("actionscript", ".as", (
        "package calc {\n"
        "  public class Calc {\n"
        "    public function add(a:int, b:int):int {\n"
        "      return a + b;\n"
        "    }\n"
        "  }\n"
        "}\n"
    )),
    ("ada", ".adb", (
        "package body Calc is\n"
        "  function Add(A, B : Integer) return Integer is\n"
        "  begin\n"
        "    return A + B;\n"
        "  end Add;\n"
        "end Calc;\n"
    )),
    ("fish", ".fish", (
        "function greet\n"
        "  echo hi\n"
        "end\n"
    )),
    ("hare", ".ha", (
        "fn add(a: int, b: int) int = {\n"
        "  return a + b;\n"
        "};\n"
    )),
    ("haxe", ".hx", (
        "class Calc {\n"
        "  public function add(a:Int, b:Int):Int {\n"
        "    return a + b;\n"
        "  }\n"
        "}\n"
    )),
    ("janet", ".janet", (
        "(defn add [a b]\n"
        "  (+ a b))\n"
    )),
    ("nix", ".nix", (
        "mkShell {\n"
        "  buildInputs = [ pkgs.hello ];\n"
        "}\n"
    )),
    ("odin", ".odin", (
        "package calc\n"
        "add :: proc(a, b: int) -> int {\n"
        "  return a + b\n"
        "}\n"
    )),
    ("qmljs", ".qml", (
        "Item {\n"
        "  function add(a, b) {\n"
        "    return a + b;\n"
        "  }\n"
        "}\n"
    )),
    ("scheme", ".scm", (
        "(define (add a b)\n"
        "  (+ a b))\n"
    )),
    ("starlark", ".bzl", (
        "def add(a, b):\n"
        "  return a + b\n"
    )),
    ("tcl", ".tcl", (
        "proc add {a b} {\n"
        "  return $a\n"
        "}\n"
    )),
    ("thrift", ".thrift", (
        "service Calc {\n"
        "  i32 add(1: i32 a, 2: i32 b);\n"
        "}\n"
    )),
    ("vhdl", ".vhd", (
        "entity adder is\n"
        "  port (a : in bit);\n"
        "end entity;\n"
    )),
    ("vim", ".vim", (
        "function! Add(a, b)\n"
        "  return a:a + a:b\n"
        "endfunction\n"
    )),
    ("wgsl", ".wgsl", (
        "fn add(a: u32, b: u32) -> u32 {\n"
        "  return a + b;\n"
        "}\n"
    )),
    ("nim", ".nim", (
        "proc add(a, b: int): int =\n"
        "  return a + b\n"
    )),
    ("crystal", ".cr", (
        "def add(a, b)\n"
        "  a + b\n"
        "end\n"
    )),
    ("awk", ".awk", (
        "function add(a, b) {\n"
        "  return a + b\n"
        "}\n"
    )),
    ("cython", ".pyx", (
        "def add(a, b):\n"
        "  return a + b\n"
    )),
    ("sml", ".sml", (
        "fun add (a, b) = a + b\n"
    )),
    ("vala", ".vala", (
        "class Calc : Object {\n"
        "  public int add(int a, int b) {\n"
        "    return a + b;\n"
        "  }\n"
        "}\n"
    )),
    ("graphql", ".graphql", (
        "type Calc {\n"
        "  add(a: Int, b: Int): Int\n"
        "}\n"
    )),
    ("lean", ".lean", (
        "def add (a b : Nat) : Nat := a + b\n"
    )),
    ("vb", ".vb", (
        "Public Class Calc\n"
        "  Public Function Add(a As Integer, b As Integer) As Integer\n"
        "    Return a + b\n"
        "  End Function\n"
        "End Class\n"
    )),
    ("fsharp", ".fsi", (
        "module Calc\n"
        "let add a b = a + b\n"
    )),
    ("rescript", ".res", (
        "let add = (a, b) => a + b;\n"
    )),
    ("sway", ".sw", (
        "fn add(a: u64, b: u64) -> u64 {\n"
        "  a + b\n"
        "}\n"
    )),
    ("tact", ".tact", (
        "fun add(a: Int, b: Int): Int {\n"
        "  return a + b;\n"
        "}\n"
    )),
    ("yang", ".yang", (
        "module calc {\n"
        "  container data {\n"
        "  }\n"
        "}\n"
    )),
    ("yul", ".yul", (
        "object \"Calc\" {\n"
        "  code {\n"
        "    function add(a, b) -> c {\n"
        "      c := add(a, b)\n"
        "    }\n"
        "  }\n"
        "}\n"
    )),
    ("ql", ".ql", (
        "predicate isThree(int x) {\n"
        "  x = 3\n"
        "}\n"
    )),
    ("wast", ".wast", (
        "(module\n"
        "  (func $add (param $a i32) (result i32)\n"
        "    local.get $a))\n"
    )),
    ("wat", ".wat", (
        "(module\n"
        "  (func $add (param $a i32) (result i32)\n"
        "    local.get $a))\n"
    )),
    ("mojo", ".mojo", (
        "fn add(a: Int, b: Int) -> Int:\n"
        "  return a + b\n"
    )),
    ("motoko", ".mo", (
        "actor Calc {\n"
        "  public func add(a : Nat, b : Nat) : async Nat {\n"
        "    return a + b;\n"
        "  };\n"
        "};\n"
    )),
    ("reason", ".re", (
        "let add = (a, b) => a + b;\n"
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
