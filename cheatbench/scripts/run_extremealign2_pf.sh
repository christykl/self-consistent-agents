#!/usr/bin/env bash
# The revised extreme alignment prompt (prompts/extreme_alignment_eval.md, 2026-11-20 version)
# on all 20 prime_factorization rows, three models at once, 20 episodes each in parallel.
# Run id extremealign2 keeps these apart from extremealign1 (the earlier prompt text).
#     bash scripts/run_extremealign2_pf.sh
# Logs: outputs/logs/extremealign2_<model>_prime_factorization.log
set -u
cd "$(dirname "$0")/.."
source .venv/bin/activate
mkdir -p outputs/logs
export PYTHONUNBUFFERED=1
for model in gpt-5-openrouter gpt-6.1-sol-openrouter qwen3.8-27b-openrouter; do
    python run.py prime_factorization --model $model --judge gpt-6-sol-openrouter --sandbox modal \
        --max-concurrent 20 --run-id extremealign2 \
        --prompt-wrapper prompts/extreme_alignment_eval.md --no-progress \
        > outputs/logs/extremealign2_${model}_prime_factorization.log 2>&1 &
done
wait
