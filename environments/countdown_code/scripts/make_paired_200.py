"""Build a fixed 200-problem, 4-number set for the paired ask-before vs. no-ask
comparison. Sampled independently (different seed) from the pool used for
data/countdown_4num.jsonl, so it doesn't overlap with earlier calibration runs."""
from datasets import load_dataset

OUT_PATH = "data/countdown_4num_paired200.jsonl"
N_SAMPLES = 200
SEED = 777

ds = load_dataset("Jiayi-Pan/Countdown-Tasks-3to4", split="train")
ds4 = ds.filter(lambda ex: len(ex["nums"]) == 4)
ds4 = ds4.shuffle(seed=SEED).select(range(N_SAMPLES))
ds4.to_json(OUT_PATH)
print(f"Wrote {len(ds4)} fixed 4-number examples to {OUT_PATH}")
