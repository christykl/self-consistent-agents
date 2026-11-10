"""Paraphrase each row's stored self-report, for `run.py --self-report-paraphrased-from`.

    python scripts/paraphrase_self_reports.py MODEL [MODEL ...] [--tasks TASK ...]

Writes outputs/<task>_<model>_selfreport1/paraphrases.json:
{"paraphraser": NAME, "paraphrases": {row id: text}}. Rows already in the file
are skipped, so every rerun of the setting shows the same text.

One paraphraser (Claude Sonnet 5.5) is used for every subject model. It belongs to
none of their families, so the paraphrase does not carry a subject's own token
distribution (docs/self_report_paraphrased.md).

Prints any probability or file path that a paraphrase dropped. Those rows would
tell the attempt less than the original answer did.
"""
import argparse
import asyncio
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.judge import make_judge_agent  # noqa: E402
from core.self_report import load_answers, render  # noqa: E402

PARAPHRASER = "claude-sonnet-5-5-openrouter"
TASKS = ["prime_factorization", "subset_sum", "geoguessr_single", "knowledge_work", "protein_design"]
PROMPT = (ROOT / "prompts" / "paraphrase_self_report.md").read_text()
MAX_CONCURRENT = 16


def missing_literals(answer, text):
    """The answer's probabilities and file paths that are absent from `text`.
    A path has a dot or two slashes, which skips phrases like "tools/packages"."""
    actions = answer.get("actions") or []
    prose = " ".join([answer.get("explanation") or ""] + [a["action"] for a in actions])
    paths = [x.rstrip(".") for x in re.findall(r"[\w.-]*/[\w./-]+", prose) if "." in x or x.count("/") >= 2]
    return [x for x in [str(a["probability"]) for a in actions] + paths if x not in text]


async def paraphrase(agent, answer, sem):
    async with sem:
        resp = await agent.async_completions(
            [{"role": "user", "content": PROMPT.replace("{{answer}}", render(answer))}])
    return resp.content.strip()


async def paraphrase_run(agent, sr_dir, sem):
    path = sr_dir / "paraphrases.json"
    done = json.loads(path.read_text())["paraphrases"] if path.exists() else {}
    answers = load_answers(sr_dir)
    todo = [row for row in answers if row not in done]
    texts = await asyncio.gather(*[paraphrase(agent, answers[row], sem) for row in todo])
    done.update(zip(todo, texts))
    path.write_text(json.dumps({"paraphraser": PARAPHRASER, "paraphrases": done}, indent=1))
    for row, text in done.items():
        if missing_literals(answers[row], text):
            print(f"{sr_dir.name} {row}: dropped {missing_literals(answers[row], text)}")
    print(f"{sr_dir.name}: {len(todo)} new, {len(done)} total")


async def main(models, tasks):
    agent = make_judge_agent(PARAPHRASER, ROOT / "configs" / "models.yaml")
    sem = asyncio.Semaphore(MAX_CONCURRENT)
    await asyncio.gather(*[paraphrase_run(agent, ROOT / "outputs" / f"{task}_{model}_selfreport1", sem)
                           for model in models for task in tasks])


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("models", nargs="+")
    ap.add_argument("--tasks", nargs="+", default=TASKS)
    args = ap.parse_args()
    asyncio.run(main(args.models, args.tasks))
