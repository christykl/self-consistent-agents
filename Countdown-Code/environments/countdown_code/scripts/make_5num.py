"""Generate 5-number Countdown problems for vf-eval's `local_file` env-arg. Jiayi-Pan/Countdown-Tasks-3to4
has no 5-number problems, so we match its 4-number distribution instead: numbers uniform in [1, 99]
(repeats allowed), target uniform in [10, 100], and keep only problems that have a solution. Rows are
written in generation order, so any prefix is an unbiased sample. Run once; output is committed to disk for reuse."""
import json
import random
from fractions import Fraction

OUT_PATH = "data/countdown_5num.jsonl"
N_SAMPLES = 1000
N_NUMS = 5
SEED = 5


def solvable(values, target):
    """True if some +,-,*,/ expression using every value exactly once equals target (exact arithmetic)."""
    if len(values) == 1:
        return values[0] == target
    for i in range(len(values)):
        for j in range(i + 1, len(values)):
            a, b = values[i], values[j]
            rest = values[:i] + values[i + 1:j] + values[j + 1:]
            candidates = {a + b, a - b, b - a, a * b}
            if b != 0:
                candidates.add(a / b)
            if a != 0:
                candidates.add(b / a)
            if any(solvable(rest + [c], target) for c in candidates):
                return True
    return False


rng = random.Random(SEED)
rows, seen, tried = [], set(), 0
while len(rows) < N_SAMPLES:
    tried += 1
    nums = [rng.randint(1, 99) for _ in range(N_NUMS)]
    target = rng.randint(10, 100)
    key = (target, tuple(sorted(nums)))
    if key in seen or not solvable([Fraction(n) for n in nums], Fraction(target)):
        continue
    seen.add(key)
    rows.append({"target": target, "nums": nums})

with open(OUT_PATH, "w") as f:
    for row in rows:
        f.write(json.dumps(row) + "\n")
print(f"Wrote {len(rows)} {N_NUMS}-number examples to {OUT_PATH} ({tried - len(rows)} of {tried} candidates rejected)")
