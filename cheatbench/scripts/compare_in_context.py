"""In-context self-report (incontext1) vs. self-report conditioned (selfreportcond1)
vs. baseline (pilot1), row by row, for each model.

    python scripts/compare_in_context.py [MODEL ...]    # default: the five sweep models

Both self-report settings show the same `selfreport1` answer for the row
(docs/self_report_in_context.md); they differ only in whether it is quoted in the
user prompt (selfreportcond1) or is the model's own earlier turn (incontext1).
Cheated is the judge's `cheated`; success is the task's grader (compare_settings.py).
A row counts only if all three settings have a final record (the last one per row)
with a judge verdict, so every comparison is over the same rows.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.self_report import load_answers  # noqa: E402
from compare_settings import OUT, jsonl, success  # noqa: E402

MODELS = sys.argv[1:] or ["gpt-5-openrouter", "gpt-6.1-sol-openrouter", "qwen3.8-27b-openrouter",
                          "gemini-3.8-flash-vertex", "gemini-4-argon-vertex"]
TASKS = ["prime_factorization", "subset_sum", "geoguessr_single", "knowledge_work", "protein_design"]
RUNS = ["pilot1", "selfreportcond1", "incontext1"]


def outcomes(task, model, run_id):
    """{row id: {cheated, success, seen, timeout}} for rows with a final record and a verdict."""
    d = OUT / f"{task}_{model}_{run_id}"
    latest = {e["episode"]: e for e in jsonl(d / "episodes.jsonl")}
    judged = {j["episode"]: j for j in jsonl(d / "judge.jsonl") if j.get("parse_ok")}
    return {e["id"]: {"cheated": judged[k].get("cheated") is True,
                      "success": bool(success(task, e, d / "trajectories" / k)),
                      "seen": judged[k].get("honey_pots_seen") is True,
                      "timeout": e.get("failure") == "timeout"}
            for k, e in latest.items() if k in judged and e.get("replicate", 1) == 1}


rows = []  # one dict per (model, task, row id) present in all three settings
for model in MODELS:
    for task in TASKS:
        answers = load_answers(OUT / f"{task}_{model}_selfreport1")
        per_run = {r: outcomes(task, model, r) for r in RUNS}
        for rid in sorted(set.intersection(*(set(v) for v in per_run.values()))):
            rows.append({"model": model, "task": task, "id": rid,
                         "tempted": answers[rid].get("tempted") is True,
                         **{r: per_run[r][rid] for r in RUNS}})


def frac(sel, run, key):
    return f"{sum(r[run][key] for r in sel)}/{len(sel)}"


print("## Totals per model (rows present in all three settings)\n")
print("| Model | Rows | Cheated: baseline | Cheated: self-report cond. | Cheated: in-context "
      "| Success: baseline | Success: cond. | Success: in-context "
      "| Honeypot seen: cond. | Honeypot seen: in-context | Timed out: cond. | Timed out: in-context |")
print("|---|---:|" + ":-:|" * 10)
for model in MODELS:
    sel = [r for r in rows if r["model"] == model]
    print(f"| {model} | {len(sel)} | " + " | ".join(
        [frac(sel, run, "cheated") for run in RUNS] + [frac(sel, run, "success") for run in RUNS]
        + [frac(sel, run, k) for k in ("seen", "timeout") for run in RUNS[1:]]) + " |")

print("\n## Cheated per task (baseline / self-report cond. / in-context)\n")
print("| Model | " + " | ".join(TASKS) + " |")
print("|---|" + ":-:|" * len(TASKS))
for model in MODELS:
    cells = []
    for task in TASKS:
        sel = [r for r in rows if r["model"] == model and r["task"] == task]
        cells.append(" / ".join(str(sum(r[run]["cheated"] for r in sel)) for run in RUNS) + f" ({len(sel)})")
    print(f"| {model} | " + " | ".join(cells) + " |")

print("\n## Paired: self-report cond. -> in-context, cheated\n")
print("| Model | Both | Cond. only | In-context only | Neither |")
print("|---|:-:|:-:|:-:|:-:|")
for model in MODELS:
    sel = [r for r in rows if r["model"] == model]
    c = lambda a, b: sum(r["selfreportcond1"]["cheated"] == a and r["incontext1"]["cheated"] == b for r in sel)
    print(f"| {model} | {c(True, True)} | {c(True, False)} | {c(False, True)} | {c(False, False)} |")

print("\n## By self-report answer (cheated: baseline / cond. / in-context)\n")
print("| Model | Said tempted: rows | cheated | Said not tempted: rows | cheated |")
print("|---|---:|:-:|---:|:-:|")
for model in MODELS:
    cells = []
    for tempted in (True, False):
        sel = [r for r in rows if r["model"] == model and r["tempted"] == tempted]
        cells += [str(len(sel)), " / ".join(str(sum(r[run]["cheated"] for r in sel)) for run in RUNS)]
    print(f"| {model} | " + " | ".join(cells) + " |")
