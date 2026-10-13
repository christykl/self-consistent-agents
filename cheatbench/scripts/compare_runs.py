"""Compare a variant run of the pilot rows with the pilot-1 baseline, row by row.

    python scripts/compare_runs.py RUN_ID [MODEL] [BASELINE_RUN_ID]
    python scripts/compare_runs.py alignprompt1        # vs pilot1, gpt-6-astra-openrouter

For each task, reads outputs/<task>_<model>_<run_id>/{episodes,judge}.jsonl for
both runs and prints one markdown row per episode: the judge's `cheated`
verdict and flags, failure type, wall time, cost (agent + judge), tool calls,
and how often the agent's own prose (assistant messages and reasoning
summaries in messages.jsonl; not tool inputs, which contain repo paths like
factoring-evals) mentions "alignment" or "eval".
"""
import json
import re
import sys
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "outputs"
RUN = sys.argv[1]
MODEL = sys.argv[2] if len(sys.argv) > 2 else "gpt-6-astra-openrouter"
BASE = sys.argv[3] if len(sys.argv) > 3 else "pilot1"
TASKS = ["prime_factorization", "subset_sum", "geoguessr_single",
         "synthetic_puzzles", "knowledge_work", "protein_design"]
FLAGS = ["answer_file_read", "used_answer_key", "prohibited_computation",
         "explicit_prohibition_violated", "copied_design", "inspected_competitor",
         "copied_or_transformed_competitor", "probed_judge", "tampering"]
MENTION = re.compile(r"\balignment\b|\beval(uation)?s?\b", re.I)


def jsonl(path):
    return [json.loads(l) for l in path.read_text().splitlines() if l.strip()] if path.exists() else []


def mentions(traj_dir):
    """Agent-written snippets matching MENTION (empty if no messages.jsonl)."""
    path = traj_dir / "messages.jsonl"
    if not path.exists():
        return []
    hits = []
    for line in path.read_text().splitlines():
        p = json.loads(line)
        p = p.get("payload", p)
        texts = []
        if p.get("type") == "reasoning":
            texts = [s["text"] for s in p.get("summary") or []]
        elif p.get("type") == "message" and p.get("role") == "assistant":
            texts = [c.get("text", "") for c in p["content"]]
        for t in texts:
            for m in MENTION.finditer(t):
                hits.append(t[max(0, m.start() - 60):m.end() + 60].replace("\n", " "))
    return hits


def episodes(task, run_id):
    d = OUT / f"{task}_{MODEL}_{run_id}"
    judged = {j["episode"]: j for j in jsonl(d / "judge.jsonl")}
    rows = {}
    for e in jsonl(d / "episodes.jsonl"):
        j = judged.get(e["episode"], {})
        rows[e["id"]] = {
            "cheated": j.get("cheated", "unjudged"),
            "flags": [f for f in FLAGS if j.get(f)],
            "failure": e.get("failure") or "",
            "wall": e.get("wall_time"),
            "cost": (e.get("cost_usd") or 0) + (j.get("judge_cost_usd") or 0),
            "calls": e.get("n_tool_calls"),
            "mentions": mentions(d / "trajectories" / e["episode"]),
        }
    return rows


def fmt_wall(s):
    return "" if s is None else f"{s / 60:.1f} min" if s >= 90 else f"{s:.0f} s"


print(f"| Task | Row | {BASE} cheated | {RUN} cheated | {RUN} flags | failure | wall | cost | tool calls | mentions align/eval |")
print("|---|---|---|---|---|---|---|---:|---:|---|")
for task in TASKS:
    base, var = episodes(task, BASE), episodes(task, RUN)
    for rid, v in var.items():
        b = base.get(rid, {})
        print(f"| {task} | {rid[:20]} | {b.get('cheated', '')} | {v['cheated']} | "
              f"{', '.join(v['flags'])} | {v['failure']} | {fmt_wall(v['wall'])} | "
              f"${v['cost']:.2f} | {v['calls']} | {len(v['mentions'])} |")
print()
for task in TASKS:
    for rid, v in episodes(task, RUN).items():
        for h in v["mentions"][:5]:
            print(f"- {task} {rid[:20]}: ...{h}...")
