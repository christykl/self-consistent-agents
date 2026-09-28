"""Build data/turn1_injection_pool.json: real turn-1 responses (ask-success-probability replay,
outputs/turn1_reasoning/turn1.jsonl) grouped by the exact probability they state.

Kept: finish_reason=stop, exactly one </think>, and no digit other than the stated percentage, so a
response never mentions another problem's numbers or target and can be injected into any problem.

    python scripts/make_injection_pool.py
"""
import json
import re

LEVELS = (50, 90, 95)


def stated(content):
    m = re.search(r"(\d+(?:\.\d+)?)\s*%", content.split("</think>")[-1])
    return float(m.group(1)) if m else None


rows = [json.loads(l) for l in open("outputs/turn1_reasoning/turn1.jsonl")]
pool = {}
for level in LEVELS:
    pool[str(level)] = [
        r["content"] for r in rows
        if stated(r["content"]) == level and r["finish_reason"] == "stop"
        and r["content"].count("</think>") == 1
        and not re.search(r"\d", re.sub(r"\d+\s*%", "", r["content"]))
    ]
    print(level, len(pool[str(level)]))
json.dump(pool, open("data/turn1_injection_pool.json", "w"), indent=1)
