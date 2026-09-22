"""
SCM file handling for Tricorder.
"""

from pathlib import Path
from typing import Optional

def get_scm_fname(lang: str) -> Optional[str]:
    """Get the SCM query file for a language."""
    scm_files = {
        'arduino': 'arduino-tags.scm',
        'awk': 'awk-tags.scm',
        'actionscript': 'actionscript-tags.scm',
        'ada': 'ada-tags.scm',
        'bash': 'bash-tags.scm',
        'cairo': 'cairo-tags.scm',
        'chatito': 'chatito-tags.scm',
        'cmake': 'cmake-tags.scm',
        'commonlisp': 'commonlisp-tags.scm',
        'clojure': 'clojure-tags.scm',
        'crystal': 'crystal-tags.scm',
        'cpp': 'cpp-tags.scm',
        'csharp': 'csharp-tags.scm',
        'c': 'c-tags.scm',
        'dart': 'dart-tags.scm',
        'd': 'd-tags.scm',
        'elisp': 'elisp-tags.scm',
        'elixir': 'elixir-tags.scm',
        'fortran': 'fortran-tags.scm',
        'func': 'func-tags.scm',
        'fsharp': 'fsharp-tags.scm',
        'fish': 'fish-tags.scm',
        'elm': 'elm-tags.scm',
        'erlang': 'erlang-tags.scm',
        'gleam': 'gleam-tags.scm',
        'gdscript': 'gdscript-tags.scm',
        'glsl': 'glsl-tags.scm',
        'go': 'go-tags.scm',
        'graphql': 'graphql-tags.scm',
        'groovy': 'groovy-tags.scm',
        'hack': 'hack-tags.scm',
        'haskell': 'haskell-tags.scm',
        'haxe': 'haxe-tags.scm',
        'hare': 'hare-tags.scm',
        'javascript': 'javascript-tags.scm',
        'java': 'java-tags.scm',
        'janet': 'janet-tags.scm',
        'julia': 'julia-tags.scm',
        'llvm': 'llvm-tags.scm',
        'lua': 'lua-tags.scm',
        'lean': 'lean-tags.scm',
        'matlab': 'matlab-tags.scm',
        'mojo': 'mojo-tags.scm',
        'motoko': 'motoko-tags.scm',
        'nix': 'nix-tags.scm',
        'nim': 'nim-tags.scm',
        'make': 'make-tags.scm',
        'ocaml_interface': 'ocaml_interface-tags.scm',
        'ocaml': 'ocaml-tags.scm',
        'odin': 'odin-tags.scm',
        'pascal': 'pascal-tags.scm',
        'pony': 'pony-tags.scm',
        'proto': 'proto-tags.scm',
        'perl': 'perl-tags.scm',
        'powershell': 'powershell-tags.scm',
        'properties': 'properties-tags.scm',
        'python': 'python-tags.scm',
        'qmljs': 'qmljs-tags.scm',
        'racket': 'racket-tags.scm',
        'r': 'r-tags.scm',
        'reason': 'reason-tags.scm',
        'rescript': 'rescript-tags.scm',
        'ruby': 'ruby-tags.scm',
        'rust': 'rust-tags.scm',
        'solidity': 'solidity-tags.scm',
        'sql': 'sql-tags.scm',
        'zig': 'zig-tags.scm',
        'starlark': 'starlark-tags.scm',
        'sway': 'sway-tags.scm',
        'swift': 'swift-tags.scm',
        'udev': 'udev-tags.scm',
        'verilog': 'verilog-tags.scm',
        'wast': 'wast-tags.scm',
        'wat': 'wat-tags.scm',
        'vb': 'vb-tags.scm',
        'vhdl': 'vhdl-tags.scm',
        'cython': 'cython-tags.scm',
        'c_sharp': 'c_sharp-tags.scm',
        'hcl': 'hcl-tags.scm',
        'kotlin': 'kotlin-tags.scm',
        'php': 'php-tags.scm',
        'ql': 'ql-tags.scm',
        'scala': 'scala-tags.scm',
        'sml': 'sml-tags.scm',
        'scheme': 'scheme-tags.scm',
        'typescript': 'typescript-tags.scm',
        'vim': 'vim-tags.scm',
        'tablegen': 'tablegen-tags.scm',
        'tact': 'tact-tags.scm',
        'thrift': 'thrift-tags.scm',
        'tcl': 'tcl-tags.scm',
        'uxntal': 'uxntal-tags.scm',
        'yang': 'yang-tags.scm',
        'yul': 'yul-tags.scm',
        'vala': 'vala-tags.scm',
        'wgsl': 'wgsl-tags.scm',
    }
    
    if lang in scm_files:
        scm_filename = scm_files[lang]
        # Search in tree-sitter-language-pack
        scm_path = Path(__file__).parent / "queries" / "tree-sitter-language-pack" / scm_filename
        if scm_path.exists():
            return str(scm_path)
        # Search in tree-sitter-languages
        scm_path = Path(__file__).parent / "queries" / "tree-sitter-languages" / scm_filename
        if scm_path.exists():
            return str(scm_path)
    
    return None
