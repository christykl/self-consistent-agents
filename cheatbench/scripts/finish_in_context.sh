#!/usr/bin/env bash
# Finish an interrupted run_in_context.sh sweep (`incontext1`): rerun every row whose
# latest record is an infra failure (anything but ok or timeout, plus a "timeout"
# whose error is an OpenRouter 402), then judge every episode still without a
# verdict (e.g. ones whose judge call hit the 402).
#
#     bash scripts/finish_in_context.sh MODEL [MODEL ...]
#
# One background process per (model, task) with rows to rerun. A timeout is a final,
# judged outcome, as in finish_five_settings.sh.
# Logs: outputs/logs/finish_incontext1_<model>_<task>.log
set -u
cd "$(dirname "$0")/.."
export PYTHONUNBUFFERED=1
JUDGE=gpt-6-sol-openrouter
mkdir -p outputs/logs

for MODEL in "$@"; do
    for task in prime_factorization subset_sum geoguessr knowledge_work protein_design; do
        dir=$task; [ "$task" = geoguessr ] && dir=geoguessr_single
        out=outputs/${dir}_${MODEL}_incontext1
        only=$(python -c "
import json, sys
last = {}
for line in open(sys.argv[1]):
    if line.strip():
        r = json.loads(line); last[r['episode']] = r
credits = lambda r: '402' in (r.get('error') or '')
print(','.join(sorted(r['id'] for r in last.values()
                      if not r['ok'] and (r['failure'] != 'timeout' or credits(r)))))" "$out/episodes.jsonl")
        [ -z "$only" ] && continue
        echo "=== $MODEL $task: rerun $only"
        python run.py "$task" --model "$MODEL" --judge $JUDGE --sandbox modal \
            --max-concurrent ${MAX_CONCURRENT:-8} --run-id incontext1 \
            --self-report-in-context-from selfreport1 --only "$only" \
            --no-progress > "outputs/logs/finish_incontext1_${MODEL}_${task}.log" 2>&1 &
    done
done
wait

for MODEL in "$@"; do
    for dir in prime_factorization subset_sum geoguessr_single knowledge_work protein_design; do
        python judge.py "outputs/${dir}_${MODEL}_incontext1" --judge $JUDGE
    done
done
