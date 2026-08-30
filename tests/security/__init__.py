import pathlib
SECURITY_DIR = pathlib.Path(__file__).parent
FIXTURES = {
    "deeply_nested.py": "def a():\n    def b():\n        def c():\n            pass\n",
    "huge_line.py": "x = " + "a(" * 1000 + "1" + ")" * 1000,
    "malformed.py": "def foo(:\n    pass\n",
    "unicode_idents.py": "def 🚀():\n    pass\n",
    "broken_source.py": "class Unclosed:\n    def __init__(self):\n",
    "giant_string.py": "x = '''" + "abc" * 10000 + "'''\n",
}
