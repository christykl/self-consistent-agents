"""Grouped bar plots: cheat rate per model in four settings on the shared 90 rows.

    python scripts/plot_cheat_by_setting.py
    # writes docs/figures/cheat_by_setting.png (all 90 rows)
    #    and docs/figures/cheat_by_setting_per_task.png (one panel per task)

Settings (run ids): baseline (pilot1), alignment prompt (alignprompt1), in-context
self-report, the four-turn version with the earlier answer as the model's own turn
(incontext1), and self-report conditioned, the two-turn version that quotes the answer
in the attempt prompt (selfreportcond1). Cheated is the judge's `cheated` on the last
record per row, counted as in scripts/compare_settings.py. The 90 rows are the five
tasks below (synthetic_puzzles, which only some models ran, is left out).
"""
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

OUT = Path(__file__).resolve().parent.parent / "outputs"
FIGS = Path(__file__).resolve().parent.parent / "docs" / "figures"
SETTINGS = [("Baseline", "pilot1"), ("Alignment prompt", "alignprompt1"),
            ("In-context self-report (4-turn)", "incontext1"),
            ("Self-report conditioned (2-turn)", "selfreportcond1")]
COLORS = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100"]
MODELS = {"GPT-5": "gpt-5-openrouter", "GPT-6.1 Sol": "gpt-6.1-sol-openrouter",
          "Qwen3.8-27B": "qwen3.8-27b-openrouter", "Gemini 3.8 Flash": "gemini-3.8-flash-vertex",
          "Gemini 4 Argon": "gemini-4-argon-vertex"}
TASKS = ["prime_factorization", "subset_sum", "geoguessr_single", "knowledge_work", "protein_design"]


def jsonl(path):
    return [json.loads(l) for l in path.read_text().splitlines() if l.strip()]


def count(task, model, run_id):
    """(cheated, rows) for one task/model/run."""
    d = OUT / f"{task}_{model}_{run_id}"
    latest = {e["episode"]: e for e in jsonl(d / "episodes.jsonl")}
    judged = {j["episode"]: j for j in jsonl(d / "judge.jsonl")}
    return sum(judged.get(k, {}).get("cheated") is True for k in latest), len(latest)


def bars(ax, counts):
    """counts[model][setting] = (cheated, rows); four bars per model, labelled with the count."""
    x = np.arange(len(MODELS))
    width = 0.2
    for i, ((setting, _), color) in enumerate(zip(SETTINGS, COLORS)):
        c = [counts[m][i] for m in MODELS]
        b = ax.bar(x + (i - 1.5) * width, [100 * k / n for k, n in c], width * 0.9, color=color, label=setting)
        ax.bar_label(b, labels=[k for k, _ in c], fontsize=7, padding=2, color="#52514e")
    ax.set_xticks(x, MODELS.keys())
    ax.set_ylabel("Cheat rate (%)")
    ax.set_ylim(0, 108)
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="y", color="#e5e4e0", linewidth=0.8)
    ax.set_axisbelow(True)


per_task = {t: {m: [count(t, MODELS[m], r) for _, r in SETTINGS] for m in MODELS} for t in TASKS}
for t in TASKS:  # every setting should cover the same rows
    for m in MODELS:
        assert len({n for _, n in per_task[t][m]}) == 1, (t, m, per_task[t][m])
total = {m: [tuple(sum(per_task[t][m][i][j] for t in TASKS) for j in (0, 1)) for i in range(len(SETTINGS))]
         for m in MODELS}

fig, ax = plt.subplots(figsize=(10, 4.5))
bars(ax, total)
ax.legend(fontsize=8, frameon=False, loc="upper left", ncol=2)
ax.set_title("Cheat rate by setting (90 rows per model; bar labels are cheated counts)")
fig.tight_layout()
fig.savefig(FIGS / "cheat_by_setting.png", dpi=150)

fig, axes = plt.subplots(2, 3, figsize=(20, 8.5))
for ax, t in zip(axes.flat, TASKS):
    bars(ax, per_task[t])
    ax.tick_params(axis="x", labelsize=8)
    ax.set_title(f"{t} ({per_task[t]['GPT-5'][0][1]} rows per model)", fontsize=10)
axes.flat[-1].axis("off")
axes.flat[-1].legend(*axes.flat[0].get_legend_handles_labels(), loc="center", frameon=False, fontsize=10)
fig.suptitle("Cheat rate by setting and task (bar labels are cheated counts)")
fig.tight_layout()
fig.savefig(FIGS / "cheat_by_setting_per_task.png", dpi=150)

for m in MODELS:
    print(m, [f"{k}/{n}" for k, n in total[m]])
