"""TC-010: parser security fixtures — adversarial inputs for tree-sitter.

These fixtures exercise the parser against hostile source that should never
crash, hang, or leak unbounded memory. Each is small and deterministic so the
test stays fast. get_tags_raw is expected to either return [] or a bounded
list of tags, and never raise.
"""
from pathlib import Path

SECURITY_DIR = Path(__file__).parent / "security"

# Deeply nested syntax — historically a parser recursion/stack-exhaustion vector.
DEEPLY_NESTED_PY = "\n".join("    " * i + f"def f{i}():\n" for i in range(0, 4000)) + "    pass\n"

# Huge single line — pathological for line-based tooling and AST row tracking.
HUGE_LINE_PY = "x = " + "+".join(f"a{i}" for i in range(0, 200000)) + "\n"

# Malformed Python: unbalanced brackets at scale.
MALFORMED_PY = "(" * 100000 + "def broken(:\n    pass\n" + ")" * 100000 + "\n"

# Unicode identifiers / homoglyphs — encoding edge cases.
UNICODE_PY = (
    "def \u03b1\u03b2\u03b3():\n"
    "    \u4e2d\u6587 = 1\n"
    "    return \U0001f600\n"
)

# Broken source tree fragment — stray NUL and control bytes.
BROKEN_PY = "def ok():\n\x00\x01\x02    return None\n"

# Giant string literal — memory pressure vector.
GIANT_STRING_PY = "S = '" + "A" * 500000 + "'\n"

FIXTURES = {
    "deeply_nested.py": DEEPLY_NESTED_PY,
    "huge_line.py": HUGE_LINE_PY,
    "malformed.py": MALFORMED_PY,
    "unicode_idents.py": UNICODE_PY,
    "broken_source.py": BROKEN_PY,
    "giant_string.py": GIANT_STRING_PY,
}
