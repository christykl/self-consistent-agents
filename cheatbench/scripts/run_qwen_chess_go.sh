#!/usr/bin/env bash
# Qwen3.8-27B (OpenRouter, Terminus-2) on every row of chess (30) and go (20),
# default setting (run id pilot1).
#
#     bash scripts/run_qwen_chess_go.sh
#
# Fireworks was considered first, but it lists Qwen3.8-27B (qwen3p8-27b) only for
# dedicated deployments, not serverless (2026-11-25), so the model stays on OpenRouter.
#
# Concurrency matches the Kimi K3 launch (scripts/run_kimi_fireworks.sh): chess 20 + go 10
# = 30 episodes at once. Go stays at 10 because each go episode holds a T4 service
# sandbox (Modal allows 10 GPUs). No cap is set on the model entry.
#
# --no-auto-retry: run.py's automatic pass would rerun `rate_limit` failures straight
# back into any throttling. `set -m` gives each background run.py its own process group,
# so `kill -INT <pid>` stops it cleanly.
#
# Watch for 429s and failed records while it runs:
#     python scripts/watch_throttling.py outputs/chess_none_qwen3.8-27b-openrouter_pilot1 outputs/go_qwen3.8-27b-openrouter_pilot1
# Logs: outputs/logs/qwen_openrouter_<task>.log
set -u -m
cd "$(dirname "$0")/.."
COMMON="--model qwen3.8-27b-openrouter --judge gpt-6-sol-openrouter --sandbox modal --no-progress --no-auto-retry --run-id pilot1"
mkdir -p outputs/logs
export PYTHONUNBUFFERED=1

python run.py go $COMMON --max-concurrent 10 > outputs/logs/qwen_openrouter_go.log 2>&1 &
python run.py chess $COMMON --max-concurrent 20 > outputs/logs/qwen_openrouter_chess.log 2>&1 &
wait
