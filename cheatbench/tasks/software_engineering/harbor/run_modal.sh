#!/bin/bash
# Run SWE-bench Pro on Modal: run_modal.sh MODEL [harbor run flags...]
# MODEL is a configs/MODEL_modal.json, named after its configs/models.yaml entry.
#   run_modal.sh gpt-6-astra-openrouter                  # all 20 tasks
#   run_modal.sh qwen3.8-27b-openrouter -l 1 --job-name smoke
# Needs OPENROUTER_API_KEY, or VERTEX_SERVICE_ACCOUNT and ADC for the Gemini entries.
set -euo pipefail
cd "$(dirname "$0")/../../.."
model=$1; shift
export PYTHONPATH=$PWD   # for vertex_gemini.py's import_path
exec .venv-harbor/bin/harbor run -c "tasks/software_engineering/harbor/configs/${model}_modal.json" -o outputs/swe_jobs "$@"
