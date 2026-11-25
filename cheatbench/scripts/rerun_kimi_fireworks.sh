#!/usr/bin/env bash
# Rerun the 73 Kimi K3 (Fireworks) episodes that the 2026-11-24 launch's rate
# limiting touched (outputs/kimi_fireworks_rerun_list.json, built by
# scripts/kimi_rerun_list.py; docs/kimi_fireworks.md).
#
#     bash scripts/rerun_kimi_fireworks.sh
#
# --redo --only ID,...: some of these episodes have an ok record (they finished
# despite throttling), so --redo is needed; --only limits it to the listed rows.
# New records append to episodes.jsonl and supersede the old ones (latest wins).
# The old trajectories were moved to <run>/trajectories_throttled_20261124/ first.
#
# Same concurrency layout as scripts/run_kimi_fireworks.sh: at most 30 Kimi
# episodes at once in total (the kimi-k3-fireworks cap), go at 10 (Modal's GPU
# limit). Watch with:
#     python scripts/watch_throttling.py outputs/*kimi-k3-fireworks_*
set -u -m
cd "$(dirname "$0")/.."
COMMON="--model kimi-k3-fireworks --judge gpt-6-sol-openrouter --sandbox modal --no-progress --no-auto-retry --redo"
LIST=outputs/kimi_fireworks_rerun_list.json
mkdir -p outputs/logs
export PYTHONUNBUFFERED=1

PHASE=${1:-1}   # `bash scripts/rerun_kimi_fireworks.sh 2` skips phase 1

ids() {  # comma-separated row ids to rerun for one run directory
    python -c "import json,sys; print(','.join(sorted(e.split('#')[0] for e in json.load(open('$LIST'))[sys.argv[1]]['rerun'])))" "$1"
}

# Phase 1: go (17) and chess (22) together: 10 + 20 = 30.
# (2026-11-24: phase 2 was started by hand with `... 2` once phase 1 was down
# to its last 4 episodes, so the budget wasn't idle for their last hour.)
if [ "$PHASE" = 1 ]; then
python run.py go $COMMON --run-id pilot1 --only "$(ids go_kimi-k3-fireworks_pilot1)" \
    --max-concurrent 10 > outputs/logs/kimi_fireworks_rerun_go.log 2>&1 &
python run.py chess $COMMON --run-id pilot1 --only "$(ids chess_none_kimi-k3-fireworks_pilot1)" \
    --max-concurrent 20 > outputs/logs/kimi_fireworks_rerun_chess.log 2>&1 &
wait
fi

# Phase 2: prime_factorization. alignprompt1 (3) + extremealign2 (16) together,
# then selfreportcond1 (15).
python run.py prime_factorization $COMMON --run-id alignprompt1 --prompt-wrapper prompts/alignment_eval.md \
    --only "$(ids prime_factorization_kimi-k3-fireworks_alignprompt1)" --max-concurrent 10 \
    > outputs/logs/kimi_fireworks_rerun_pf_alignprompt.log 2>&1 &
python run.py prime_factorization $COMMON --run-id extremealign2 --prompt-wrapper prompts/extreme_alignment_eval.md \
    --only "$(ids prime_factorization_kimi-k3-fireworks_extremealign2)" --max-concurrent 20 \
    > outputs/logs/kimi_fireworks_rerun_pf_extremealign.log 2>&1 &
wait
python run.py prime_factorization $COMMON --run-id selfreportcond1 --self-report-from selfreport1 \
    --only "$(ids prime_factorization_kimi-k3-fireworks_selfreportcond1)" --max-concurrent 20 \
    > outputs/logs/kimi_fireworks_rerun_pf_selfreportcond.log 2>&1
