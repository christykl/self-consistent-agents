"""Read the agent's answer out of a `--self-report` episode record.

The answer is the JSON object `{tempted, explanation, actions}` that
prompts/self_report.md asks the agent to end its final message with.
Used by scripts/self_report_table.py and by `run.py --self-report-from`.
"""
import json
import re


def answers_in(text):
    """Every JSON object with a `tempted` key in `text`, including one nested
    as a string inside another object (Terminus-2 replies are themselves JSON,
    and the model sometimes puts its answer inside their `analysis` field)."""
    found = []
    for i in [m.start() for m in re.finditer(r"\{", text)]:
        try:
            obj, _ = json.JSONDecoder().raw_decode(text, i)
        except ValueError:
            continue
        if isinstance(obj, dict) and "tempted" in obj:
            found.append(obj)
        elif isinstance(obj, dict):
            found += [a for v in obj.values() if isinstance(v, str) for a in answers_in(v)]
    return found


def find_answer(rec):
    """Codex ends with the answer. Terminus-2 asks the agent to confirm
    `task_complete` in an extra turn, so its final message is usually the
    confirmation and the answer is in an earlier reply. Raw replies
    (`raw_responses`) are searched first: Harbor's trajectory keeps only the
    parsed analysis/plan and drops an answer written after the JSON reply."""
    steps = (rec.get("harbor_trajectory") or {}).get("steps") or []
    texts = ([rec["final_text"]] + list(reversed(rec.get("raw_responses") or []))
             + [s.get("message") or "" for s in reversed(steps) if s.get("source") == "agent"])
    return next(a[-1] for a in map(answers_in, texts) if a)


def load_answers(run_dir):
    """{row id: answer} for every successful episode in a self-report run dir
    (replicate 1 if the row was repeated)."""
    recs = [json.loads(line) for line in (run_dir / "episodes.jsonl").read_text().splitlines()
            if line.strip()]
    return {r["id"]: find_answer(r) for r in recs if r.get("ok") and r.get("replicate", 1) == 1}
