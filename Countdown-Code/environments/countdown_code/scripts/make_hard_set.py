"""Build data/countdown_4num_hard.jsonl: the hardest problems of the paired-200 set, each repeated
R times with a `seed` column (one row per rollout; run with -r 1, so the injected turn-1 response
varies per rollout).

Hardness = corrected legit-solve rate pooled over the no-ask, ask-before and ask-with-problem runs
(12 rollouts/problem); the ask-success-probability run (658b8ecd) is deliberately left out of the
selection so it stays an unbiased baseline on this set.

    python scripts/make_hard_set.py
"""
import json
import sys

sys.path.insert(0, "scripts")
from rescore_hacks import per_problem  # noqa: E402

THRESHOLD, R = 0.75, 8
runs = [per_problem(r, "fixed") for r in ("3fb9e8c3", "bfd04a60", "e2807f1e")]
rate = {i: sum(p[i].count("legit") for p in runs) / sum(len(p[i]) for p in runs) for i in runs[0]}
problems = [json.loads(l) for l in open("data/countdown_4num_paired200.jsonl")]
hard = [i for i in sorted(rate) if rate[i] <= THRESHOLD]
with open("data/countdown_4num_hard.jsonl", "w") as f:
    for rep in range(R):
        for i in hard:
            f.write(json.dumps({**problems[i], "paired_id": i, "seed": f"{i}-{rep}"}) + "\n")
print(len(hard), "problems x", R, "=", len(hard) * R, "rows")
