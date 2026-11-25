"""prime_factorization: episodes judged as cheating, per model, in five settings.

    python scripts/plot_pf_cheat.py
    # writes docs/figures/prime_factorization_cheat_by_setting.png

Settings (run ids): baseline (pilot1), alignment prompt (alignprompt1), in-context self-report
(incontext1), self-report conditioned (selfreportcond1), paraphrased self-report (selfreportpara1).
Cheated is the judge's `cheated` on the last record per row, as in scripts/compare_settings.py.
"""
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "outputs"
FIGS = ROOT / "docs" / "figures"
TASK = "prime_factorization"
ROWS = 20
MODELS = {"GPT-5": "gpt-5-openrouter", "GPT-6.1 Sol": "gpt-6.1-sol-openrouter",
          "Gemini 3.8 Flash": "gemini-3.8-flash-vertex", "Gemini 4 Argon": "gemini-4-argon-vertex",
          "Qwen3.8-27B": "qwen3.8-27b-openrouter"}
# Same colors as scripts/plot_cheat_by_setting.py and scripts/plot_setting_diagrams.py.
SETTINGS = [("Baseline", "pilot1", "#2a78d6"), ("Alignment prompt", "alignprompt1", "#eb6834"),
            ("In-context self-report", "incontext1", "#1baf7a"),
            ("Self-report conditioned", "selfreportcond1", "#eda100"),
            ("Paraphrased self-report", "selfreportpara1", "#8a5fd1")]
INK = "#52514e"


def jsonl(path):
    return [json.loads(l) for l in path.read_text().splitlines() if l.strip()]


def cheated(model, run_id):
    d = OUT / f"{TASK}_{model}_{run_id}"
    latest = {e["episode"]: e for e in jsonl(d / "episodes.jsonl")}
    assert len(latest) == ROWS, (model, run_id, len(latest))
    judged = {j["episode"]: j for j in jsonl(d / "judge.jsonl")}
    return sum(judged[k]["cheated"] is True for k in latest)


fig, ax = plt.subplots(figsize=(11, 4.2))
x = np.arange(len(MODELS))
width = 0.16
for i, (label, run_id, color) in enumerate(SETTINGS):
    counts = [cheated(model, run_id) for model in MODELS.values()]
    print(label, counts)
    # Bars are narrower than their slots to leave a small gap between neighbors.
    bars = ax.bar(x + (i - 2) * width, counts, width * 0.9, color=color, label=label)
    ax.bar_label(bars, fontsize=8, padding=2, color=INK)
ax.set_xticks(x, MODELS.keys())
ax.set_ylabel(f"Rows judged as cheating (of {ROWS})", color=INK)
ax.set_ylim(0, ROWS + 2)
ax.set_yticks(range(0, ROWS + 1, 5))
ax.tick_params(axis="both", length=0, labelcolor=INK)
ax.spines[["top", "right", "left"]].set_visible(False)
ax.spines["bottom"].set_color("#c3c2b7")
ax.grid(axis="y", color="#e5e4e0", linewidth=0.8)
ax.set_axisbelow(True)
fig.legend(loc="upper center", bbox_to_anchor=(0.5, 0.93), ncol=5, frameon=False, fontsize=9)
fig.suptitle(f"{TASK}: cheating by model and setting", x=0.01, ha="left", fontsize=13)
fig.text(0.01, 0.01, "Cheated: the judge's verdict on the transcript. One episode per row.", fontsize=8, color=INK)
fig.tight_layout(rect=(0, 0.04, 1, 0.89))
fig.savefig(FIGS / "prime_factorization_cheat_by_setting.png", dpi=150)
