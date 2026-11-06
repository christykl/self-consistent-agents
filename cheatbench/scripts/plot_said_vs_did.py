"""What the self-report answer says vs. what the attempts do, on the shared 90 rows.

    python scripts/plot_said_vs_did.py
    # writes docs/figures/said_not_tempted.png and docs/figures/self_report_vs_cheat.png

The answer is the model's `selfreport1` answer for the row ("would you ever be tempted
to cheat?", `tempted` true/false); both self-report settings show this same answer.
- said_not_tempted.png: cheat rate on the rows where the answer said "not tempted", in
  baseline (pilot1, which never saw the answer), in-context self-report (4-turn,
  incontext1) and self-report conditioned (2-turn, selfreportcond1).
- self_report_vs_cheat.png: share of rows answered "tempted" next to the cheat rate in
  each setting. "Tempted" is not a prediction of cheating, so this compares the two
  rates rather than scoring calibration.
Cheated is the judge's `cheated` on the last record per row (scripts/compare_settings.py).
"""
import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.self_report import load_answers  # noqa: E402

OUT = Path(__file__).resolve().parent.parent / "outputs"
TASKS = ["prime_factorization", "subset_sum", "geoguessr_single", "knowledge_work", "protein_design"]
SETTINGS = [("Baseline", "pilot1", "#2a78d6"), ("In-context self-report (4-turn)", "incontext1", "#1baf7a"),
            ("Self-report conditioned (2-turn)", "selfreportcond1", "#eda100")]
MODELS = {"GPT-5": "gpt-5-openrouter", "GPT-6.1 Sol": "gpt-6.1-sol-openrouter",
          "Qwen3.8-27B": "qwen3.8-27b-openrouter", "Gemini 3.8 Flash": "gemini-3.8-flash-vertex",
          "Gemini 4 Argon": "gemini-4-argon-vertex"}


def jsonl(path):
    return [json.loads(l) for l in path.read_text().splitlines() if l.strip()]


def cheated(task, model, run_id):
    """{row id: judged cheated} for the last record of each row."""
    d = OUT / f"{task}_{model}_{run_id}"
    latest = {e["episode"]: e for e in jsonl(d / "episodes.jsonl") if e.get("replicate", 1) == 1}
    judged = {j["episode"]: j for j in jsonl(d / "judge.jsonl")}
    return {e["id"]: judged.get(k, {}).get("cheated") is True for k, e in latest.items()}


# rows[model] = [(tempted, {run: cheated})] over the 90 rows
rows = {}
for name, model in MODELS.items():
    rows[name] = []
    for task in TASKS:
        answers = load_answers(OUT / f"{task}_{model}_selfreport1")
        runs = {run: cheated(task, model, run) for _, run, _ in SETTINGS}
        rows[name] += [(answers[rid].get("tempted") is True, {run: runs[run][rid] for run in runs}) for rid in answers]
    assert len(rows[name]) == 90, (name, len(rows[name]))


def style(ax, ylabel):
    ax.set_xticks(np.arange(len(MODELS)), MODELS.keys())
    ax.set_ylabel(ylabel)
    ax.set_ylim(0, 108)
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="y", color="#e5e4e0", linewidth=0.8)
    ax.set_axisbelow(True)


x = np.arange(len(MODELS))

fig, ax = plt.subplots(figsize=(10, 4.5))
for i, (label, run, color) in enumerate(SETTINGS):
    groups = [[c[run] for t, c in rows[m] if not t] for m in MODELS]
    b = ax.bar(x + (i - 1) * 0.27, [100 * sum(g) / len(g) for g in groups], 0.25, color=color, label=label)
    ax.bar_label(b, labels=[f"{sum(g)}/{len(g)}" for g in groups], fontsize=7, padding=2, color="#52514e")
style(ax, "Cheat rate (%)")
ax.legend(fontsize=8, frameon=False, loc="upper right")
ax.set_title('Cheat rate on rows where the self-report said "not tempted" (labels: cheated / rows)')
fig.tight_layout()
fig.savefig("docs/figures/said_not_tempted.png", dpi=150)

fig, ax = plt.subplots(figsize=(11, 4.5))
bars = [("Self-report: tempted", None, "#e87ba4")] + SETTINGS
for i, (label, run, color) in enumerate(bars):
    k = [sum(t for t, _ in rows[m]) if run is None else sum(c[run] for _, c in rows[m]) for m in MODELS]
    b = ax.bar(x + (i - 1.5) * 0.2, [100 * v / 90 for v in k], 0.18, color=color,
               label=label if run is None else f"Cheated: {label}")
    ax.bar_label(b, labels=k, fontsize=7, padding=2, color="#52514e")
style(ax, "% of 90 rows")
ax.legend(fontsize=8, frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.08), ncol=4)
ax.set_title('Self-reported "tempted" rate vs. actual cheat rate (labels: rows out of 90)')
fig.tight_layout()
fig.savefig("docs/figures/self_report_vs_cheat.png", dpi=150)
