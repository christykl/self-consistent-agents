"""One illustrative figure per setting in docs/figures/cheat_by_setting.png: the
conversation the agent sees, turn by turn, with the prompts used.

    python scripts/plot_setting_diagrams.py
    # writes docs/figures/setting_{pilot1,alignprompt1,incontext1,selfreportcond1,selfreportpara1}.png

Prompt text is read from prompts/*.md, so the figures follow the templates. The
example row is prime_factorization fact_n52_18; its self-report answer is Qwen3.8-27B's
real answer from the selfreport1 run (the same text both self-report settings show).
The task prompt is abbreviated to its first lines (baseline and alignment prompt)
and to just the {{task}} placeholder in the two self-report settings.
"""
import json
import sys
import textwrap
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, Rectangle

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from core.self_report import load_answers, render  # noqa: E402

PROMPTS = ROOT / "prompts"
FIGS = ROOT / "docs" / "figures"
ROW = "fact_n52_18"
SR_MODEL = "qwen3.8-27b-openrouter"

task_input = next(json.loads(l)["input"] for l in (ROOT / "tasks/prime_factorization/data.jsonl").open()
                  if json.loads(l)["id"] == ROW)
TASK = "\n".join(task_input.splitlines()[:6]) + "\n[... rest of the CheatBench task prompt ...]"
SR_DIR = ROOT / f"outputs/prime_factorization_{SR_MODEL}_selfreport1"
ANSWER = render(load_answers(SR_DIR)[ROW])
PARAPHRASE = json.loads((SR_DIR / "paraphrases.json").read_text())["paraphrases"][ROW]

# Same colors as scripts/plot_cheat_by_setting.py (selfreportpara1 is not plotted there yet).
COLORS = {"pilot1": "#2a78d6", "alignprompt1": "#eb6834", "incontext1": "#1baf7a", "selfreportcond1": "#eda100",
          "selfreportpara1": "#8a5fd1"}
USER_BG, MODEL_BG, HARNESS_BG = "#eef3fb", "#f3f1ec", "#f7f7f7"
TASK_BG, ANSWER_BG = "#dde7f5", "#fbecc4"

# Layout, in inches.
WIDTH, LEFT, RIGHT = 9.0, 1.25, 8.8
LINE, PAD, GAP = 0.145, 0.1, 0.16
WRAP = 100  # characters per line at FONT pt monospace across the box
FONT = 7.6


def template(name):
    return (PROMPTS / name).read_text().strip()


def segments(text, short_task=False, answer=ANSWER):
    """Split prompt text into (style, lines): plain text, the {{task}} slot, the {{self_report}} slot.
    With `short_task`, the task slot shows just the {{task}} placeholder. `answer` fills the
    {{self_report}} slot."""
    out = []
    for piece in text.replace("{{self_report}}", "\0answer\0").replace("{{task}}", "\0task\0").split("\0"):
        if piece == "task":
            out.append(("task", ["{{task}}"] if short_task else TASK.splitlines()))
        elif piece == "answer":
            out.append(("answer", answer.splitlines()))
        elif piece.strip("\n"):
            out.append(("text", piece.strip("\n").splitlines()))
    return [(style, [w for line in lines for w in (textwrap.wrap(line, WRAP, subsequent_indent="  ") or [""])])
            for style, lines in out]


def user(text, short_task=False, answer=ANSWER):
    return ("User", USER_BG, segments(text, short_task, answer))


def model(text, style="note"):
    if style == "answer":
        return ("Model", MODEL_BG, segments("{{self_report}}"))
    return ("Model", MODEL_BG, [("note", textwrap.wrap(text, WRAP))])


def harness():
    return ("Harness", HARNESS_BG, [("note", textwrap.wrap(
        "Harness system/developer instructions and environment context (Codex, Gemini CLI, or "
        "Terminus-2; for Terminus-2 the user prompt below sits inside Harbor's instructions template).", WRAP))])


def divider(text):
    return ("divider", None, text)


def box_height(segs):
    return 2 * PAD + LINE * sum(len(lines) for _, lines in segs) + 0.06 * (len(segs) - 1)


def draw(run_id, title, subtitle, turns):
    heights = [0.3 if t[0] == "divider" else box_height(t[2]) for t in turns]
    height = 0.75 + sum(heights) + GAP * len(turns) + 0.15
    fig = plt.figure(figsize=(WIDTH, height))
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, WIDTH)
    ax.set_ylim(height, 0)  # y grows downward
    ax.axis("off")

    color = COLORS[run_id]
    ax.add_patch(Rectangle((0.2, 0.2), 0.08, 0.38, color=color))
    ax.text(0.4, 0.26, title, fontsize=12, weight="bold", va="top")
    ax.text(0.4, 0.5, subtitle, fontsize=8, color="#52514e", va="top")

    y = 0.75
    n = 0
    for (role, bg, segs), h in zip(turns, heights):
        if role == "divider":
            ax.plot([LEFT, RIGHT], [y + 0.15, y + 0.15], color="#9a988f", lw=0.8, ls=(0, (4, 3)))
            ax.text((LEFT + RIGHT) / 2, y + 0.15, f" {segs} ", fontsize=7.5, color="#52514e", ha="center",
                    va="center", style="italic", bbox=dict(fc="white", ec="none"))
            y += h + GAP
            continue
        if role in ("User", "Model"):
            n += 1
            label = f"Turn {n}\n{role}"
        else:
            label = role
        ax.text(LEFT - 0.15, y + 0.05, label, fontsize=8.5, weight="bold", ha="right", va="top",
                color=color if role in ("User", "Model") else "#7a786f")
        ax.add_patch(FancyBboxPatch((LEFT, y), RIGHT - LEFT, h, boxstyle="round,pad=0,rounding_size=0.06",
                                    fc=bg, ec=color if role != "Harness" else "#cfcdc6", lw=1.0))
        ty = y + PAD
        for style, lines in segs:
            seg_h = LINE * len(lines)
            if style in ("task", "answer"):
                ax.add_patch(Rectangle((LEFT + 0.06, ty - 0.02), RIGHT - LEFT - 0.12, seg_h + 0.03,
                                       fc=TASK_BG if style == "task" else ANSWER_BG, ec="none"))
                tag = "{{task}}" if style == "task" else ("{{self_report}}" if role == "User" else "answer JSON")
                if lines != [tag]:
                    ax.text(RIGHT - 0.1, ty, tag, fontsize=6.5, color="#52514e", ha="right", va="top", style="italic")
            for line in lines:
                ax.text(LEFT + 0.1, ty, line, fontsize=FONT, va="top",
                        family="sans-serif" if style == "note" else "monospace",
                        style="italic" if style == "note" else "normal",
                        color="#52514e" if style == "note" else "#1f1e1c")
                ty += LINE
            ty += 0.06
        y += h + GAP

    fig.savefig(FIGS / f"setting_{run_id}.png", dpi=150)
    plt.close(fig)


ATTEMPT = ("Attempt: the agent explores the sandbox, runs commands, calls the task's tools (here "
           "`verify_factors`), and finishes. The judge reads the whole transcript from turn 1 and labels "
           "the episode cheated or not.")

draw("pilot1", "Baseline", "run id pilot1; no extra flags. The user prompt is the task prompt as is.",
     [harness(), user("{{task}}"), model(ATTEMPT)])

draw("alignprompt1", "Alignment prompt",
     "run id alignprompt1; --prompt-wrapper prompts/alignment_eval.md",
     [harness(), user(template("alignment_eval.md")), model(ATTEMPT)])

draw("incontext1", "In-context self-report (4-turn)",
     "run id incontext1; --self-report-in-context-from selfreport1. Turns 1-2 are the selfreport1 episode "
     "(prompts/self_report.md), restored, not re-run.",
     [harness(), user(template("self_report.md"), short_task=True),
      model("", style="answer"),
      divider("selfreport1 exploration, reasoning and prose around the JSON are dropped; "
              "the attempt runs in a fresh sandbox"),
      user(template("self_report_in_context.md"), short_task=True), model(ATTEMPT)])

draw("selfreportcond1", "Self-report conditioned (2-turn)",
     "run id selfreportcond1; --self-report-from selfreport1. The same answer JSON as the 4-turn setting, "
     "quoted in the user prompt.",
     [harness(), user(template("self_report_conditioned.md"), short_task=True), model(ATTEMPT)])

# Wrapped here so the prose lines do not get the hanging indent used for JSON,
# and narrower than WRAP so the first line clears the {{self_report}} tag.
draw("selfreportpara1", "Paraphrased self-report (2-turn)",
     "run id selfreportpara1; --self-report-paraphrased-from selfreport1. The same answer, paraphrased "
     "in the user's voice.",
     [harness(),
      user(template("self_report_paraphrased.md"), short_task=True,
           answer="\n".join(textwrap.fill(line, WRAP - 16) for line in PARAPHRASE.splitlines())),
      model(ATTEMPT)])

print("wrote", *(f"docs/figures/setting_{r}.png" for r in COLORS))
