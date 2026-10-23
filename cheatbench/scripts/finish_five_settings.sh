#!/usr/bin/env bash
# Finish an interrupted run_five_settings.sh sweep: re-judge verdicts that failed
# (e.g. OpenRouter 402), then rerun every baseline row whose latest record is missing or
# an infra failure (anything but ok or timeout; a timeout is a final, judged outcome),
# then re-judge again. A run dir that does not exist yet runs every row.
#
#     bash scripts/finish_five_settings.sh MODEL
#
# Logs: outputs/logs/finish_five_settings_<model>_<task>.log
set -u
cd "$(dirname "$0")/.."
MODEL=$1
JUDGE=gpt-6-sol-openrouter
COMMON="--model $MODEL --judge $JUDGE --sandbox modal --max-concurrent ${MAX_CONCURRENT:-8}"
RUNS="selfreport1 pilot1 honeypot1 alignprompt1 selfreportcond1 extremealign1"

rejudge() {
    for run_id in $RUNS; do
        out=outputs/${1}_${MODEL}_${run_id}
        [ -f "$out/episodes.jsonl" ] && python judge.py "$out" --judge $JUDGE
    done
}

run_task() {
    task=$1; dir=$2
    rejudge "$dir"
    for spec in "selfreport1|--self-report" \
                "pilot1|" \
                "honeypot1|--honeypot alignment" \
                "alignprompt1|--prompt-wrapper prompts/alignment_eval.md" \
                "selfreportcond1|--self-report-from selfreport1" \
                "extremealign1|--prompt-wrapper prompts/extreme_alignment_eval.md"; do
        run_id=${spec%%|*}; flags=${spec#*|}
        out=outputs/${dir}_${MODEL}_${run_id}
        [ -f "$out/run.json" ] && [ ! -f "$out/run_pilot.json" ] && cp "$out/run.json" "$out/run_pilot.json"
        only=""
        if [ -f "$out/episodes.jsonl" ]; then
            # Rows of the (complete) baseline run that have no final record here: failed or never started.
            only=$(python -c "import json,sys; L={}; [L.update({r['episode']: r}) for r in map(json.loads, open(sys.argv[1]))]; final={r['id'] for r in L.values() if r['ok'] or r['failure'] == 'timeout'}; print(','.join(sorted({json.loads(l)['id'] for l in open(sys.argv[2])} - final)))" "$out/episodes.jsonl" "outputs/${dir}_${MODEL}_pilot1/episodes.jsonl")
            [ -z "$only" ] && { echo "=== $task $run_id: nothing to rerun"; continue; }
            only="--only $only"
        fi
        echo "=== $task $run_id $(date) $only"
        python run.py "$task" $COMMON --run-id "$run_id" --skip 0 $only $flags --no-progress
    done
    rejudge "$dir"
}

export PYTHONUNBUFFERED=1
mkdir -p outputs/logs
for td in prime_factorization:prime_factorization subset_sum:subset_sum geoguessr:geoguessr_single \
          knowledge_work:knowledge_work protein_design:protein_design; do
    run_task ${td%%:*} ${td#*:} > outputs/logs/finish_five_settings_${MODEL}_${td%%:*}.log 2>&1 &
done
wait
