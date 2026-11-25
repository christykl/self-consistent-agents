#!/usr/bin/env bash
# Kimi K3 (Fireworks, Kimi Code) on every row of chess and go (default setting)
# and prime_factorization in five settings.
#
#     bash scripts/run_kimi_fireworks.sh
#
# Rerunning resumes: rows with an ok record are skipped (an ok-but-throttled
# episode needs `run.py ... --redo --only ID,...`; see outputs/kimi_fireworks_rerun_list.json).
#
# Concurrency. The binding limit is Fireworks' token rate limit, not Modal:
# kimi-k3-fireworks has `max_concurrent_episodes: 30` in configs/models.yaml, and
# that 30 is the TOTAL across all processes running at once, so phase 1 splits it
# (go 10 + chess 20) and the prime_factorization settings run one after another.
# Modal allows 10 GPUs and 5000 sandboxes; each go episode holds a T4 service
# sandbox, so go stays at 10.
#   (The 2026-11-24 launch did not follow this layout: chess 24 + go 10 + up to 40
#   prime_factorization episodes at once drew 429s on 39% of requests;
#   docs/kimi_fireworks.md.)
#
# --no-auto-retry: run.py's automatic pass reruns `rate_limit` failures once, which
# under throttling just repeats them. `set -m` gives each background run.py its own
# process group, so `kill -INT <pid>` stops it cleanly (a background job in a
# non-interactive shell otherwise ignores SIGINT).
#
# Watch for throttling while it runs:
#     python scripts/watch_throttling.py outputs/*kimi-k3-fireworks_*
# Logs: outputs/logs/kimi_fireworks_<task>.log
set -u -m
cd "$(dirname "$0")/.."
COMMON="--model kimi-k3-fireworks --judge gpt-6-sol-openrouter --sandbox modal --no-progress --no-auto-retry"
mkdir -p outputs/logs
export PYTHONUNBUFFERED=1

# Phase 1: chess and go together (20 + 10 = the 30-episode budget).
python run.py go $COMMON --run-id pilot1 --max-concurrent 10 > outputs/logs/kimi_fireworks_go.log 2>&1 &
python run.py chess $COMMON --run-id pilot1 --max-concurrent 20 > outputs/logs/kimi_fireworks_chess.log 2>&1 &
wait

# Phase 2: prime_factorization, one setting at a time (20 rows each). selfreport1
# must precede selfreportcond1, which reads it.
python run.py prime_factorization $COMMON --run-id pilot1 --max-concurrent 20 \
    > outputs/logs/kimi_fireworks_prime_factorization.log 2>&1
python run.py prime_factorization $COMMON --run-id selfreport1 --self-report --max-concurrent 20 \
    > outputs/logs/kimi_fireworks_prime_factorization_selfreport.log 2>&1
python run.py prime_factorization $COMMON --run-id alignprompt1 --prompt-wrapper prompts/alignment_eval.md \
    --max-concurrent 20 > outputs/logs/kimi_fireworks_prime_factorization_alignprompt.log 2>&1
python run.py prime_factorization $COMMON --run-id extremealign2 --prompt-wrapper prompts/extreme_alignment_eval.md \
    --max-concurrent 20 > outputs/logs/kimi_fireworks_prime_factorization_extremealign.log 2>&1
python run.py prime_factorization $COMMON --run-id selfreportcond1 --self-report-from selfreport1 \
    --max-concurrent 20 > outputs/logs/kimi_fireworks_prime_factorization_selfreportcond.log 2>&1
