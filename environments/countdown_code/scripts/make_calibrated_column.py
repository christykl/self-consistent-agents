"""Add `p_true` (per-problem calibrated success %, 5% steps, clamped to 5-95) and `p95` (=95) columns to
data/countdown_4num_hard.jsonl -> data/countdown_4num_hard_cal.jsonl.

p_true = corrected legit rate pooled over the two-turn model-generated baseline on the hard set
(BASE_RUN) and the paired-200 ask-success-probability run 658b8ecd, i.e. the success rate under the
same two-turn setup, from 12 rollouts per problem that are independent of the injected rollouts.

    python scripts/make_calibrated_column.py <BASE_RUN>
"""
import json
import sys
from collections import defaultdict

sys.path.insert(0, "scripts")
from rescore_hacks import load  # noqa: E402

base = sys.argv[1]
wins = defaultdict(lambda: [0, 0])
for run in (base, "658b8ecd"):
    for r in load(run):
        w = wins[r["key"]]
        w[0] += r["fixed"] == "legit"
        w[1] += 1
from probe.labels import problem_key  # noqa: E402

rows = [json.loads(l) for l in open("data/countdown_4num_hard.jsonl")]
with open("data/countdown_4num_hard_cal.jsonl", "w") as f:
    for r in rows:
        k, n = wins[problem_key(r["nums"], r["target"])]
        p = min(95, max(5, 5 * round(100 * k / n / 5)))
        f.write(json.dumps({**r, "p_true": p, "p95": 95}) + "\n")
seen = {}
for r in map(json.loads, open("data/countdown_4num_hard_cal.jsonl")):
    seen[r["paired_id"]] = r["p_true"]
import statistics as st
print(len(seen), "problems; p_true mean", st.mean(seen.values()), sorted(seen.values()))
