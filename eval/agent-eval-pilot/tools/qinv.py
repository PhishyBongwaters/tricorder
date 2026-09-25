import re, glob, os
for p in sorted(glob.glob(r'eval/agent-eval-pilot/v13/leg-A-*/prompt.md')):
    txt = open(p, encoding='utf-8', errors='replace').read()
    m = re.search(r'Question ONLY.*?\n(.*?)\n', txt, re.S)
    q = (m.group(1).strip()[:110] if m else '?')
    print(os.path.basename(os.path.dirname(p)), '|', q)
