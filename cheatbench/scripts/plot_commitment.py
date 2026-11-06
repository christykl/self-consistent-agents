"""Commitment language in the attempt, and cheating with vs. without it: in-context
self-report (4-turn, incontext1) vs. self-report conditioned (2-turn, selfreportcond1).

    python scripts/plot_commitment.py    # writes docs/figures/commitment_language.png

"Commitment language" is in_context_framing.py's `commitment` pattern ("I promised /
committed to ...", "my stated values", ...) anywhere in the attempt's own reasoning or
messages. Left: share of the 90 attempts with it. Right: cheat rate among attempts with
and without it, for the three models that cheat in these settings (GPT-6.1 Sol cheats
once and Gemini 4 Argon never).
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from in_context_framing import PATTERNS, episodes

SETTINGS = [("In-context self-report (4-turn)", "incontext1", "#1baf7a"),
            ("Self-report conditioned (2-turn)", "selfreportcond1", "#eda100")]
MODELS = {"GPT-5": "gpt-5-openrouter", "GPT-6.1 Sol": "gpt-6.1-sol-openrouter",
          "Qwen3.8-27B": "qwen3.8-27b-openrouter", "Gemini 3.8 Flash": "gemini-3.8-flash-vertex",
          "Gemini 4 Argon": "gemini-4-argon-vertex"}
CHEATING = ["GPT-5", "Qwen3.8-27B", "Gemini 3.8 Flash"]

# split[model][run] = (cheated flags of attempts with commitment language, ... without)
split = {}
for name, model in MODELS.items():
    split[name] = {}
    for _, run, _ in SETTINGS:
        E = episodes(model, run)
        has = [any(PATTERNS["commitment"].search(t) for t in w) for _, w in E]
        split[name][run] = ([c for (c, _), h in zip(E, has) if h], [c for (c, _), h in zip(E, has) if not h])


def style(ax):
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="y", color="#e5e4e0", linewidth=0.8)
    ax.set_axisbelow(True)
    ax.set_ylim(0, 108)


fig, (left, right) = plt.subplots(1, 2, figsize=(15, 4.8), gridspec_kw={"width_ratios": [5, 4]})

x = np.arange(len(MODELS))
for i, (label, run, color) in enumerate(SETTINGS):
    with_, without = zip(*(split[m][run] for m in MODELS))
    n = [len(a) + len(b) for a, b in zip(with_, without)]
    b = left.bar(x + (i - 0.5) * 0.36, [100 * len(a) / k for a, k in zip(with_, n)], 0.33, color=color, label=label)
    left.bar_label(b, labels=[f"{len(a)}/{k}" for a, k in zip(with_, n)], fontsize=7, padding=2, color="#52514e")
left.set_xticks(x, MODELS.keys(), fontsize=8)
left.set_ylabel("Attempts with commitment language (%)")
left.set_title("How often the attempt uses commitment language", fontsize=10)
left.legend(fontsize=8, frameon=False, loc="upper left")
style(left)

x = np.arange(len(CHEATING))
offsets = [-1.5, -0.5, 0.5, 1.5]
for k, ((label, run, color), (part, hatch)) in enumerate(
        [(s, p) for s in SETTINGS for p in ((0, None), (1, "//"))]):
    groups = [split[m][run][part] for m in CHEATING]
    b = right.bar(x + offsets[k] * 0.2, [100 * sum(g) / len(g) if g else 0 for g in groups], 0.18,
                  color=color if hatch is None else "white", edgecolor=color, hatch=hatch, linewidth=1.2,
                  label=f"{label.split(' (')[1][:-1]}, {'with' if part == 0 else 'without'}")
    right.bar_label(b, labels=[f"{sum(g)}/{len(g)}" for g in groups], fontsize=7, padding=2, color="#52514e")
right.set_xticks(x, CHEATING, fontsize=8)
right.set_ylabel("Cheat rate (%)")
right.set_title("Cheat rate with vs. without commitment language (labels: cheated / attempts)", fontsize=10)
right.legend(fontsize=8, frameon=False, loc="upper left", ncol=2)
style(right)

fig.tight_layout()
fig.savefig("docs/figures/commitment_language.png", dpi=150)
