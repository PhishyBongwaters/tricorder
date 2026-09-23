#!/usr/bin/env python3
"""meter_leg.py — token-meter agent-leg payload artifacts.

Usage: python eval/agent-eval-pilot/v13/meter_leg.py <legdir>

Counts agent-visible result-payload tokens (utils.count_tokens, tiktoken
cl100k) for every step_*.txt in the leg dir. Steps that delivered nothing
(timeouts, harness errors) have no artifact and count 0 — noted, not
invented.
"""
import glob
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
from utils import count_tokens

legdir = sys.argv[1]
total = 0
for p in sorted(glob.glob(os.path.join(legdir, "step_*.txt"))):
    with open(p, encoding="utf-8", errors="replace") as f:
        text = f.read()
    tk = count_tokens(text)
    total += tk
    print(f"{os.path.basename(p)}: {tk} tokens ({len(text)} chars)")
print(f"TOTAL: {total} tokens")
