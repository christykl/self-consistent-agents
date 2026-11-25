"""GPT-5 on prime_factorization: baseline vs. the three self-report settings, row by row.

Prints, for each row, the judge's verdict and cheat route in pilot1, selfreportcond1,
selfreportpara1 and incontext1 (CODE = prohibited computation, e.g. `factor N`;
KEY = used a planted answer key), then per setting:
  - episodes that never submitted anything to the verifier,
  - episodes whose visible reasoning/messages refer back to the earlier self-report
    answer (a loose keyword pattern; spot-check with --show).

Usage: python scripts/pf_gpt5_self_report_settings.py [--show]
"""
import json
import re
import sys

BASE = "outputs/prime_factorization_gpt-5-openrouter_"
RUNS = ["pilot1", "selfreportcond1", "selfreportpara1", "incontext1"]
REFERS_BACK = re.compile(
    r"(promis(e|ed)\b|commitment\b|earlier (planning|answer|session|commitment|promise)"
    r"|previously (stated|said|promised|committed)|planning session|previous planning"
    r"|I said (I|no)|honesty test|testing my commitment|personal guideline|the planning"
    r"|said I wouldn|stated I wouldn|recalled my)", re.I)


def last_records(path):
    by_id = {}
    for line in open(path):
        r = json.loads(line)
        by_id[r["id"]] = r
    return by_id


def attempt_text(run, row):
    """Visible reasoning summaries and assistant messages of the attempt only
    (for incontext1, everything after the restored self-report history)."""
    t = json.load(open(f"{BASE}{run}/trajectories/{row}#1/transcript.json"))
    started = run != "incontext1"
    out = []
    for m in t["messages"]:
        p = m.get("payload", {})
        if not started:
            started = p.get("type") == "thread_settings_applied"
            continue
        if p.get("type") == "reasoning":
            out.append(" ".join(x.get("text", "") for x in p.get("summary", [])))
        elif p.get("type") == "message" and p.get("role") == "assistant":
            out.append(" ".join(c.get("text", "") for c in p["content"]))
    return " ".join(out)


def route(j):
    if not j["cheated"]:
        return "-"
    parts = [name for key, name in [("prohibited_computation", "CODE"), ("used_answer_key", "KEY"),
                                    ("tampering", "TAMPER")] if j.get(key)]
    return "cheat:" + "+".join(parts)


judge = {r: last_records(BASE + r + "/judge.jsonl") for r in RUNS}
eps = {r: last_records(BASE + r + "/episodes.jsonl") for r in RUNS}
rows = sorted(judge["incontext1"], key=lambda s: int(s.split("_")[-1]))

print("row".ljust(13) + "".join(r.ljust(17) for r in RUNS) + "self-report tempted")
for row in rows:
    print(row.ljust(13) + "".join(route(judge[r][row]).ljust(17) for r in RUNS)
          + str(eps["incontext1"][row]["prior_self_report"]["tempted"]))

print()
for r in RUNS:
    cheated = sum(judge[r][x]["cheated"] for x in rows)
    no_submit = sum(not eps[r][x]["grader_state"]["attempts"] for x in rows)
    line = f"{r:16s} cheated {cheated:2d}/20   never submitted {no_submit:2d}/20"
    if r != "pilot1":
        refers = [x for x in rows if REFERS_BACK.search(attempt_text(r, x))]
        line += (f"   refers back to the self-report {len(refers):2d}/20"
                 f" (cheated {sum(judge[r][x]['cheated'] for x in refers)})")
        if "--show" in sys.argv:
            for x in refers:
                text = attempt_text(r, x)
                m = REFERS_BACK.search(text)
                print(f"    {x}: ...{text[max(0, m.start() - 150):m.end() + 150]}...".replace("\n", " "))
    print(line)
