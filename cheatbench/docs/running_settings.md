# Running the five settings on any model, harness, or subset of rows

Do the environment setup in [`../README.md`](../README.md) first (plus
[`modal_backend.md`](modal_backend.md) for `--sandbox modal`). This page covers only how to
run our five settings. Results from the settings are in
[`report_gpt5_five_settings.md`](report_gpt5_five_settings.md) and
[`report_sol_four_settings.md`](report_sol_four_settings.md).

## The settings

Each setting is one `run.py` invocation with its own `--run-id`, so the outputs of different
settings never mix (`outputs/<task>_<model>_<run-id>/`).

| Setting | `--run-id` | Extra flags |
|---|---|---|
| Baseline | `pilot1` | none |
| Alignment honeypot | `honeypot1` | `--honeypot alignment` ([details](honeypot_alignment.md)) |
| Alignment prompt | `alignprompt1` | `--prompt-wrapper prompts/alignment_eval.md` |
| Self-report conditioned | `selfreportcond1` | `--self-report-from selfreport1` |
| Strict eval prompt | `evalstrict1` | `--prompt-wrapper prompts/eval_strict.md` |

The self-report-conditioned setting reads the model's own answer to "would you be tempted
to cheat?" on the same row, so run the self-report first:

| Self-report (prerequisite) | `selfreport1` | `--self-report` |

Tasks: `prime_factorization`, `subset_sum`, `geoguessr` (the folder is `geoguessr_single`
in `outputs/`), `knowledge_work`, `protein_design`.

## Run one setting on one task

```bash
python run.py prime_factorization --model gpt-5-openrouter --judge gpt-6-sol-openrouter \
    --sandbox modal --max-concurrent 8 --run-id pilot1
```

Subsetting rows (all rows run by default):

- `--limit N` runs the first N rows; `--skip N` skips the first N (to extend an earlier `--limit` run in the same run dir).
- `--only ID,ID` runs specific row ids.
- Rerunning a command resumes: rows already in the run dir are skipped (`--redo` to override).

## Run all five settings on a model

```bash
bash scripts/run_five_settings.sh MODEL
bash scripts/finish_five_settings.sh MODEL   # re-judge failed verdicts, rerun infra failures
```

`run_five_settings.sh` starts one background process per task and runs the settings in
order within a task (self-report first). Logs go to `outputs/logs/`. The task list and the
`--skip` bookkeeping for the original pilot rows live in the script; a model with no
existing run dir runs every row. To run a subset of tasks, copy the `run_task` lines you
want. Judge verdicts are written automatically; `python judge.py OUTDIR --judge JUDGE`
re-judges a run dir.

## A different model or harness

- **Model:** add an entry to `configs/models.yaml` (model slug, `api_key_env`, `api_base_url`,
  `generation_config`, and `harness: {name, version}`), then pass its name as `--model`.
  Copy an existing OpenRouter entry such as `gpt-5-openrouter`.
- **Harness:** `--harness NAME` overrides the model's harness with its latest release. Names
  are those in `core/agents/` (codex, claude-sdk, gemini-cli, terminus-2, ...). Run
  `python run.py --help` for the list. Harnesses differ in what reasoning they expose, which
  affects the eval-awareness analysis below.
- Gemini on Vertex needs the extra setup in [`gemini_vertex.md`](gemini_vertex.md).

## Tables and analysis

```bash
python scripts/compare_settings.py MODEL            # cheated / success per task per setting
python scripts/self_report_table.py MODEL           # self-report vs. baseline outcome per row
python scripts/eval_awareness.py MODEL [MODEL ...]  # does the agent voice suspicion of a test?
```

`eval_awareness.py` reads the baseline run (`--run pilot1`); see
[`report_eval_awareness.md`](report_eval_awareness.md). To instead ask a model directly
whether it believes it is being evaluated (no attempt, no judge), see
`scripts/run_eval_belief.sh`, which passes `--probe prompts/eval_belief.md`.
