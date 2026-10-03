"""Build eval-only problem files that top every no-ask problem up to 4 rollouts.

Counts existing rollouts per problem (`target|numbers`) across the no-ask runs used by the probe,
then writes one file per number of missing rollouts (r=3 for problems seen once, r=2 for twice).
Problems already at >=4 rollouts are skipped.  Rows are shuffled with a fixed seed so a partial run
is an unbiased sample.

    python scripts/make_topup.py
    vf-eval ... -a '{"local_file": "data/countdown_topup_r3.jsonl", "num_samples": 0, "eval_only": true}' -n <rows> -r 3
"""
import json
import random
from collections import Counter, defaultdict

from probe.labels import load_rollouts

TARGET = 4
SEED = 0

counts = Counter()
problems = {}
for key, numbers, target, _, _ in load_rollouts():
    counts[key] += 1
    problems[key] = (numbers, target)

by_missing = defaultdict(list)
for key, n in counts.items():
    if n < TARGET:
        by_missing[TARGET - n].append(key)

rng = random.Random(SEED)
for missing, keys in sorted(by_missing.items()):
    keys.sort()
    rng.shuffle(keys)
    path = f"data/countdown_topup_r{missing}.jsonl"
    with open(path, "w") as f:
        for key in keys:
            numbers, target = problems[key]
            f.write(json.dumps({"target": target, "nums": numbers}) + "\n")
    print(f"{path}: {len(keys)} problems x r={missing} = {len(keys) * missing} rollouts")
