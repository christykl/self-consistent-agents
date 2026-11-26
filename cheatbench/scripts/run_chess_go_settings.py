"""Chess and Go in four prompt settings for one model, then one rerun pass for infra failures.

    python scripts/run_chess_go_settings.py gpt-6.1-sol-openrouter
    python scripts/run_chess_go_settings.py kimi-k3-fireworks 21 9   # chess / go concurrency

Settings (selfreportcond1 and incontext1 read the model's selfreport1 run, which must
already exist for both tasks):
    alignprompt1     --prompt-wrapper prompts/alignment_eval.md
    extremealign2    --prompt-wrapper prompts/extreme_alignment_eval.md  (2026-11-20 text)
    selfreportcond1  --self-report-from selfreport1
    incontext1       --self-report-in-context-from selfreport1

Slots. Each task has a pool of slots (chess 30, Go 10 by default; each Go episode holds a T4
and Modal allows 10 GPUs), and every episode is its own `run.py --only ROW` process, so a
slot is reused the moment its episode ends. The four settings' rows are interleaved
(row 1 of each setting, then row 2, ...), so the settings run in parallel and see the same
conditions over time. (Until 2026-11-25 each setting was one run.py batch and the settings
ran one after another, which left most slots idle while each setting's last rows finished.)
The optional CHESS_N GO_N arguments lower the pools: for a model entry with
`max_concurrent_episodes` (kimi-k3-fireworks: 30, the TOTAL across all run.py processes),
CHESS_N + GO_N must fit under it, and GO_N must fit under the GPUs other runs leave free.
Several run.py processes then append to one run dir's episodes.jsonl; each record is one
line written in one call, and run.py skips only rows with an ok record.

Episodes already running when the script starts (run.py processes of this model on these
settings, e.g. from an earlier launch of this script) keep their slots: those rows are not
started again, and the pool only uses the slots they leave free, taking each one as an
episode ends.

Rerun pass: once a task's first pass (and any earlier run.py on it) has finished, rows
whose latest record failed for any reason other than `timeout` or `max_turns` (those are
measurements of the agent), plus rows with no record at all, are run once more.
One kind of `timeout` is rerun: "(container killed)" (the host's backstop at 3600 + 900 s)
when the agent's model calls stopped 10+ min before the budget ran out, i.e. the container
hung (seen 2026-11-24, chess 2OINf: calls stopped at 25 min, killed at 75 min).
One pass only; whatever still fails is printed at the end.

Out of funds: once any record is `usage_limit` (an OpenRouter 402), the script starts no
further episode for either task. Rerunning the script after a top-up resumes: rows with an
ok, `timeout` or `max_turns` record are not rerun.

Watchdog: the agent sandbox's forwarder (core/sandbox/modal_runtime.py FORWARDER) sometimes
dies mid-episode, cause unknown (~1 in 30 episodes, 2026-11-24). Codex then logs only
"Reconnecting... waiting for network" until the 3600 s timeout, and the record would read as
an agent timeout. When an unfinished episode's log ends in three such lines, the watchdog
terminates its agent sandbox, so the record is `container_exit` and the rerun pass takes it.

Logs: this script prints one line per episode start/end (with run.py's exit code);
each episode's run.py output goes to outputs/logs/settings_<model>/<task>_<run_id>_<row>.log
(..._rerun.log for the rerun pass).
"""
import glob
import json
import os
import queue
import subprocess
import sys
import threading
import time
from datetime import datetime

import modal

MODEL = sys.argv[1]
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
SETTINGS = {
    "alignprompt1": ["--prompt-wrapper", "prompts/alignment_eval.md"],
    "extremealign2": ["--prompt-wrapper", "prompts/extreme_alignment_eval.md"],
    "selfreportcond1": ["--self-report-from", "selfreport1"],
    "incontext1": ["--self-report-in-context-from", "selfreport1"],
}
CHESS_N, GO_N = (int(a) for a in sys.argv[2:4]) if len(sys.argv) > 2 else (30, 10)
TASKS = {"chess": ("chess_none", CHESS_N), "go": ("go", GO_N)}  # task -> (run dir prefix, slots)
# --no-auto-retry: this script's own rerun pass handles failures, and run.py's automatic
# retry of `rate_limit` failures would send them straight back into the throttling.
COMMON = ["--model", MODEL, "--judge", "gpt-6-sol-openrouter", "--sandbox", "modal", "--no-progress",
          "--no-auto-retry", "--max-concurrent", "1"]
AGENT_RESULTS = ("timeout", "max_turns")  # failures that are findings, not infra
STALL = "Reconnecting... waiting for network"
BUDGET_S = 3600  # chess and go `timeout_s`
NO_FUNDS = threading.Event()  # set once any run records `usage_limit`; both tasks stop
LOG_DIR = f"outputs/logs/settings_{MODEL}"


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


# run.py processes of this model that were running before this script started
# ({pid: (task, run_id, row or None)}); they hold slots. A process this script started
# names its one row with --only; a whole-setting batch (row None) holds its unrecorded rows.
EARLIER = {}
for line in subprocess.run(["pgrep", "-fl", f"run.py .*--model {MODEL} "],
                           capture_output=True, text=True).stdout.splitlines():
    pid, cmd = line.split(" ", 1)
    words = cmd.split()
    task, run_id = words[words.index("run.py") + 1], words[words.index("--run-id") + 1]
    row = words[words.index("--only") + 1] if "--only" in words else None
    if task in TASKS and run_id in SETTINGS:
        EARLIER[int(pid)] = (task, run_id, row)


def in_flight(task):
    """{(run_id, row)} being run by a still-running earlier run.py. A single-row process's
    row counts even if it already has a record (a retry of a failed row: 2026-11-25, Go
    ogs_76510140_m196 was started twice when this counted only unrecorded rows)."""
    rows = set()
    for pid, (t, run_id, row) in EARLIER.items():
        if t != task or subprocess.run(["kill", "-0", str(pid)], capture_output=True).returncode:
            continue
        if row:
            rows.add((run_id, row))
            continue
        started = {os.path.basename(d).split("#")[0]
                   for d in glob.glob(f"{run_dir(task, run_id)}/trajectories/*#1")}
        rows |= {(run_id, r) for r in started - set(latest_records(task, run_id))}
    return rows


def todo(task, run_id):
    """Rows to run: no record yet, a latest record that failed for a reason other than
    `timeout` / `max_turns` (a natural timeout is a result about the agent; never rerun),
    or a `timeout` that is really a hung container (`hung`). Rows in flight are left out."""
    all_ids = sorted(latest_records(task, "selfreport1"))  # every row of the task
    recs = latest_records(task, run_id)
    busy = {r for s, r in in_flight(task) if s == run_id}

    def due(i):
        if i in busy:
            return False
        if i not in recs:
            return True
        r = recs[i]
        if r.get("ok"):
            return False
        if r.get("failure") not in AGENT_RESULTS:
            return True
        return "(container killed)" in str(r.get("error")) and hung(task, run_id, i)
    return [i for i in all_ids if due(i)]


def out_of_funds(task, run_id):
    if any(r.get("failure") == "usage_limit" for r in latest_records(task, run_id).values()):
        if not NO_FUNDS.is_set():
            log(f"OUT OF FUNDS in {task} {run_id}: starting nothing else. Top up, then rerun this script.")
        NO_FUNDS.set()
    return NO_FUNDS.is_set()


def run_episode(task, run_id, row, suffix):
    cmd = [sys.executable, "run.py", task, *COMMON, "--run-id", run_id, *SETTINGS[run_id],
           "--only", row]
    log(f"start {task} {run_id} {row}{suffix}")
    with open(f"{LOG_DIR}/{task}_{run_id}_{row}{suffix}.log", "w") as out:
        code = subprocess.run(cmd, stdout=out, stderr=subprocess.STDOUT,
                              env={**os.environ, "PYTHONUNBUFFERED": "1"}).returncode
    rec = latest_records(task, run_id).get(row, {})
    result = "ok" if rec.get("ok") else rec.get("failure") or "NO RECORD"
    log(f"end   {task} {run_id} {row}{suffix}: exit {code}, {result}")


def run_pool(task, jobs, suffix):
    """Run `jobs` [(run_id, row)] on the task's slots, less those earlier runs still hold."""
    q = queue.Queue()
    for job in jobs:
        q.put(job)

    def worker(i):
        while True:
            while i < len(in_flight(task)):  # slot i is still held by an earlier run.py
                time.sleep(30)
            try:
                run_id, row = q.get_nowait()
            except queue.Empty:
                return
            if out_of_funds(task, run_id):
                return
            run_episode(task, run_id, row, suffix)
            out_of_funds(task, run_id)

    workers = [threading.Thread(target=worker, args=(i,)) for i in range(TASKS[task][1])]
    for w in workers:
        w.start()
    for w in workers:
        w.join()


def run_task(task):
    assert latest_records(task, "selfreport1"), f"no {task} selfreport1 run for {MODEL}"
    for suffix in ("", "_rerun"):
        if suffix:  # the rerun pass waits for earlier runs, so their failures are in it too
            while in_flight(task):
                time.sleep(60)
        per_setting = [[(run_id, row) for row in todo(task, run_id)] for run_id in SETTINGS]
        # Interleave: row 1 of each setting, then row 2, ...
        jobs = [job for group in zip(*[g + [None] * (max(map(len, per_setting)) - len(g))
                                       for g in per_setting]) for job in group if job]
        log(f"{task}{suffix or ' first pass'}: {len(jobs)} episodes "
            f"({', '.join(f'{s} {len(g)}' for s, g in zip(SETTINGS, per_setting))}), "
            f"{TASKS[task][1]} slots, {len(in_flight(task))} held by earlier runs")
        run_pool(task, jobs, suffix)


def watchdog():
    killed = set()
    while True:
        for task in TASKS:
            for run_id in SETTINGS:
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


os.makedirs(LOG_DIR, exist_ok=True)
log(f"earlier run.py processes holding slots: {EARLIER}")
# The watchdog starts first, so it also covers runs still going from an earlier launch.
threading.Thread(target=watchdog, daemon=True).start()
threads = [threading.Thread(target=run_task, args=(t,)) for t in TASKS]
for t in threads:
    t.start()
for t in threads:
    t.join()

for task in TASKS:
    for run_id in SETTINGS:
        recs = latest_records(task, run_id)
        bad = {i: r.get("failure") for i, r in recs.items() if not r.get("ok")}
        log(f"final {task} {run_id}: {len(recs)} rows, not ok: {bad}")
