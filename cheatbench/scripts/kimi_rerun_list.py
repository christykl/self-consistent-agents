"""List the Kimi K3 (Fireworks) episodes to rerun from the 2026-11-24 runs.

An episode is on the list if its log shows ANY Fireworks 429 (throttling ate
into its time budget or killed it), or if its latest record is a failure other
than an unthrottled timeout (dead go service sandbox, cancelled by us), or if it
has no record at all. An unthrottled timeout is a valid outcome, not a rerun:
the agent used its whole budget and the judge scores what is there.
Episodes still running are reported as such.

    python scripts/kimi_rerun_list.py        # writes outputs/kimi_fireworks_rerun_list.json
"""
import json, os, glob

# run dir -> its run.py log; a run whose log has no summary yet is still running.
LOGS = {"chess_none_kimi-k3-fireworks_pilot1": "kimi_fireworks_chess",
        "prime_factorization_kimi-k3-fireworks_selfreportcond1": "kimi_fireworks_prime_factorization_selfreportcond"}
RUNS = ["chess_none_kimi-k3-fireworks_pilot1", "go_kimi-k3-fireworks_pilot1",
        "prime_factorization_kimi-k3-fireworks_pilot1", "prime_factorization_kimi-k3-fireworks_selfreport1",
        "prime_factorization_kimi-k3-fireworks_alignprompt1", "prime_factorization_kimi-k3-fireworks_extremealign2",
        "prime_factorization_kimi-k3-fireworks_selfreportcond1"]

out = {}
for run in RUNS:
    d = f"outputs/{run}"
    latest = {}
    for line in open(f"{d}/episodes.jsonl"):
        r = json.loads(line)
        latest[r["episode"]] = r
    log_name = LOGS.get(run)
    running = bool(log_name) and "=== summary" not in open(f"outputs/logs/{log_name}.log").read()
    entries, still_running = {}, []
    for ep in sorted(os.listdir(f"{d}/trajectories")):
        log = open(f"{d}/trajectories/{ep}/container.stderr.log", errors="replace").read()
        rec = latest.get(ep)
        reasons = []
        if "-> 429" in log:
            reasons.append(f"throttled ({log.count('-> 429')} x 429)")
        if rec is None and running and not reasons:
            still_running.append(ep)
            continue
        if rec is None:
            reasons.append("no record (cancelled with its process)")
        elif rec.get("failure") and not (rec["failure"] == "timeout" and not reasons):
            reasons.append(f"failed: {rec['failure']}")
        if reasons:
            entries[ep] = "; ".join(reasons)
    out[run] = {"rerun": entries, "still_running_clean": still_running}
    print(f"{run:55s} rerun {len(entries):2d} / {len(os.listdir(d + '/trajectories'))}"
          + (f"   (+{len(still_running)} still running, clean so far)" if still_running else ""))

json.dump(out, open("outputs/kimi_fireworks_rerun_list.json", "w"), indent=1)
print("total", sum(len(v["rerun"]) for v in out.values()), "-> outputs/kimi_fireworks_rerun_list.json")
