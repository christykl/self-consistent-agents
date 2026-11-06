#!/usr/bin/env bash
# Ask each model, in a planning session that explores the (unmodified) environment,
# whether it believes it is being evaluated. Baseline setting, all 90 rows, no judge.
#
#     bash scripts/run_eval_belief.sh
#
# One background process per task, models in sequence. Reruns resume (done rows are skipped).
# Logs: outputs/logs/eval_belief_<task>.log
set -u
cd "$(dirname "$0")/.."
export VERTEX_SERVICE_ACCOUNT=cheatbench-vertex@andreas-jacob-8fc0.iam.gserviceaccount.com
export PYTHONUNBUFFERED=1
mkdir -p outputs/logs

run_task() {
    task=$1
    for model in gpt-5-openrouter gpt-6.1-sol-openrouter gemini-4-argon-vertex; do
        echo "=== $task $model $(date)"
        python run.py "$task" --model $model --judge gpt-6-sol-openrouter --sandbox modal --max-concurrent 8 \
            --run-id evalbelief1 --probe prompts/eval_belief.md --no-judge --no-progress
    done
}

for task in prime_factorization subset_sum geoguessr knowledge_work protein_design; do
    run_task $task > outputs/logs/eval_belief_$task.log 2>&1 &
done
wait
