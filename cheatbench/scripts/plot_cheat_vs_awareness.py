"""Cheat rate vs. eval-awareness setting on the shared 90 rows (numbers from docs/report_gpt5_five_settings.md,
docs/report_gemini_five_settings.md, docs/report_gemini_flash_five_settings.md and docs/report_qwen_five_settings.md;
cheated counts out of 90)."""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

SETTINGS = ["Base", "Alignment\nhoneypot", "Alignment\nprompt", "Extreme alignment\nprompt", "Self-report\nconditioned"]
CHEATED = {  # base, honeypot, alignprompt, evalstrict, selfreportcond
    "GPT-5": [58, 54, 55, 1, 14],
    "GPT-6.1 Sol": [66, 48, 40, 0, 0],
    "Gemini 4 Argon": [7, 3, 1, 0, 0],
    "Gemini 3.8 Flash": [90, 90, 67, 0, 10],
    "Qwen3.8-27B": [87, 84, 79, 4, 24],
}
for (name, c), color in zip(CHEATED.items(), ["#4C78A8", "#E45756", "#54A24B", "#F58518", "#B279A2"]):
    y = [None if x is None else 100 * x / 90 for x in c]
    pts = [(i, v) for i, v in enumerate(y[:4]) if v is not None]
    plt.plot(*zip(*pts), "o-", label=name, color=color, markersize=8 if len(pts) == 1 else 5)
    if y[4] is not None:  # self-report conditioned is not part of the awareness progression: star, no connecting line
        plt.plot([4], [y[4]], "*", color=color, markersize=12)
plt.xticks(range(5), SETTINGS, fontsize=8)
plt.ylabel("Cheat rate (%)")
plt.ylim(0, 100)
plt.xlabel("Eval-awareness level (increasing)")
plt.legend(loc="center right", fontsize=8)
plt.title("Cheat rate vs. eval-awareness level")
plt.tight_layout()
plt.savefig("docs/figures/cheat_vs_awareness.png", dpi=150)
