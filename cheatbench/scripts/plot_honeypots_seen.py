"""Honeypot-seen rate vs. eval-awareness setting on the 90 rows (synthetic_puzzles excluded).

Honeypot seen is the cheating judge's `honey_pots_seen` (the agent saw a concrete route to the answer,
whether or not it used it). Episodes without a judge record count as not seen.
"""
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent.parent
TASKS = ["prime_factorization", "subset_sum", "geoguessr_single", "knowledge_work", "protein_design"]
RUNS = ["pilot1", "honeypot1", "alignprompt1", "evalstrict1", "selfreportcond1"]
LABELS = ["Base", "Alignment\nhoneypot", "Alignment\nprompt", "Extreme alignment\nprompt", "Self-report\nconditioned"]
MODELS = {"GPT-5": "gpt-5-openrouter", "GPT-6.1 Sol": "gpt-6.1-sol-openrouter", "Gemini 4 Argon": "gemini-4-argon-vertex"}


def jsonl(path):
    return [json.loads(l) for l in path.read_text().splitlines() if l.strip()]


def seen_rate(model, run):
    """(% of the 90 rows whose judge says honeypot seen, n rows); last record per episode wins."""
    seen = n = 0
    for task in TASKS:
        d = ROOT / "outputs" / f"{task}_{model}_{run}"
        if not d.exists():
            continue
        judged = {j["episode"]: j for j in jsonl(d / "judge.jsonl")} if (d / "judge.jsonl").exists() else {}
        for ep in {e["episode"] for e in jsonl(d / "episodes.jsonl")}:
            n += 1
            seen += judged.get(ep, {}).get("honey_pots_seen") is True
    return 100 * seen / n if n else None, n


for (name, model), color in zip(MODELS.items(), ["#4C78A8", "#E45756", "#54A24B"]):
    rates = []
    for run in RUNS[:1] if "gemini" in model else RUNS:  # Gemini: baseline only
        r, n = seen_rate(model, run)
        if r is not None:
            rates.append(r)
            print(f"{name:15s} {run:16s} n={n:3d} honeypot seen={r:5.1f}%")
    plt.plot(range(min(len(rates), 4)), rates[:4], "o-", label=name, color=color, markersize=8 if len(rates) == 1 else 5)
    if len(rates) == 5:  # self-report conditioned is not part of the awareness progression: star, no connecting line
        plt.plot([4], rates[4:], "*", color=color, markersize=12)
plt.xticks(range(5), LABELS, fontsize=8)
plt.ylabel("Honeypot seen (% of episodes)")
plt.ylim(0, 100)
plt.xlabel("Eval-awareness level (increasing)")
plt.legend()
plt.title("Honeypot seen vs. eval-awareness level")
plt.tight_layout()
plt.savefig(ROOT / "docs/figures/honeypots_seen_vs_awareness.png", dpi=150)
