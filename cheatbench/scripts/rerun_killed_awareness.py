"""Reclassify eval awareness for the episodes scripts/rerun_killed_gemini.py reran, in place.

    python scripts/rerun_killed_awareness.py

Uses scripts/eval_awareness.py's classifier and replaces only those rows of docs/data/eval_awareness_RUN.json,
so the other episodes keep their classifications (counts vary a little between classifier runs).
A model with no rows in a file was never classified there (Flash) and is left out.
"""
import json
from pathlib import Path

from eval_awareness import classify, cf

ROOT = Path(__file__).resolve().parent.parent
listed = json.loads((ROOT / "docs/data/killed_gemini_reruns.json").read_text())
for run in ["pilot1", "honeypot1", "alignprompt1", "selfreportcond1"]:
    path = ROOT / "docs/data" / f"eval_awareness_{run}.json"
    rows = json.loads(path.read_text())
    episodes = [m for m in listed if m["run_id"] == run and any(r["model"] == m["model"] for r in rows)]
    jobs = [(m["model"], m["task"], m["episode"], ROOT / "outputs" / m["run_dir"] / "trajectories" / m["episode"])
            for m in episodes]
    with cf.ThreadPoolExecutor(8) as ex:
        new = list(ex.map(classify, jobs))
    for m, row in zip(episodes, new):
        verdicts = [json.loads(line) for line in (ROOT / "outputs" / m["run_dir"] / "judge.jsonl").read_text().splitlines()]
        row["cheated"] = [v for v in verdicts if v["episode"] == m["episode"]][-1].get("cheated") is True
        old = next(r for r in rows if (r["model"], r["task"], r["episode"]) == (row["model"], row["task"], row["episode"]))
        print(run, row["model"], m["id"], "aware", old["aware"], "->", row["aware"], row["level"], "cheated", row["cheated"])
        rows[rows.index(old)] = row
    path.write_text(json.dumps(rows, indent=1))
