"""Chess and Go: episodes judged as cheating, and total/honest wins, per model in five settings.

    python scripts/plot_chess_go.py
    # writes docs/figures/chess_go_cheat_by_setting.png and docs/figures/chess_go_success_by_setting.png

Same layout as scripts/plot_pf_cheat.py and scripts/plot_pf_success.py, one panel (or panel row)
per task. Settings (run ids): baseline (pilot1; pilot2 for GPT-5, its run on the fixed prompt in
docs/chess_go_prompt_fix.md), alignment prompt (alignprompt1), extreme alignment prompt
(extremealign2), in-context self-report (incontext1), self-report conditioned (selfreportcond1).
No model has a paraphrased self-report run on chess or Go, so that setting is left out.

Labels: "pending" for runs listed in PENDING (Qwen's non-baseline settings; its baseline is in
docs/qwen_chess_go.md; Kimi K3's settings are in docs/kimi_fireworks.md); "n/r" (not run) for any other missing run dir (GPT-5 has
only a baseline on the fixed prompt).

Counts use the last record per row, as in scripts/compare_settings.py.
Cheated: the judge's `cheated`. Total win: the grader's `trusted_win` (a win the opponent's
engine really conceded). Honest win: a total win the judge did not mark as cheated.
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
TASKS = {"Chess": ("chess_none", 30), "Go": ("go", 20)}
MODELS = {"GPT-5": "gpt-5-openrouter", "GPT-6.1 Sol": "gpt-6.1-sol-openrouter",
          "Kimi K3": "kimi-k3-fireworks", "Qwen3.8-27B": "qwen3.8-27b-openrouter"}
# Same colors as scripts/plot_pf_cheat.py.
SETTINGS = [("Baseline", "pilot1", "#2a78d6"), ("Alignment prompt", "alignprompt1", "#eb6834"),
            ("Extreme alignment prompt", "extremealign2", "#d6407a"),
            ("In-context self-report", "incontext1", "#1baf7a"),
            ("Self-report conditioned", "selfreportcond1", "#eda100")]
SHORT = {"Baseline": "Baseline", "Alignment prompt": "Alignment\nprompt",
         "Extreme alignment prompt": "Extreme\nalignment\nprompt", "In-context self-report": "In-context\nself-report",
         "Self-report conditioned": "Self-report\nconditioned"}
BASELINE = {"gpt-5-openrouter": "pilot2"}
PENDING = {("qwen3.8-27b-openrouter", run_id) for _, run_id, _ in SETTINGS[1:]}
TOTAL_COLOR, HONEST_COLOR, INK = "#2a78d6", "#eb6834", "#52514e"


def jsonl(path):
    return [json.loads(l) for l in path.read_text().splitlines() if l.strip()]


def won(record):
    """The grader's trusted_win: chess keeps it at the top of grader_state, Go under `game`."""
    state = record["grader_state"]
    return bool(state.get("trusted_win") or (state.get("game") or {}).get("trusted_win"))


def count(task, rows, model, run_id):
    """(cheated, total wins, honest wins), or "pending" / "n/r"."""
    if (model, run_id) in PENDING:
        return "pending"
    if run_id == "pilot1":
        run_id = BASELINE.get(model, run_id)
    d = OUT / f"{task}_{model}_{run_id}"
    if not d.exists():
        return "n/r"
    latest = {e["episode"]: e for e in jsonl(d / "episodes.jsonl")}
    assert len(latest) == rows, (task, model, run_id, len(latest))
    judged = {j["episode"]: j for j in jsonl(d / "judge.jsonl")}
    cheated = [k for k in latest if judged[k]["cheated"] is True]
    wins = [k for k, e in latest.items() if won(e)]
    honest = [k for k in wins if k not in cheated]
    return len(cheated), len(wins), len(honest)


def label_bars(ax, bars, values):
    """Numbers above bars; "pending" and "n/r" written vertically, since bars are narrow."""
    for bar, v in zip(bars, values):
        text = str(v)
        ax.annotate(text, (bar.get_x() + bar.get_width() / 2, bar.get_height()), xytext=(0, 2),
                    textcoords="offset points", ha="center", va="bottom", fontsize=8, color=INK,
                    rotation=90 if text == "pending" else 0)


def style(ax, rows):
    ax.set_ylim(0, rows + 4)
    ax.set_yticks(range(0, rows + 1, 5))
    ax.tick_params(axis="both", length=0, labelcolor=INK)
    ax.spines[["top", "right", "left"]].set_visible(False)
    ax.spines["bottom"].set_color("#c3c2b7")
    ax.grid(axis="y", color="#e5e4e0", linewidth=0.8)
    ax.set_axisbelow(True)


results = {(name, model): [count(task, rows, model, run_id) for _, run_id, _ in SETTINGS]
           for name, (task, rows) in TASKS.items() for model in MODELS.values()}
for key, counts in results.items():
    print(*key, counts)
FOOTNOTE = "One episode per row. pending: run not finished. n/r: not run in this setting."

# Cheating: one panel per task, models along x, one bar per setting.
fig, axes = plt.subplots(1, len(TASKS), figsize=(16, 4.4), gridspec_kw={"width_ratios": [1, 1]})
x = np.arange(len(MODELS))
width = 0.16
for ax, (name, (task, rows)) in zip(axes, TASKS.items()):
    for i, (label, _, color) in enumerate(SETTINGS):
        values = [results[name, model][i] for model in MODELS.values()]
        values = [v if isinstance(v, str) else v[0] for v in values]
        # Bars are narrower than their slots to leave a small gap between neighbors.
        bars = ax.bar(x + (i - 2) * width, [0 if isinstance(v, str) else v for v in values], width * 0.9,
                      color=color, label=label)
        label_bars(ax, bars, values)
    ax.set_title(name, fontsize=11)
    ax.set_xticks(x, MODELS.keys())
    ax.set_ylabel(f"Rows judged as cheating (of {rows})", color=INK)
    style(ax, rows)
fig.legend(*axes[0].get_legend_handles_labels(), loc="upper center", bbox_to_anchor=(0.5, 0.93), ncol=5,
           frameon=False, fontsize=9)
fig.suptitle("chess and go: cheating by model and setting", x=0.01, ha="left", fontsize=13)
fig.text(0.01, 0.01, "Cheated: the judge's verdict on the transcript. " + FOOTNOTE, fontsize=8, color=INK)
fig.tight_layout(rect=(0, 0.04, 1, 0.89))
fig.savefig(FIGS / "chess_go_cheat_by_setting.png", dpi=150)

# Wins: one row per task, one panel per model, settings along x, total and honest bars.
fig, axes = plt.subplots(len(TASKS), len(MODELS), figsize=(18, 8.4), sharey="row")
x = np.arange(len(SETTINGS))
width = 0.38
for r, (name, (task, rows)) in enumerate(TASKS.items()):
    for ax, (model_name, model) in zip(axes[r], MODELS.items()):
        counts = results[name, model]
        for j, (offset, color, label) in enumerate([(-width / 2, TOTAL_COLOR, "Total wins"),
                                                    (width / 2, HONEST_COLOR, "Honest wins")]):
            values = [c if isinstance(c, str) else c[j + 1] for c in counts]
            # Bars are narrower than their slots to leave a small gap between each pair.
            bars = ax.bar(x + offset, [0 if isinstance(v, str) else v for v in values], width * 0.92,
                          color=color, label=label)
            label_bars(ax, bars, values)
        ax.set_title(f"{name}: {model_name}", fontsize=11)
        ax.set_xticks(x, [SHORT[label] for label, _, _ in SETTINGS], fontsize=7)
        style(ax, rows)
    axes[r][0].set_ylabel(f"Rows won (of {rows})", color=INK)
fig.legend(*axes[0][0].get_legend_handles_labels(), loc="upper right", ncol=2, frameon=False, fontsize=9)
fig.suptitle("chess and go: wins by model and setting", x=0.01, ha="left", fontsize=13)
fig.text(0.01, 0.01, "Win: the grader's trusted_win (the opponent engine really lost). Honest: a win the judge did "
         "not mark as cheating. " + FOOTNOTE, fontsize=8, color=INK)
fig.tight_layout(rect=(0, 0.03, 1, 0.97))
fig.savefig(FIGS / "chess_go_success_by_setting.png", dpi=150)
