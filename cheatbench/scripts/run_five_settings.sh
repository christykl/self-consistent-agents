#!/usr/bin/env bash
# Run one model in the five settings on every row of five pilot tasks
# (synthetic_puzzles dropped after the Sol sweep).
#
#     bash scripts/run_five_settings.sh [MODEL]    # default gpt-6.1-sol-openrouter
#
# The four pilot settings (and the self-reports that the self-report-conditioned
# setting reads) already hold the first 2-3 rows of each task, so those runs are
# extended with --skip (the pilot's --limit) into the same run dir; settings with
# no existing run dir (a new model) run every row. The extreme
# alignment prompt setting is new and runs every row. One background process per task,
# settings in order within a task (self-reports before the conditioned run).
# Logs: outputs/logs/five_settings_<model>_<task>.log
set -u
cd "$(dirname "$0")/.."
MODEL=${1:-gpt-6.1-sol-openrouter}
COMMON="--model $MODEL --judge gpt-6-sol-openrouter --sandbox modal --max-concurrent 8"
mkdir -p outputs/logs

run_task() {
    task=$1; dir=$2; pilot_rows=$3
    for spec in "selfreport1|--self-report" \
                "pilot1|" \
                "honeypot1|--honeypot alignment" \
                "alignprompt1|--prompt-wrapper prompts/alignment_eval.md" \
                "selfreportcond1|--self-report-from selfreport1" \
                "extremealign1|--prompt-wrapper prompts/extreme_alignment_eval.md"; do
        run_id=${spec%%|*}; flags=${spec#*|}
        out=outputs/${dir}_${MODEL}_${run_id}
        skip=$pilot_rows; [ "$run_id" = extremealign1 ] && skip=0
        # A model with no pilot run dir (e.g. gpt-5-openrouter) runs every row.
        [ -d "$out" ] || skip=0
        # run.py rewrites run.json; keep the pilot's copy.
        [ -f "$out/run.json" ] && [ ! -f "$out/run_pilot.json" ] && cp "$out/run.json" "$out/run_pilot.json"
        echo "=== $task $run_id (skip $skip) $(date)"
        python run.py "$task" $COMMON --run-id "$run_id" --skip "$skip" $flags --no-progress
    done
}

export PYTHONUNBUFFERED=1
run_task prime_factorization prime_factorization 3 > outputs/logs/five_settings_${MODEL}_prime_factorization.log 2>&1 &
run_task subset_sum subset_sum 3 > outputs/logs/five_settings_${MODEL}_subset_sum.log 2>&1 &
run_task geoguessr geoguessr_single 2 > outputs/logs/five_settings_${MODEL}_geoguessr.log 2>&1 &
run_task knowledge_work knowledge_work 2 > outputs/logs/five_settings_${MODEL}_knowledge_work.log 2>&1 &
run_task protein_design protein_design 2 > outputs/logs/five_settings_${MODEL}_protein_design.log 2>&1 &
wait
