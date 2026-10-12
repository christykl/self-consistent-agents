"""Re-run ONLY turn 1 of the ask-success-probability condition and record per-turn token usage.

The saved `658b8ecd` results only have a combined token_usage (both turns), so turn-1 reasoning
tokens are unrecoverable from them. This replays the exact turn-1 prompt stored in 658b8ecd
(system + task + ASK_SUCCESS_PROBABILITY_PROMPT) against the same model/temperature, without
the solve turn, and saves the provider's usage (completion_tokens, reasoning_tokens) per rollout.

Subset: `--n` problems at evenly spaced ranks of difficulty, where difficulty = mean output tokens
of the no-ask run 3fb9e8c3 (independent of the self-report). Output: turn1_reasoning.jsonl next to
this script's parent (environments/countdown_code/outputs/turn1_reasoning/).

    export OPENROUTER_API_KEY=...; source .venv/bin/activate
    python3 scripts/turn1_reasoning.py --n 50 --r 4      # difficulty-stratified 50 problems
    python3 scripts/turn1_reasoning.py --remaining --r 4  # append the other 150 to the same file
"""

import argparse
import asyncio
import json
import os
from collections import defaultdict
from pathlib import Path

import numpy as np
from openai import AsyncOpenAI

ROOT = Path(__file__).resolve().parent.parent
RUNS = ROOT / "outputs/evals/countdown_code--openai--o4-mini"
NOASK, SUCCPROB = "3fb9e8c3", "658b8ecd"


def load(run):
    with open(RUNS / run / "results.jsonl") as f:
        return [json.loads(line) for line in f]


def select(n):
    tok = defaultdict(list)
    for r in load(NOASK):
        tok[r["example_id"]].append(r["token_usage"]["output_tokens"])
    ids = sorted(tok, key=lambda e: (np.mean(tok[e]), e))
    step = len(ids) / n
    return [ids[int(step * i + step / 2)] for i in range(n)]


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=50)
    ap.add_argument("--r", type=int, default=4)
    ap.add_argument("--remaining", action="store_true", help="run all problems not yet in --out; append")
    ap.add_argument("--c", type=int, default=20)
    ap.add_argument("--out", default=str(ROOT / "outputs/turn1_reasoning/turn1.jsonl"))
    a = ap.parse_args()
    prompts = {}
    for r in load(SUCCPROB):
        prompts[r["example_id"]] = r["prompt"]
    if a.remaining:
        done = {json.loads(line)["example_id"] for line in open(a.out)}
        ids = sorted(set(prompts) - done)
    else:
        ids = select(a.n)
    client = AsyncOpenAI(base_url="https://openrouter.ai/api/v1", api_key=os.environ["OPENROUTER_API_KEY"], max_retries=3)
    sem = asyncio.Semaphore(a.c)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    fout = open(a.out, "a" if a.remaining else "w")

    async def one(e, k):
        async with sem:
            for _ in range(3):  # OpenRouter occasionally returns choices=None
                resp = await client.chat.completions.create(
                    model="openai/o4-mini", messages=prompts[e], temperature=1)
                if resp.choices:
                    break
            else:
                return
        u = resp.usage
        row = {"example_id": e, "rollout": k, "content": resp.choices[0].message.content,
               "completion_tokens": u.completion_tokens,
               "reasoning_tokens": u.completion_tokens_details.reasoning_tokens,
               "prompt_tokens": u.prompt_tokens, "finish_reason": resp.choices[0].finish_reason}
        fout.write(json.dumps(row) + "\n"); fout.flush()

    await asyncio.gather(*(one(e, k) for e in ids for k in range(a.r)))


if __name__ == "__main__":
    asyncio.run(main())
