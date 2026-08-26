"""Issue #42 — parser correctness for language-specific constructs.

Asserts the exact constructs called out in the issue are extracted correctly:
  - C++    : template<...> class Foo { void bar(); }  -> "Foo::bar" (scoped)
  - Rust   : impl<T> Trait for Struct<T> { fn needed } -> "needed" as method
  - Python : class A: async def method(self)           -> "method" with async kept

Run:  python -m pytest tests/test_issue42.py -v
"""
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core import Tricorder  # noqa: E402


def _make_tricorder(tmp_root: Path) -> Tricorder:
    return Tricorder(
        root=str(tmp_root),
        file_reader_func=lambda f: Path(f).read_text(encoding="utf-8")
        if Path(f).exists() else None,
        output_handler_funcs={"info": lambda *a, **k: None,
                              "warning": lambda *a, **k: None,
                              "error": lambda *a, **k: None},
    )


class TestParserCorrectness(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.tr = _make_tricorder(self.tmp)

    def _write(self, ext, code):
        f = self.tmp / f"sample{ext}"
        f.write_text(code, encoding="utf-8")
        return str(f)

    def test_cpp_template_method_scoped(self):
        code = ("template<typename T>\n"
                "class Foo {\n"
                "public:\n"
                "    void bar();\n"
                "};\n")
        recs = self.tr.get_symbols(self._write(".cpp", code), "x.cpp")
        bar = [r for r in recs if r.name.endswith("::bar") or r.name == "bar"]
        self.assertTrue(bar, "C++ Foo::bar not extracted")
        self.assertTrue(
            any(r.name == "Foo::bar" for r in recs),
            f"expected scoped name 'Foo::bar', got names={[r.name for r in recs]}",
        )

    def test_rust_impl_trait_method(self):
        code = ("trait Trait {\n"
                "    fn needed(&self);\n"
                "}\n"
                "struct Struct<T> { val: T }\n"
                "impl<T> Trait for Struct<T> {\n"
                "    fn needed(&self) {}\n"
                "}\n")
        recs = self.tr.get_symbols(self._write(".rs", code), "x.rs")
        methods = [r for r in recs if r.name == "needed" or r.name.endswith("::needed")]
        self.assertTrue(methods, "Rust impl<T> Trait::needed not extracted")
        self.assertTrue(
            any(r.type == "method" for r in methods),
            f"needed should be a method, got {[r.type for r in methods]}",
        )

    def test_python_async_method_keeps_async(self):
        code = ("class A:\n"
                "    async def method(self):\n"
                "        return 1\n")
        recs = self.tr.get_symbols(self._write(".py", code), "x.py")
        methods = [r for r in recs if r.name == "method"]
        self.assertTrue(methods, "Python async def method not extracted")
        sig = (methods[0].signature or "") + (methods[0].body or "")
        self.assertIn(
            "async", sig,
            f"async keyword lost from method signature/body: sig={methods[0].signature!r}",
        )


if __name__ == "__main__":
    unittest.main()
