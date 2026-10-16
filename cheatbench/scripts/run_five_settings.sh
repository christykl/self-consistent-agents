#!/usr/bin/env bash
# Run one model in the five settings on every row of the six pilot tasks.
#
#     bash scripts/run_five_settings.sh [MODEL]    # default gpt-6.1-sol-openrouter
#
# The four pilot settings (and the self-reports that the self-report-conditioned
# setting reads) already hold the first 2-3 rows of each task, so those runs are
# extended with --skip (the pilot's --limit) into the same run dir. The strict
# eval prompt setting is new and runs every row. One background process per task,
# settings in order within a task (self-reports before the conditioned run).
# Logs: outputs/logs/five_settings_<task>.log
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
                "evalstrict1|--prompt-wrapper prompts/eval_strict.md"; do
        run_id=${spec%%|*}; flags=${spec#*|}
        skip=$pilot_rows; [ "$run_id" = evalstrict1 ] && skip=0
        # run.py rewrites run.json; keep the pilot's copy.
        out=outputs/${dir}_${MODEL}_${run_id}
        [ -f "$out/run.json" ] && [ ! -f "$out/run_pilot.json" ] && cp "$out/run.json" "$out/run_pilot.json"
        echo "=== $task $run_id (skip $skip) $(date)"
        python run.py "$task" $COMMON --run-id "$run_id" --skip "$skip" $flags --no-progress
    done
}

export PYTHONUNBUFFERED=1
run_task prime_factorization prime_factorization 3 > outputs/logs/five_settings_prime_factorization.log 2>&1 &
run_task subset_sum subset_sum 3 > outputs/logs/five_settings_subset_sum.log 2>&1 &
run_task geoguessr geoguessr_single 2 > outputs/logs/five_settings_geoguessr.log 2>&1 &
run_task synthetic_puzzles synthetic_puzzles 2 > outputs/logs/five_settings_synthetic_puzzles.log 2>&1 &
run_task knowledge_work knowledge_work 2 > outputs/logs/five_settings_knowledge_work.log 2>&1 &
run_task protein_design protein_design 2 > outputs/logs/five_settings_protein_design.log 2>&1 &
wait
