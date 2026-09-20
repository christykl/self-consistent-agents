"""Filter Jiayi-Pan/Countdown-Tasks-3to4 to 4-number problems and dump a local JSONL
for vf-eval's `local_file` env-arg. Run once; output is committed to disk for reuse."""
from datasets import load_dataset

OUT_PATH = "data/countdown_4num.jsonl"
N_SAMPLES = 3000
SEED = 42

ds = load_dataset("Jiayi-Pan/Countdown-Tasks-3to4", split="train")
ds4 = ds.filter(lambda ex: len(ex["nums"]) == 4)
ds4 = ds4.shuffle(seed=SEED).select(range(min(N_SAMPLES, len(ds4))))
ds4.to_json(OUT_PATH)
print(f"Wrote {len(ds4)} 4-number examples to {OUT_PATH}")
