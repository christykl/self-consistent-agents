"""Print a compact excerpt of one episode: analysis/plan, commands, truncated output.

Usage: python trace.py RUN_DIR EPISODE FIRST_STEP LAST_STEP [WIDTH]
"""
import json,sys,re
run,ep=sys.argv[1],sys.argv[2]; lo,hi=int(sys.argv[3]),int(sys.argv[4]); w=int(sys.argv[5]) if len(sys.argv)>5 else 220
st=[json.loads(l) for l in open(f'{run}/trajectories/{ep}/messages.jsonl')]
for s in st[1:]:
    if not (lo<=s['step_id']<=hi): continue
    msg=(s.get('message') or '')
    a=re.search(r'Analysis: (.*?)(\nPlan:|$)',msg,re.S); p=re.search(r'Plan: (.*)',msg,re.S)
    print(f"--- step {s['step_id']}")
    if a: print('analysis:', a.group(1).strip().replace('\n',' ')[:w])
    if p: print('plan:', p.group(1).strip().replace('\n',' ')[:w])
    res=((s.get('observation') or {}).get('results') or [])
    for c in s.get('tool_calls') or []:
        print('$', (c.get('arguments') or {}).get('keystrokes','').strip()[:w*2])
    for r in res[:1]:
        t=re.sub(r'\n{2,}','\n',(r.get('content') or '')).strip()
        print('>', t[-w*2:].replace('\n','\n> '))
