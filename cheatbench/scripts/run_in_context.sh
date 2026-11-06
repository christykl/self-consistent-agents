#!/usr/bin/env bash
# The in-context self-report setting (`incontext1`) on every row of the five
# tasks, for each MODEL given:
#
#     bash scripts/run_in_context.sh MODEL [MODEL ...]
#
# Each attempt continues the history [self-report prompt, answer JSON] rebuilt
# from the model's `selfreport1` run (docs/self_report_in_context.md): one
# sandbox per episode. One background process per (model, task), each with
# --max-concurrent 8. Rerunning resumes: rows with an ok record are skipped.
# Logs: outputs/logs/incontext1_<model>_<task>.log
set -u
cd "$(dirname "$0")/.."
export PYTHONUNBUFFERED=1
mkdir -p outputs/logs
for MODEL in "$@"; do
    for task in prime_factorization subset_sum geoguessr knowledge_work protein_design; do
        python run.py "$task" --model "$MODEL" --judge gpt-6-sol-openrouter --sandbox modal \
            --max-concurrent ${MAX_CONCURRENT:-8} --run-id incontext1 \
            --self-report-in-context-from selfreport1 \
            --no-progress > "outputs/logs/incontext1_${MODEL}_${task}.log" 2>&1 &
    done
done
wait
