"""Meter agent-eval-2.0 Go legs: sum of agent-visible result tokens per leg.

Leg score = tokens across tool-result payloads (JSON hits, file reads,
grep/dir-listing output). Timed-out calls delivered nothing -> 0.
Directive text excluded (it is the treatment, not the spend).
Tokenizer: tip utils.count_tokens (tiktoken cl100k), same as 9/21 + 9/22.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

TIP = Path(r"C:\Users\macdo\AppData\Local\Temp\opencode\tricorder-fix-parallel-qualify")
GO = Path(r"D:\Projects\Tricorder-Testing-Repos\go")
TMP = Path(r"C:\Users\macdo\AppData\Local\Temp\opencode")
PY = r"C:\ProgramData\miniconda3\python.exe"

sys.path.insert(0, str(TIP))
from utils import count_tokens  # noqa: E402


def tok(text):
    return count_tokens(text, "gpt-4")


def read_range(rel, offset, limit):
    lines = (GO / rel).read_text(encoding="utf-8").splitlines()
    return "\n".join(lines[offset - 1:offset - 1 + limit])


def grep_file(rel, pattern):
    out = []
    for i, ln in enumerate((GO / rel).read_text(encoding="utf-8").splitlines(), 1):
        if re.search(pattern, ln):
            out.append(f"{i}:{ln}")
    return "\n".join(out)


def listing(rel):
    return "\n".join(sorted(p.name for p in (GO / rel).iterdir()))


def grep_glob(subdir, glob, pattern):
    out = []
    for p in sorted((GO / subdir).glob(glob)):
        for i, ln in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            if re.search(pattern, ln):
                out.append(f"{p.name}:{i}:{ln}")
    return "\n".join(out)


def cli(db, *args):
    cmd = [PY, str(TIP / "tricorder.py"), "--root", str(GO),
           "--db-path", str(db), *args]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    return p.stdout


DB1, DB3, DB5 = TMP / "eval-go-G1.db", TMP / "eval-go-G3.db", TMP / "eval-go-G5.db"
legs = {}

# ---- A-legs (tricorder): init + detect/symbols JSON re-run warm + reads ----
a = {}
a["init"] = cli(DB5, "--init")
a["detect_nl"] = cli(DB5, "--detect", "build SSA form for function",
                     "--format", "json", "--max-results", "10")
a["detect_exact"] = cli(DB5, "--detect", "BuildSSA",
                        "--format", "json", "--max-results", "10")
a["symbols"] = cli(DB5, "--symbols", "buildssa", "--format", "json")
a["read"] = read_range("src/cmd/compile/internal/ssagen/ssa.go", 295, 50)
legs["A-G5"] = a

b = {}
b["init"] = cli(DB3, "--init")
b["detect"] = cli(DB3, "--detect", "channel send receive",
                  "--format", "json", "--max-results", "10")
b["symbols"] = cli(DB3, "--symbols", "chansend chanrecv", "--format", "json")
legs["A-G3"] = b  # transcript lists no read commands; bodies unverified

c = {}
c["init"] = cli(DB1, "--init")
c["detect"] = cli(DB1, "--detect", "background mark worker gc",
                  "--format", "json", "--max-results", "10")
c["symbols1"] = cli(DB1, "--symbols", "gcBgMarkWorker", "--format", "json")
c["symbols2"] = cli(DB1, "--symbols", "gcDrain", "--format", "json")
c["read"] = read_range("src/runtime/mgc.go", 1766, 80)
legs["A-G1"] = c

# ---- B-legs (baseline): reads + grep/dir outputs ----
d = {}
d["ls_runtime"] = listing("src/runtime")
d["grep_mgc"] = grep_glob("src/runtime", "mgc*.go",
                          r"func gcBgMarkWorker|func gcMark|mark phase|gcMarkWorker")
d["read1"] = read_range("src/runtime/mgc.go", 1766, 160)
d["read2"] = read_range("src/runtime/mgc.go", 1972, 60)
d["grep_mark"] = grep_file("src/runtime/mgcmark.go",
                           r"^func gcDrain|^func gcMark|^func greyobject|^func blacken")
d["read3"] = read_range("src/runtime/mgcmark.go", 1181, 80)
d["read4"] = read_range("src/runtime/mgc.go", 880, 30)
legs["B-G1"] = d

e = {}
e["ls_runtime"] = listing("src/runtime")
e["grep_chan"] = grep_file("src/runtime/chan.go",
                           r"^func (chansend|chanrecv|recv|send|select)")
e["read1"] = read_range("src/runtime/chan.go", 155, 30)
e["read2"] = read_range("src/runtime/chan.go", 305, 40)
e["read3"] = read_range("src/runtime/chan.go", 495, 30)
e["read4"] = read_range("src/runtime/chan.go", 690, 25)
e["read5"] = read_range("src/runtime/chan.go", 384, 25)
legs["B-G3"] = e

f = {}
f["ls_root"] = listing(".")
f["ls_internal"] = listing("src/cmd/compile/internal")
f["ls_ssagen"] = listing("src/cmd/compile/internal/ssagen")
f["read_ssa_full"] = (GO / "src/cmd/compile/internal/ssagen/ssa.go").read_text(
    encoding="utf-8")
f["grep_ssagen"] = grep_glob("src/cmd/compile/internal/ssagen", "*.go",
                             r"func (Build|Compile|buildssa|ssaGen)")
f["read_pgen"] = read_range("src/cmd/compile/internal/ssagen/pgen.go", 290, 120)
f["grep_gc"] = grep_file("src/cmd/compile/internal/gc/compile.go",
                         r"ssagen\.Compile|buildssa")
f["read_gc1"] = read_range("src/cmd/compile/internal/gc/compile.go", 155, 50)
f["read_gc2"] = read_range("src/cmd/compile/internal/gc/compile.go", 130, 30)
legs["B-G5"] = f

table = {}
for leg, parts in legs.items():
    counts = {k: tok(v) for k, v in parts.items()}
    counts["_total"] = sum(counts.values())
    table[leg] = counts

print(json.dumps(table, indent=1))
(TMP / "meter_go.json").write_text(json.dumps(table, indent=1))
