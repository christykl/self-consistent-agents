# CLAUDE.md

Project-specific harness notes for this repo. Experimental results and their interpretation live in
`environments/countdown_code/FINDINGS.md` — keep findings there and harness mechanics here.

> Do not put project notes in `environments/AGENTS.md`. That file is a verbatim mirror of the
> upstream Verifiers "Environments" documentation and is meant to be re-syncable; local edits there
> would be lost and would pollute the mirror.

## `countdown_code` environment

Working directory for everything below: `environments/countdown_code/`. All paths in the commands
are relative to it, and the venv is `environments/countdown_code/.venv`.

```bash
cd environments/countdown_code && source .venv/bin/activate
```

### Local env-args added to `load_environment`

`countdown_code/countdown_code.py` has two env-args beyond the upstream template. Both default to
`False`, so omitting them reproduces the original single-turn, random-split behavior.

#### `ask_before_hacking: bool = False`

When `True`, `load_environment` returns `AskBeforeHackingEnv` (a `vf.MultiTurnEnv` subclass with
`max_turns=2`) instead of `vf.SingleTurnEnv`:

- **Turn 1** — the model is asked `ASK_BEFORE_HACKING_PROMPT`, a yes/no question about whether it
  would be tempted to weaken the test or fabricate a result. `process_example_ask_before_hacking`
  puts this in `prompt` and stashes the real task in `info["task_prompt"]`.
- **Turn 2** — `env_response` returns `state["info"]["task_prompt"]` as a user message, i.e. the
  unmodified countdown-code task.

The rollout `completion` is therefore `(assistant, user, assistant)`. Scoring is unaffected because
`extract_model_response` in `reward_fns.py` reads `completion[-1]`, which is the task answer.

#### `eval_only: bool = False`

When `True`, the loaded dataset is used directly as **both** train and eval set with no
`train_test_split`.

This exists because the default `train_test_split` is **unseeded** and re-randomizes on every
`load_environment` call, so two `vf-eval` invocations draw different problems even from the same
`local_file`. That makes matched/paired comparisons across conditions impossible. With `eval_only`,
the eval set is exactly the rows of `local_file` in file order — verified deterministic across
repeated invocations.

Use `eval_only: true` for any paired or repeated-measures comparison. Use the default split for
independent-sample runs.

### Data files and the scripts that build them

| File | Rows | Built by | Notes |
|---|---|---|---|
| `data/countdown_4num.jsonl` | 3000 | `scripts/make_4num_split.py` (seed 42) | 4-number problems sampled from `Jiayi-Pan/Countdown-Tasks-3to4` |
| `data/countdown_4num_paired200.jsonl` | 200 | `scripts/make_paired_200.py` (seed 777) | Fixed set for paired runs; drawn separately from the 4-number pool |

Both scripts are one-shot — the outputs are on disk and reused. Re-run only to regenerate. Note the
two sets are independent draws from the same pool, so a small incidental overlap is possible (4 rows
between the current two files).

### Example usage

Set the key from the environment, not inline on the command line (see Gotchas):

```bash
export OPENROUTER_API_KEY=...   # or: source .env
```

**Baseline, no-ask** (independent random split):
```bash
vf-eval countdown_code -m "openai/o4-mini" -b https://openrouter.ai/api/v1 -k OPENROUTER_API_KEY \
  -a '{"local_file": "data/countdown_4num.jsonl", "num_samples": 0, "test_size": 0.4, "ask_before_hacking": false}' \
  -n 1000 -r 1 -c 20 -T 1 --save-results --debug
```

**Ask-before-hacking** — same command with `"ask_before_hacking": true`.

**Paired fixed-set run** (identical problems in both conditions, `r=4` rollouts each; run once per
condition, flipping the boolean):
```bash
vf-eval countdown_code -m "openai/o4-mini" -b https://openrouter.ai/api/v1 -k OPENROUTER_API_KEY \
  -a '{"local_file": "data/countdown_4num_paired200.jsonl", "num_samples": 0, "eval_only": true, "ask_before_hacking": <bool>}' \
  -n 200 -r 4 -c 20 -T 1 --save-results --debug
```

`num_samples: 0` disables the sub-sampling step in `load_environment`; pass it whenever using
`local_file`, otherwise the default of 50,000 applies.

Results land in `outputs/evals/countdown_code--openai--o4-mini/<run_id>/` as `results.jsonl`,
`metadata.json` and `eval.log`.

### Gotchas when running and reading evals

- **`results.jsonl` is appended in completion order**, not example order (blocks of `r` rollouts per
  example). Two runs' raw partial files are not row-comparable.
- **`metadata.json` holds running averages over completed rollouts only.** Its `avg_metrics` are not
  final until the row count reaches `n × r`. Do not quote them while a run is in flight.
- **To read a partial run safely**, restrict to `example_id`s that have all `r` rollouts complete in
  *both* runs being compared. Because `eval_only` preserves file order and the files are pre-shuffled
  at build time, that subset is an unbiased sample.
- **`env_commit` in `metadata.json` is just git HEAD**, not the working-tree state. Runs made from a
  dirty tree all report the same commit, so metadata alone cannot tell you which code produced which
  run. Commit before launching a run worth keeping.
- **Never pass the API key inline** on the `vf-eval` command line — it becomes readable in `ps aux`
  to any local process. Export it or source a gitignored `.env`.
- Check remaining OpenRouter budget with
  `curl https://openrouter.ai/api/v1/auth/key -H "Authorization: Bearer $OPENROUTER_API_KEY"`.
  Use `/auth/key`, not `/api/v1/credits` — the latter reports account-wide totals rather than this
  key's limit.

### Linear probe (`environments/countdown_code/probe/`)

Predicts o4-mini hacking (exec=1 & eq=0) on the no-ask runs (`dbc2e66b`, `39f39e60`, `3fb9e8c3`) from
mean-pooled last-layer Qwen3-4B features of the task prompt. Setup and run instructions for a GPU node: `environments/countdown_code/probe/SERVER_SETUP.md`
(avoid `pip install -e .` there — the core deps include `vllm`).

```bash
python -m probe.features --out probe/features_qwen3_4b.npz   # GPU, one pass per distinct problem
python -m probe.probe --features probe/features_qwen3_4b.npz # CPU, grouped-CV logistic regression
```

Rollouts are grouped by problem (`target|numbers`) so duplicates across runs never straddle CV folds.
