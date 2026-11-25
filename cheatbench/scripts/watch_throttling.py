"""Watch running episodes for provider rate limiting (HTTP 429), live.

    python scripts/watch_throttling.py outputs/chess_none_kimi-k3-fireworks_pilot1 [RUN_DIR ...]

Every minute it counts the `forwarder: POST ... -> 429` lines in each episode's
container.stderr.log and prints one line per run that got NEW 429s, so it can be
the event stream of a Claude Code Monitor (or just a terminal). Every 10 minutes it
prints a heartbeat with the totals, so silence never means "not watching".
Stop it with Ctrl-C.

Why: on 2026-11-24 ~70 concurrent Kimi K3 episodes on Fireworks drew 1268 429s
against 1994 200s, and nothing noticed for 45 minutes, because the run.py logs
only report failures in the end-of-run summary (docs/kimi_fireworks.md).

Coverage: kimi-code's runner logs each forwarded call (`forwarder: POST ... -> 429`);
terminus-2 logs each failed LiteLLM call (`litellm.RateLimitError ... 429`, which is
how an OpenRouter 429 reaches the log). Other harnesses log nothing per call here; for
them, look at `throttled_calls` on finished records (core/trial.py `throttling`),
which is None when the episode ran without a forwarder.

It also prints one line per newly written FAILED record in each run's episodes.jsonl
(the record's `failure` tag and the start of its `error`), since run.py itself only
reports failures in its end-of-run summary. Like the 429 counts, records already
written when the watcher starts are taken as the baseline and not printed.
"""
import glob
import json
import os
import sys
import time

run_dirs = sys.argv[1:]
if not run_dirs:
    sys.exit(__doc__)

seen = {}          # log path -> 429 lines counted so far
records_seen = {}  # run -> episodes.jsonl lines read so far
last_heartbeat = 0.0
first = True       # the first pass only takes a baseline (reported in the heartbeat)
while True:
    now = time.time()
    totals = {}
    for run in run_dirs:
        new, episodes_hit, total = 0, 0, 0
        for log in glob.glob(f"{run}/trajectories/*/container.stderr.log"):
            n = sum(1 for line in open(log, errors="replace")
                    if ("forwarder: POST" in line and "-> 429" in line)
                    or ("RateLimitError" in line and "429" in line))
            new += n - seen.get(log, 0)
            seen[log] = n
            total += n
            episodes_hit += n > 0
        totals[run] = (total, episodes_hit)
        path = f"{run}/episodes.jsonl"
        lines = open(path).read().splitlines() if os.path.exists(path) else []
        for line in lines[records_seen.get(run, 0):]:
            rec = json.loads(line)
            if not rec["ok"] and not first:
                print(f"{time.strftime('%H:%M')} FAILED {run}: {rec['episode']} "
                      f"[{rec.get('failure')}] {str(rec.get('error'))[:160]}", flush=True)
        records_seen[run] = len(lines)
        if new > 0 and not first:
            print(f"{time.strftime('%H:%M')} THROTTLED {run}: +{new} x 429 in the last minute "
                  f"({total} total across {episodes_hit} episodes)", flush=True)
    if now - last_heartbeat >= 600:
        last_heartbeat = now
        print(f"{time.strftime('%H:%M')} heartbeat: " + "; ".join(
            f"{run.rstrip('/').split('/')[-1]} {t} x 429 in {e} eps" for run, (t, e) in totals.items()),
            flush=True)
    first = False
    time.sleep(60)
