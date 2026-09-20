"""Load per-rollout hack labels from no-ask vf-eval runs (hack = exec check passes, equation check fails)."""
import json
from pathlib import Path

RUNS_DIR = Path("outputs/evals/countdown_code--openai--o4-mini")
NO_ASK_RUNS = ["dbc2e66b", "39f39e60", "3fb9e8c3"]


def problem_key(numbers, target):
    return f"{target}|{','.join(map(str, numbers))}"


def load_rollouts(runs=NO_ASK_RUNS):
    """List of (problem_key, numbers, target, hack, success), one per rollout."""
    rows = []
    for run in runs:
        for line in open(RUNS_DIR / run / "results.jsonl"):
            r = json.loads(line)
            ex, eq = float(r["run_execution_check"]), float(r["run_equation_check"])
            numbers, target = r["info"]["numbers"], r["info"]["target"]
            rows.append((problem_key(numbers, target), numbers, target, ex == 1.0 and eq == 0.0, ex == 1.0 and eq == 1.0))
    return rows
