import glob, os, re
for p in sorted(glob.glob(r'eval/agent-eval-pilot/v13/leg-A-*/grade.md')):
    leg = os.path.basename(os.path.dirname(p))
    if 'attempt1' not in leg and 'attempt2' not in leg:
        continue
    txt = open(p, encoding='utf-8', errors='replace').read()
    verdict = re.search(r'Verdict:\s*([^\n]+)', txt)
    gt = re.search(r'[Gg]round truth[:\s]*([^\n]+)', txt)
    tok = re.search(r'\*\*Total\*\*\s*\|\s*\|\s*\*\*([\d,]+)\*\*', txt)
    print('===', leg)
    print('  verdict:', verdict.group(1).strip()[:80] if verdict else '?')
    print('  gt:', (gt.group(1).strip()[:160] if gt else '?'))
    print('  A-tokens:', tok.group(1) if tok else '?')
