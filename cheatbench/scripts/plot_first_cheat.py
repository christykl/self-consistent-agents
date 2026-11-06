"""When cheating attempts first get at the planted answer: baseline vs. in-context
self-report (4-turn) vs. self-report conditioned (2-turn).

    python scripts/plot_first_cheat.py    # writes docs/figures/first_cheat_timing.png

One dot per cheated episode in which scripts/first_cheat.py finds the answer access
(math-task cheats by prohibited computation have no access and are not shown; the
column title gives how many cheats are shown). Top: index of the tool call that first
gets at the answer (0 = the attempt's first call). Bottom: rejected submissions before
it (symlog scale: linear up to 2, logarithmic above). Black bars are medians. Marker shape is the task. Only the three
models that cheat in the self-report settings are shown.
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from first_cheat import TASKS, episodes

SETTINGS = [("Baseline", "pilot1", "#2a78d6"), ("4-turn", "incontext1", "#1baf7a"),
            ("2-turn", "selfreportcond1", "#eda100")]
MODELS = {"GPT-5": "gpt-5-openrouter", "Qwen3.8-27B": "qwen3.8-27b-openrouter",
          "Gemini 3.8 Flash": "gemini-3.8-flash-vertex"}
MARKERS = dict(zip(TASKS, ["o", "s", "^", "D", "P"]))

data = {(m, run): episodes(model, run) for m, model in MODELS.items() for _, run, _ in SETTINGS}

fig, axes = plt.subplots(2, len(MODELS), figsize=(15, 8), sharey="row")
rng = np.random.default_rng(0)
for col, m in enumerate(MODELS):
    shown = []
    for row, (what, ylabel) in enumerate([(0, "Tool call of first answer access"),
                                          (1, "Rejected submissions before it")]):
        ax = axes[row, col]
        for i, (_, run, color) in enumerate(SETTINGS):
            E = [r for r in data[m, run] if r["cheated"] and r["access"]]
            if row == 0:
                shown.append(f"{len(E)}/{sum(r['cheated'] for r in data[m, run])}")
            for task in TASKS:
                y = [r["access"][what] for r in E if r["task"] == task]
                ax.scatter(i + rng.uniform(-0.25, 0.25, len(y)), y, s=22, marker=MARKERS[task],
                           color=color, alpha=0.75, linewidths=0)
            if E:
                med = np.median([r["access"][what] for r in E])
                ax.plot([i - 0.32, i + 0.32], [med, med], color="black", linewidth=2)
        ax.set_xticks(range(len(SETTINGS)), [s[0] for s in SETTINGS])
        if row == 1:
            ax.set_yscale("symlog", linthresh=2)
            ax.set_yticks([0, 1, 2, 5, 10, 20, 50, 100], ["0", "1", "2", "5", "10", "20", "50", "100"])
        ax.spines[["top", "right"]].set_visible(False)
        ax.grid(axis="y", color="#e5e4e0", linewidth=0.8)
        ax.set_axisbelow(True)
        if col == 0:
            ax.set_ylabel(ylabel)
    axes[0, col].set_title(f"{m}\ncheats shown (baseline / 4-turn / 2-turn): {' / '.join(shown)}", fontsize=10)

handles = [plt.Line2D([], [], marker=MARKERS[t], linestyle="", color="#52514e", label=t) for t in TASKS]
handles.append(plt.Line2D([], [], color="black", linewidth=2, label="median"))
fig.legend(handles=handles, loc="lower center", ncol=len(handles), frameon=False, fontsize=9)
fig.suptitle("When cheating episodes first get at the planted answer")
fig.tight_layout(rect=(0, 0.04, 1, 1))
fig.savefig("docs/figures/first_cheat_timing.png", dpi=150)

for m in MODELS:  # medians, for the doc
    for label, run, _ in SETTINGS:
        E = [r for r in data[m, run] if r["cheated"] and r["access"]]
        if E:
            print(m, label, len(E), "median call", np.median([r["access"][0] for r in E]),
                  "median rejections", np.median([r["access"][1] for r in E]),
                  "zero rejections", sum(r["access"][1] == 0 for r in E))
