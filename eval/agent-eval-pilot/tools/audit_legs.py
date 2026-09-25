import glob, os, re
base = r'eval/agent-eval-pilot/v13'
for d in sorted(glob.glob(os.path.join(base, 'leg-*/'))):
    leg = os.path.basename(os.path.normpath(d))
    steps = [p for p in glob.glob(os.path.join(d, 'step*.txt'))
             if os.path.isfile(p)]
    tr = os.path.join(d, 'transcript.md')
    if not os.path.exists(tr):
        print('%-32s steps=%2d transcript=MISSING' % (leg, len(steps)))
        continue
    txt = open(tr, encoding='utf-8', errors='replace').read()
    rows = [l for l in txt.splitlines()
            if re.match(r'\|\s*\d+\s*\|', l)]
    print('%-32s steps=%2d transcript_rows=%2d %s'
          % (leg, len(steps), len(rows),
             'OK' if (rows and len(steps) >= len(rows)) else
             ('GAP(%d missing)' % (len(rows) - len(steps)) if rows and len(steps) < len(rows)
              else ('OK-unmetered' if not rows and not steps else
                    ('no-rows+%dsteps' % len(steps))))))
