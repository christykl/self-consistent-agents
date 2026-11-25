#!/usr/bin/env bash
# The paraphrased self-report setting (`selfreportpara1`) on every row of the
# five tasks, for each MODEL given:
#
#     bash scripts/run_paraphrased.sh MODEL [MODEL ...]
#     TASKS=prime_factorization MAX_CONCURRENT=20 bash scripts/run_paraphrased.sh MODEL ...
#
# Same setup as `selfreportcond1`, but the attempt prompt carries a paraphrase of
# the self-report in the user's voice (docs/self_report_paraphrased.md). The
# paraphrases are generated first and reused on reruns. One background process
# per (model, task), each with --max-concurrent 8. Rerunning resumes: rows with
# an ok record are skipped.
# Logs: outputs/logs/selfreportpara1_<model>_<task>.log
set -u
cd "$(dirname "$0")/.."
export PYTHONUNBUFFERED=1
mkdir -p outputs/logs
TASKS=${TASKS:-prime_factorization subset_sum geoguessr knowledge_work protein_design}
python scripts/paraphrase_self_reports.py "$@" --tasks ${TASKS/geoguessr/geoguessr_single} || exit 1
for MODEL in "$@"; do
    for task in $TASKS; do
        python run.py "$task" --model "$MODEL" --judge gpt-6-sol-openrouter --sandbox modal \
            --max-concurrent ${MAX_CONCURRENT:-8} --run-id selfreportpara1 \
            --self-report-paraphrased-from selfreport1 \
            --no-progress > "outputs/logs/selfreportpara1_${MODEL}_${task}.log" 2>&1 &
    done
done
wait
