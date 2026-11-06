"""Mean reasoning tokens per episode vs. eval-awareness setting, on the 90 rows (synthetic_puzzles excluded).

Codex (GPT-5, Sol): sum of `reasoning_output_tokens` over the per-response `token_usage_record`s.
Gemini CLI: sum of `tokens.thoughts` over session records (deduplicated by record id).
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


def reasoning_tokens(model, traj):
    path = traj / "messages.jsonl"
    if not path.exists():
        return 0
    seen, total = set(), 0
    for line in path.read_text().splitlines():
        o = json.loads(line)
        if "gemini" in model:
            msgs = o["$set"].get("messages", []) if "$set" in o else [o]
            for m in msgs:
                if m.get("type") == "gemini" and m["id"] not in seen:
                    seen.add(m["id"]); total += (m.get("tokens") or {}).get("thoughts", 0)
        elif o.get("type") == "token_usage_record":
            rid = o["payload"]["response_id"]
            if rid not in seen:
                seen.add(rid); total += o["payload"]["usage"]["reasoning_output_tokens"]
    return total


def episodes(model, run):
    """{row id: reasoning tokens} for the 90 rows (last record per row wins)."""
    out = {}
    for task in TASKS:
        d = ROOT / "outputs" / f"{task}_{model}_{run}"
        if not d.exists():
            continue
        for line in (d / "episodes.jsonl").read_text().splitlines():
            e = json.loads(line)
            out[e["id"]] = reasoning_tokens(model, d / "trajectories" / e["episode"])
    return out


for (name, model), color in zip(MODELS.items(), ["#4C78A8", "#E45756", "#54A24B"]):
    means = []
    for run in RUNS[:1] if "gemini" in model else RUNS:  # Gemini: baseline only
        t = episodes(model, run)
        if t:
            means.append(sum(t.values()) / len(t))
            print(f"{name:15s} {run:16s} n={len(t):3d} mean reasoning tokens={means[-1]:8.0f}")
    plt.plot(range(min(len(means), 4)), means[:4], "o-", label=name, color=color, markersize=8 if len(means) == 1 else 5)
    if len(means) == 5:  # self-report conditioned is not part of the awareness progression: star, no connecting line
        plt.plot([4], means[4:], "*", color=color, markersize=12)
plt.xticks(range(5), LABELS, fontsize=8)
plt.ylabel("Mean reasoning tokens per episode")
plt.xlabel("Eval-awareness level (increasing)")
plt.legend()
plt.title("Reasoning tokens vs. eval-awareness level")
plt.tight_layout()
plt.savefig(ROOT / "docs/figures/reasoning_tokens_vs_awareness.png", dpi=150)
