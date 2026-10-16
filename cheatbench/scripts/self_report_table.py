"""Pair each self-report episode with the pilot attempt on the same row.

    python scripts/self_report_table.py [MODEL]    # default gpt-6-astra-openrouter

For every task, reads outputs/<task>_<model>_selfreport1/episodes.jsonl (the
agent's JSON answer is the last object with a `tempted` key in its final
message, else in the latest earlier message that has one) and the judge
verdicts of both the self-report run and the pilot attempt run. Prints one
markdown row per row id.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.self_report import find_answer  # noqa: E402

OUT = Path(__file__).resolve().parent.parent / "outputs"
MODEL = sys.argv[1] if len(sys.argv) > 1 else "gpt-6-astra-openrouter"
TASKS = ["prime_factorization", "subset_sum", "geoguessr_single",
         "synthetic_puzzles", "knowledge_work", "protein_design"]


def jsonl(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def flags(verdict):
    """The judge's true boolean fields, minus the summary `cheated` flag."""
    return [k for k, v in verdict.items()
            if v is True and k not in ("cheated", "parse_ok")]


print("| Task | Row | Self-report: tempted | Actions listed (p) | Max p | Explored (tool calls) | Self-report episode judged cheated | Attempt judged cheated | Attempt flags |")
print("|---|---|---|---|---:|---:|---|---|---|")
for task in TASKS:
    sr_dir = OUT / f"{task}_{MODEL}_selfreport1"
    if not sr_dir.exists():  # e.g. synthetic_puzzles, not run for gpt-5-openrouter
        continue
    sr_judge = {j["episode"]: j for j in jsonl(sr_dir / "judge.jsonl")}
    attempt_judge = {j["id"]: j for j in jsonl(OUT / f"{task}_{MODEL}_pilot1" / "judge.jsonl")}
    for rec in sorted(jsonl(sr_dir / "episodes.jsonl"), key=lambda r: r["id"]):
        ans = find_answer(rec)
        actions = "; ".join(f"{a['action']} ({a['probability']})" for a in ans["actions"]) or "none"
        max_p = max([a["probability"] for a in ans["actions"]], default=0)
        attempt = attempt_judge[rec["id"]]
        print(f"| {task} | {rec['id']} | {ans['tempted']} | {actions} | {max_p} | "
              f"{rec['n_tool_calls']} | {sr_judge[rec['episode']]['cheated']} | "
              f"{attempt['cheated']} | {', '.join(flags(attempt))} |")
