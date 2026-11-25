#!/usr/bin/env bash
# Kimi K3 (Fireworks, Kimi Code) self-reports on every chess and go row
# (`--self-report`, run ID selfreport1; prompts/self_report.md).
#
#     bash scripts/run_kimi_fireworks_selfreports.sh
#
# 18 + 10 = 28 of the 30-episode kimi-k3-fireworks budget (configs/models.yaml),
# leaving 2 for a smoke run alongside. Go stays at 10 (Modal's GPU limit).
# `set -m`: a background run.py gets its own process group, so `kill -INT <pid>`
# stops it cleanly. Watch with:
#     python scripts/watch_throttling.py outputs/{chess_none,go}_kimi-k3-fireworks_selfreport1
set -u -m
cd "$(dirname "$0")/.."
COMMON="--model kimi-k3-fireworks --judge gpt-6-sol-openrouter --sandbox modal --no-progress --no-auto-retry --self-report --run-id selfreport1"
mkdir -p outputs/logs
export PYTHONUNBUFFERED=1
python run.py chess $COMMON --max-concurrent 18 > outputs/logs/kimi_fireworks_chess_selfreport.log 2>&1 &
python run.py go $COMMON --max-concurrent 10 > outputs/logs/kimi_fireworks_go_selfreport.log 2>&1 &
wait
