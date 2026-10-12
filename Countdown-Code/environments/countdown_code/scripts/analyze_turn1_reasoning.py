"""Analysis of turn-1 reasoning tokens vs stated success probability (FINDINGS_STATE_A.md, Part 2).

Reads outputs/turn1_reasoning/turn1.jsonl (from scripts/turn1_reasoning.py; 200 problems x 4
turn-1-only replays of the ask-success-probability prompt) and joins per-problem difficulty and
outcomes from the no-ask run 3fb9e8c3 and the conditioned run 658b8ecd. Cluster bootstrap over
problems (3000 draws, fixed seed). Spearman throughout.

    source .venv/bin/activate && python3 -m scripts.analyze_turn1_reasoning [--raw]

Legit = exec=1 & eq=1 after the false-positive correction (scripts/rescore_hacks.py); --raw uses the
uncorrected labels.
"""

import json
import re
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

from scripts import rescore_hacks

ROOT = Path(__file__).resolve().parent.parent
RUNS = ROOT / "outputs/evals/countdown_code--openai--o4-mini"
rng = np.random.default_rng(0)


def load(path):
    with open(path) as f:
        return [json.loads(line) for line in f]


def rank(x):
    x = np.asarray(x, float)
    o = np.argsort(x, kind="mergesort")
    r = np.empty(len(x))
    r[o] = np.arange(len(x))
    for v in np.unique(x):
        m = x == v
        if m.sum() > 1:
            r[m] = r[m].mean()
    return r


def sp(a, b):
    a, b = rank(a), rank(b)
    return np.nan if a.std() == 0 or b.std() == 0 else np.corrcoef(a, b)[0, 1]


def ci(a, b, g=None, B=3000):
    a, b = np.asarray(a), np.asarray(b)
    g = np.arange(len(a)) if g is None else np.asarray(g)
    u = np.unique(g)
    ix = {k: np.where(g == k)[0] for k in u}
    v = []
    for _ in range(B):
        i = np.concatenate([ix[k] for k in rng.choice(u, len(u))])
        v.append(sp(a[i], b[i]))
    v = np.array(v)
    v = v[~np.isnan(v)]
    return f"{sp(a, b):+.3f} [{np.percentile(v, 2.5):+.3f}, {np.percentile(v, 97.5):+.3f}]"


def stated(text):
    t = str(text).split("</think>")[-1]
    m = re.findall(r"(\d+(?:\.\d+)?)\s*%", t) or re.findall(r'"probability"\s*:\s*"?(\d+(?:\.\d+)?)', t)
    if m:
        return float(m[0])
    m = re.search(r"\b(0?\.\d+|1\.0+)\b", t)
    return 100 * float(m.group(1)) if m else None


def resid(y, x):
    return y - np.polyval(np.polyfit(x, y, 1), x)


T = load(ROOT / "outputs/turn1_reasoning/turn1.jsonl")
print(f"replays: {len(T)}, finish_reason: {sorted({t['finish_reason'] for t in T})}")
rows = [(t["example_id"], stated(t["content"]), t["reasoning_tokens"], t["completion_tokens"]) for t in T]
print(f"parsed probability: {sum(r[1] is not None for r in rows)}/{len(rows)}")
rows = [r for r in rows if r[1] is not None]
e = np.array([r[0] for r in rows]); p = np.array([r[1] for r in rows])
rt = np.array([r[2] for r in rows], float)
print(f"turn-1 reasoning tokens: mean {rt.mean():.0f}, median {np.median(rt):.0f}, p90 {np.percentile(rt, 90):.0f}, max {rt.max():.0f}")
print(f"stated p: mean {p.mean():.1f}, 90/95 share {np.mean((p == 90) | (p == 95)):.2f}")

print("\n== rollout level (cluster bootstrap over problems)")
print("reasoning tokens vs stated p, pooled:", ci(rt, p, e))
dr, dp = [], []
for i in np.unique(e):
    m = e == i
    dr += list(rt[m] - rt[m].mean()); dp += list(p[m] - p[m].mean())
print("within-problem deviations:", ci(dr, dp, np.repeat(np.unique(e), [(e == i).sum() for i in np.unique(e)])))

print("\n== by turn-1 reasoning tokens")
for lo, hi in [(0, 500), (500, 1000), (1000, 3000), (3000, 1e12)]:
    m = (rt >= lo) & (rt < hi)
    print(f"[{lo}, {hi:.0f}) n={m.sum()} mean p={p[m].mean():.1f} share<=80={np.mean(p[m] <= 80):.2f}")

nt, nl, cl, cp = defaultdict(list), defaultdict(list), defaultdict(list), defaultdict(list)
LABEL = "raw" if "--raw" in sys.argv else "fixed"  # fixed = false-positive corrected (rescore_hacks.py)
print(f"outcome label: {LABEL}")
for r in load(RUNS / "3fb9e8c3/results.jsonl"):
    nt[r["example_id"]].append(r["token_usage"]["output_tokens"])
for r in rescore_hacks.load("3fb9e8c3"):
    nl[r["example_id"]].append(r[LABEL] == "legit")
for r in load(RUNS / "658b8ecd/results.jsonl"):
    s = stated(next(m for m in r["completion"] if m["role"] == "assistant")["content"])
    if s is not None:
        cp[r["example_id"]].append(s)
for r in rescore_hacks.load("658b8ecd"):
    cl[r["example_id"]].append(r[LABEL] == "legit")

ids = sorted(set(e))
P = np.array([p[e == i].mean() for i in ids]); RT = np.array([rt[e == i].mean() for i in ids])
LRT = np.array([np.log1p(rt[e == i]).mean() for i in ids])
D = np.array([np.mean(nt[i]) for i in ids]); NL = np.array([np.mean(nl[i]) for i in ids])
CL = np.array([np.mean(cl[i]) for i in ids]); P0 = np.array([np.mean(cp[i]) for i in ids])

print(f"\n== problem level (n={len(ids)})")
print("mean turn-1 reasoning vs mean stated p:", ci(RT, P))
print("mean log turn-1 reasoning vs mean stated p:", ci(LRT, P))
print("stated p (replay) vs stated p (original 658b8ecd):", ci(P, P0))
print("turn-1 reasoning vs difficulty (no-ask tokens):", ci(RT, D))
print("stated p vs difficulty:", ci(P, D))
print("turn-1 reasoning vs no-ask legit rate:", ci(RT, NL), "| vs conditioned legit rate:", ci(RT, CL))
print("stated p vs no-ask legit rate:", ci(P, NL), "| vs conditioned legit rate:", ci(P, CL))
print("no-ask tokens vs no-ask legit rate:", ci(D, NL))
rp, rr, rl = rank(P), rank(RT), rank(NL)
print("partial rho(legit, turn-1 reasoning | stated p):", f"{np.corrcoef(resid(rl, rp), resid(rr, rp))[0, 1]:+.3f}")
print("partial rho(legit, stated p | turn-1 reasoning):", f"{np.corrcoef(resid(rl, rr), resid(rp, rr))[0, 1]:+.3f}")

print("\n== difficulty quartiles (no-ask mean tokens): n, turn-1 reasoning, stated p, no-ask legit")
b = np.digitize(D, np.quantile(D, [.25, .5, .75]))
for k in range(4):
    m = b == k
    print(f"Q{k + 1} n={m.sum()} reasoning={RT[m].mean():.0f} (median {np.median(RT[m]):.0f}) p={P[m].mean():.1f} legit={NL[m].mean():.3f}")

print("\n== (1) total output tokens, existing runs (stated p = original 658b8ecd answers)")
tot, sp0 = [], []
for r in load(RUNS / "658b8ecd/results.jsonl"):
    s = stated(next(m for m in r["completion"] if m["role"] == "assistant")["content"])
    if s is not None:
        tot.append(r["token_usage"]["output_tokens"]); sp0.append(s)
print(f"stated p vs total output tokens in 658b8ecd, per rollout (n={len(tot)}):", ci(tot, sp0))
print("per problem, stated p (orig) vs no-ask tokens:", ci(P0, D))
print("per problem, no-ask tokens vs no-ask legit rate:", ci(D, NL))
print("per problem, stated p (orig) vs no-ask legit rate:", ci(P0, NL))
r0, rd, rl0 = rank(P0), rank(D), rank(NL)
print("partial rho(legit, stated p (orig) | no-ask tokens):", f"{np.corrcoef(resid(rl0, rd), resid(r0, rd))[0, 1]:+.3f}")
for k in range(4):
    m = b == k
    print(f"Q{k + 1} no-ask tokens={D[m].mean():.0f} stated p (orig)={P0[m].mean():.1f} no-ask legit={NL[m].mean():.3f}")
