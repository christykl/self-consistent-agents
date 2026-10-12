"""Build a fixed 200-problem, 5-number set for paired comparisons, sampled with a
fixed seed from data/countdown_5num.jsonl (which is in generation order)."""
import json
import random

IN_PATH = "data/countdown_5num.jsonl"
OUT_PATH = "data/countdown_5num_paired200.jsonl"
N_SAMPLES = 200
SEED = 555

with open(IN_PATH) as f:
    rows = [json.loads(line) for line in f if line.strip()]
sample = random.Random(SEED).sample(rows, N_SAMPLES)
with open(OUT_PATH, "w") as f:
    for r in sample:
        f.write(json.dumps(r) + "\n")
print(f"Wrote {len(sample)} fixed 5-number examples to {OUT_PATH}")
