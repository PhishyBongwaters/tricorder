#!/usr/bin/env python3
"""Run bench_validity.py with verified output."""
import subprocess, sys
res = subprocess.run([sys.executable, "bench/bench_validity.py"], capture_output=True, text=True)
print(res.stdout)
print(res.stderr, file=sys.stderr)
sys.exit(res.returncode)
