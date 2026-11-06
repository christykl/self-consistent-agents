"""Rerun the Gemini episodes lost to the old run_cli deadline (docs/gemini_vertex.md).

An episode whose latest record says "container killed" was killed by the host before the runner
could read its session. This script reruns exactly those episodes, with the flags of their
setting, and appends to the same run dirs, so the new record and verdict become the latest ones
that compare_settings.py and the other tables read.

    python scripts/rerun_killed_gemini.py          # needs VERTEX_SERVICE_ACCOUNT

Before rerunning it saves the old outcome in docs/data/killed_gemini_reruns.json and moves the old
trajectory to outputs/_killed_gemini_sessions/, since a rerun writes to the same trajectory path.
Smoke-test run dirs are ignored (their run ids are not in FLAGS). Running it again reruns any listed
episode whose latest record is still "container killed" or an infrastructure failure. One background
run.py per run dir.
Logs: outputs/logs/rerun_killed_<run dir>.log
"""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUTPUTS = ROOT / "outputs"
ARCHIVE = OUTPUTS / "_killed_gemini_sessions"
MANIFEST = ROOT / "docs/data/killed_gemini_reruns.json"
MODELS = ["gemini-4-argon-vertex", "gemini-3.8-flash-vertex"]
TASKS = ["prime_factorization", "subset_sum", "knowledge_work"]
# The same flags as scripts/run_five_settings.sh and scripts/run_in_context.sh.
FLAGS = {"pilot1": [],
         "honeypot1": ["--honeypot", "alignment"],
         "alignprompt1": ["--prompt-wrapper", "prompts/alignment_eval.md"],
         "selfreportcond1": ["--self-report-from", "selfreport1"],
         "incontext1": ["--self-report-in-context-from", "selfreport1"]}


def jsonl(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def latest(path):
    return {r["episode"]: r for r in jsonl(path)} if path.exists() else {}


manifest = json.loads(MANIFEST.read_text()) if MANIFEST.exists() else []
to_run = {}  # run dir name -> (task, model, run id, row ids)
for task in TASKS:
    for model in MODELS:
        for run_id in FLAGS:
            name = f"{task}_{model}_{run_id}"
            run_dir = OUTPUTS / name
            records = latest(run_dir / "episodes.jsonl")
            verdicts = latest(run_dir / "judge.jsonl")
            only = []
            for episode, rec in records.items():
                listed = any(m["run_dir"] == name and m["episode"] == episode for m in manifest)
                killed = "container killed" in (rec.get("error") or "")
                if killed and not listed:
                    old_dir = run_dir / "trajectories" / episode
                    transcript = old_dir / "transcript.json"
                    manifest.append({
                        "run_dir": name, "task": task, "model": model, "run_id": run_id,
                        "id": rec["id"], "episode": episode,
                        "old_messages": len(json.loads(transcript.read_text()).get("messages") or []),
                        "old_cheated": verdicts.get(episode, {}).get("cheated"),
                        "old_verdict": verdicts.get(episode)})
                    (ARCHIVE / name).mkdir(parents=True, exist_ok=True)
                    shutil.move(str(old_dir), str(ARCHIVE / name / episode))
                    # run.py rewrites run.json; keep the sweep's copy.
                    if not (run_dir / "run_pilot.json").exists():
                        shutil.copy(run_dir / "run.json", run_dir / "run_pilot.json")
                    only.append(rec["id"])
                elif listed and killed:
                    # Killed again while streaming its transcript (CONTAINER_GRACE_S was too
                    # short): keep what that attempt recorded, then run it once more.
                    old_dir = run_dir / "trajectories" / episode
                    entry = next(m for m in manifest if m["run_dir"] == name and m["episode"] == episode)
                    entry.setdefault("truncated_reruns", []).append({
                        "messages": len(json.loads((old_dir / "transcript.json").read_text()).get("messages") or []),
                        "cheated": verdicts.get(episode, {}).get("cheated"),
                        "verdict": verdicts.get(episode)})
                    n = len(entry["truncated_reruns"])
                    shutil.move(str(old_dir), str(ARCHIVE / name / f"{episode}.rerun{n}"))
                    only.append(rec["id"])
                elif listed and not rec["ok"] and rec.get("failure") != "timeout":
                    only.append(rec["id"])
            if only:
                to_run[name] = (task, model, run_id, only)

MANIFEST.write_text(json.dumps(manifest, indent=1))
print(f"{len(manifest)} listed episodes; rerunning {sum(len(v[3]) for v in to_run.values())}")

env = {**os.environ, "PYTHONUNBUFFERED": "1"}
(OUTPUTS / "logs").mkdir(exist_ok=True)
processes = []
for name, (task, model, run_id, only) in to_run.items():
    print(name, only, flush=True)
    processes.append(subprocess.Popen(
        [sys.executable, "run.py", task, "--model", model, "--judge", "gpt-6-sol-openrouter",
         "--sandbox", "modal", "--max-concurrent", "8", "--run-id", run_id, "--only", ",".join(only),
         *FLAGS[run_id], "--no-progress"],
        cwd=ROOT, env=env, stdout=open(OUTPUTS / "logs" / f"rerun_killed_{name}.log", "a"),
        stderr=subprocess.STDOUT))
for process in processes:
    process.wait()
print("exit codes:", [p.returncode for p in processes])
