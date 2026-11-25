#!/usr/bin/env bash
# Rerun the 3 Qwen3.8-27B chess/Go episodes lost to infra on 2026-11-25
# (docs/qwen_chess_go.md): chess PNMjr and FBLBF (an MCP call hung past Terminus-2's
# old 60 s timeout, recorded as "timeout after 3600s"), Go ogs_64055438_m52 (service
# sandbox shut down).
#
#     bash scripts/rerun_qwen_chess_go.sh
#
# --redo --only: same run id; new records append to episodes.jsonl and supersede the
# old ones (latest wins). The failed attempts' trajectories were moved to
# <run>/trajectories_infra_20261125/ first.
set -u -m
cd "$(dirname "$0")/.."
COMMON="--model qwen3.8-27b-openrouter --judge gpt-6-sol-openrouter --sandbox modal --no-progress --no-auto-retry --redo --run-id pilot1"
mkdir -p outputs/logs
export PYTHONUNBUFFERED=1

python run.py chess $COMMON --only PNMjr,FBLBF --max-concurrent 20 > outputs/logs/qwen_openrouter_rerun_chess.log 2>&1 &
python run.py go $COMMON --only ogs_64055438_m52 --max-concurrent 10 > outputs/logs/qwen_openrouter_rerun_go.log 2>&1 &
wait
