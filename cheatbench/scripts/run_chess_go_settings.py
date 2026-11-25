"""Chess and Go in four prompt settings for one model, then one rerun pass for infra failures.

    python scripts/run_chess_go_settings.py gpt-6.1-sol-openrouter
    python scripts/run_chess_go_settings.py kimi-k3-fireworks 21 9   # chess / go concurrency

Settings, in order (selfreportcond1 and incontext1 read the model's selfreport1 run, which
must already exist for both tasks):
    alignprompt1     --prompt-wrapper prompts/alignment_eval.md
    extremealign2    --prompt-wrapper prompts/extreme_alignment_eval.md  (2026-11-20 text)
    selfreportcond1  --self-report-from selfreport1
    incontext1       --self-report-in-context-from selfreport1

Chess and Go run in parallel, settings one after another within a task, so chess holds at
most 30 episodes and Go at most 10 (each Go episode holds a T4; Modal allows 10 GPUs).
The optional CHESS_N GO_N arguments lower these: for a model entry with
`max_concurrent_episodes` (kimi-k3-fireworks: 30, the TOTAL across all run.py processes),
CHESS_N + GO_N must fit under it, and GO_N must fit under the GPUs other runs leave free.
Each task starts once no other run.py process for this model is running on that task.

Rerun pass: after a task's four settings finish, each setting reruns (`--only ...`)
the rows whose latest record failed for any reason other than `timeout` or `max_turns`
(those are measurements of the agent), plus rows with no record at all (an aborted batch).
One kind of `timeout` is rerun: "(container killed)" (the host's backstop at 3600 + 900 s)
when the agent's model calls stopped 10+ min before the budget ran out, i.e. the container
hung (seen 2026-11-24, chess 2OINf: calls stopped at 25 min, killed at 75 min).
One pass only; whatever still fails is printed at the end.

Out of funds: run.py stops its batch at the first `usage_limit` record (an OpenRouter 402),
and this script then starts no further setting or rerun for either task. Rerunning the
script after a top-up resumes: rows with an ok, `timeout` or `max_turns` record are not rerun.

Watchdog: the agent sandbox's forwarder (core/sandbox/modal_runtime.py FORWARDER) sometimes
dies mid-episode, cause unknown (~1 in 30 episodes, 2026-11-24). Codex then logs only
"Reconnecting... waiting for network" until the 3600 s timeout, and the record would read as
an agent timeout. When an unfinished episode's log ends in three such lines, the watchdog
terminates its agent sandbox, so the record is `container_exit` and the rerun pass takes it.

Logs: outputs/logs/settings_<model>_<task>_<run_id>.log (and ..._rerun.log)
"""
import glob
import json
import os
import subprocess
import sys
import threading
import time
from datetime import datetime

import modal

MODEL = sys.argv[1]
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
SETTINGS = [
    ("alignprompt1", ["--prompt-wrapper", "prompts/alignment_eval.md"]),
    ("extremealign2", ["--prompt-wrapper", "prompts/extreme_alignment_eval.md"]),
    ("selfreportcond1", ["--self-report-from", "selfreport1"]),
    ("incontext1", ["--self-report-in-context-from", "selfreport1"]),
]
CHESS_N, GO_N = (int(a) for a in sys.argv[2:4]) if len(sys.argv) > 2 else (30, 10)
TASKS = {"chess": ("chess_none", CHESS_N), "go": ("go", GO_N)}  # task -> (run dir prefix, max concurrent)
# --no-auto-retry: this script's own rerun pass handles failures, and run.py's automatic
# retry of `rate_limit` failures would send them straight back into the throttling.
COMMON = ["--model", MODEL, "--judge", "gpt-6-sol-openrouter", "--sandbox", "modal", "--no-progress",
          "--no-auto-retry"]
AGENT_RESULTS = ("timeout", "max_turns")  # failures that are findings, not infra
STALL = "Reconnecting... waiting for network"
BUDGET_S = 3600  # chess and go `timeout_s`
NO_FUNDS = threading.Event()  # set once any run records `usage_limit`; both tasks stop


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def run_dir(task, run_id):
    return f"outputs/{TASKS[task][0]}_{MODEL}_{run_id}"


def latest_records(task, run_id):
    path = f"{run_dir(task, run_id)}/episodes.jsonl"
    recs = {}
    if os.path.exists(path):
        for line in open(path):
            r = json.loads(line)
            recs[r["id"]] = r
    return recs


def hung(task, run_id, row_id):
    """A host-side kill ("timeout after 4500s (container killed)") of an episode whose agent had
    gone quiet: its model calls (the service-side bridge log) span less than BUDGET_S - 600 s.
    A natural timeout reads "timeout after 3600s" (the in-container runner stopped the CLI)."""
    path = f"{run_dir(task, run_id)}/trajectories/{row_id}#1/service/inference_requests.jsonl"
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        return True  # no model call at all: hung from the start (chess O0aIK, 2026-11-25)
    ts = [datetime.fromisoformat(json.loads(l)["timestamp"]) for l in open(path)]
    return (ts[-1] - ts[0]).total_seconds() < BUDGET_S - 600


def todo(task, run_id):
    """Rows to run: no record yet, a latest record that failed for a reason other than
    `timeout` / `max_turns` (a natural timeout is a result about the agent; never rerun),
    or a `timeout` that is really a hung container (`hung`)."""
    all_ids = sorted(latest_records(task, "selfreport1"))  # every row of the task
    recs = latest_records(task, run_id)

    def due(i):
        if i not in recs:
            return True
        r = recs[i]
        if r.get("ok"):
            return False
        if r.get("failure") not in AGENT_RESULTS:
            return True
        return "(container killed)" in str(r.get("error")) and hung(task, run_id, i)
    return all_ids, [i for i in all_ids if due(i)]


def run(task, run_id, flags, log_name):
    """One run.py over this setting's todo rows (none -> nothing to do)."""
    all_ids, ids = todo(task, run_id)
    if not ids:
        return
    # run.py by itself would also rerun timeouts (they are not `ok`), so name the rows
    # unless every row is due.
    extra = [] if ids == all_ids else ["--only", ",".join(ids)]
    cmd = [sys.executable, "run.py", task, *COMMON, "--run-id", run_id,
           "--max-concurrent", str(TASKS[task][1]), *flags, *extra]
    log(f"start {task} {run_id} {' '.join(extra)}")
    with open(f"outputs/logs/{log_name}.log", "w") as out:
        code = subprocess.run(cmd, stdout=out, stderr=subprocess.STDOUT,
                              env={**os.environ, "PYTHONUNBUFFERED": "1"}).returncode
    log(f"end   {task} {run_id} exit {code}")


def out_of_funds(task, run_id):
    """run.py stops a batch at the first `usage_limit` record (e.g. OpenRouter 402); stop the sweep too."""
    if any(r.get("failure") == "usage_limit" for r in latest_records(task, run_id).values()):
        log(f"OUT OF FUNDS in {task} {run_id}: starting nothing else. Top up, then rerun this script.")
        NO_FUNDS.set()
    return NO_FUNDS.is_set()


def run_task(task):
    # Wait for earlier runs of this task and model (reruns, self-reports, a previous launch).
    while subprocess.run(["pgrep", "-f", f"run.py {task} .*--model {MODEL}"],
                         capture_output=True).returncode == 0:
        time.sleep(30)
    assert latest_records(task, "selfreport1"), f"no {task} selfreport1 run for {MODEL}"
    # First pass, then one rerun pass over whatever failed for infrastructure reasons.
    for suffix in ("", "_rerun"):
        for run_id, flags in SETTINGS:
            if out_of_funds(task, run_id):
                return
            run(task, run_id, flags, f"settings_{MODEL}_{task}_{run_id}{suffix}")
            if out_of_funds(task, run_id):
                return


def watchdog():
    killed = set()
    while True:
        for task in TASKS:
            for run_id, _ in SETTINGS:
                for f in glob.glob(f"{run_dir(task, run_id)}/trajectories/*/container.stderr.log"):
                    lines = open(f, errors="replace").read().splitlines()
                    # The log is appended to, so a rerun's episode follows the earlier
                    # attempt's: the current sandbox is named by the LAST host line.
                    hosts = [l for l in lines if l.startswith("[host] modal sandbox ")]
                    if len(lines) < 3 or not hosts or not all(STALL in l for l in lines[-3:]):
                        continue
                    sb_id = hosts[-1].split("modal sandbox ")[1].split(";")[0]
                    if sb_id in killed:
                        continue
                    log(f"watchdog: {f} stalled (forwarder dead); terminating {sb_id}")
                    modal.Sandbox.from_id(sb_id).terminate()
                    killed.add(sb_id)
        time.sleep(60)


# The watchdog starts first, so it also covers runs still going from an earlier launch.
threading.Thread(target=watchdog, daemon=True).start()
threads = [threading.Thread(target=run_task, args=(t,)) for t in TASKS]
for t in threads:
    t.start()
for t in threads:
    t.join()

for task in TASKS:
    for run_id, _ in SETTINGS:
        recs = latest_records(task, run_id)
        bad = {i: r.get("failure") for i, r in recs.items() if not r.get("ok")}
        log(f"final {task} {run_id}: {len(recs)} rows, not ok: {bad}")
