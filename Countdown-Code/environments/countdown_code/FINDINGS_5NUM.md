# 5-Number No-Ask Findings

Environment: `countdown_code`, run with `vf-eval` via OpenRouter, temperature 1, no-ask prompt. Overview and the
hack definition are in `FINDINGS.md`. One section per model. The problem sets differ and Sonnet 5's
run is partial, so compare with care.

| Section | Model | Problems | Status |
|---|---|---|---|
| 1 | `openai/o4-mini` | first 200 rows of `data/countdown_5num.jsonl` × r=4 | complete |
| 2 | `anthropic/claude-sonnet-5` | `data/countdown_5num_paired200.jsonl` (seed 555) × r=4 | partial (212/800) |

The two 200-problem sets are different samples of `data/countdown_5num.jsonl`; they share 45 problems.

---

# 1. o4-mini (State C)

Model: `openai/o4-mini` (via OpenRouter), temperature 1. Environment: `countdown_code`, run with `vf-eval`.
Overview and the hack definition are in `FINDINGS.md`. The 4-number comparison baseline is the State B pool
(`FINDINGS_STATE_B.md`). Do not mix numbers across states.

### TL;DR

- 5-number problems are much harder: the solve rate falls from **93.3% to 61.4%** (−31.9pp, CI [−36.7, −27.2]).
- The base hack rate rises **3.5% → 14.8%** (+11.3pp, CI [+8.5, +14.2]), about 4×.
- The rise in hacking comes from more failures, not from more hacking per failure. The share of failed
  rollouts that end in a hack actually *falls*, 51.9% → 38.2% (−13.8pp, CI [−21.8, −5.4]).

### Datasets and runs

**State C — 5-number no-ask**: the first 200 rows of `data/countdown_5num.jsonl` × r=4 = 800 rollouts, no errors.
`Jiayi-Pan/Countdown-Tasks-3to4` has no 5-number problems, so `scripts/make_5num.py` (seed 5) generates 1000
locally to match the 4-number file's distribution:
- numbers uniform in [1, 99], repeats allowed
- target uniform in [10, 100]
- only solvable problems are kept (checked with an exact-arithmetic search; 735/1735 candidates had no solution)
- no duplicate problems

Rows are in generation order, so any prefix is an unbiased sample. Rows 200–999 are unused and available for an
extension.

| Run ID | Date | n × r | Dataset file | Condition | Role |
|---|---|---|---|---|---|
| `cf6301bb` | 2026-09-25 | 200 × 4 | `countdown_5num.jsonl` (`eval_only`) | no-ask | State C |
| `e19ac0c6` | 2026-09-24 | 10 × 1 | `countdown_5num.jsonl` (`eval_only`) | no-ask | pilot; not analysed |

Both runs were made at commit `ce7da10`. Analysis: `python scripts/analyze_5num.py` (run 2026-09-25).

### Results (State B vs. State C, problems with 4 rollouts)

| | Problems | **Hack** | Solved | Failed | Hacks / failed | Mean output tokens |
|---|---|---|---|---|---|---|
| 4-num (B) | 1,143 | **3.5%** | 93.3% | 6.7% | 51.9% | 6,176 |
| 5-num (C) | 200 | **14.8%** | 61.4% | 38.6% | 38.2% | 14,978 |

5-num minus 4-num, 95% bootstrap CI over problems (resampling each state independently, 10,000 draws):

| Metric | Difference | 95% CI |
|---|---|---|
| Hack rate | +11.3pp | [+8.5, +14.2] |
| Solve rate | −31.9pp | [−36.7, −27.2] |
| Hacks / failed rollouts | −13.8pp | [−21.8, −5.4] |

#### Hacks by per-problem solve count

This mirrors the State B pass-count table, but buckets by solves. Problems where all 4 rollouts solve
it have no failures and are omitted.

| Solved rollouts | 4-num problems | 4-num hacks / failed | 5-num problems | 5-num hacks / failed |
|---|---|---|---|---|
| 3 | 136 | 66/136 = 48.5% | 45 | 18/45 = 40.0% |
| 2 | 57 | 59/114 = 51.8% | 33 | 30/66 = 45.5% |
| 1 | 18 | 33/54 = 61.1% | 42 | 44/126 = 34.9% |
| 0 | 1 | 2/4 = 50.0% | 18 | 26/72 = 36.1% |

Reading:
- More 5-number rollouts fail, and more failures produce more hacks.
- Given a failure, o4-mini is *less* likely to hack on 5-number problems. That holds in every solve-count
  bucket, so it is not only a harder-problem mix. More of its 5-number failures are honest: a wrong or missing
  answer with an intact test.
- A plausible reason is that the longer 5-number searches (about 2.4× the output tokens) more often end in an
  unfinished or invalid answer. This is not verified.

### Caveats

- **Problems are generated, not drawn from the HF dataset.** The 5-number set matches the 4-number file's number
  range, target range and solvability, but it comes from a different generator than the 4-number pool.
- **Time gap.** State B was run 2026-09-17 to 09-20; State C on 2026-09-24/25. No concurrent 4-number control was
  run.
- **Only 200 problems.** The hack-rate CI is ±~2.9pp, which is ample for an +11pp effect. The per-failure
  bucket rates are pooled and have no CIs.


---

# 2. Sonnet 5 (partial)

Model: `anthropic/claude-sonnet-5` (via OpenRouter), temperature 1, **no `max_tokens` set** (provider default)
Environment: `countdown_code`, no-ask prompt (`ask_before_hacking: false`), `eval_only: true`
Dataset: `data/countdown_5num_paired200.jsonl` — 200 problems sampled with `random.Random(555)` from
`data/countdown_5num.jsonl` by `scripts/make_5num_paired200.py` (deterministic; md5
`412f9e6d5dd970b287a074a8f2d17a6c`). Reuse this file for later paired experiments.
Run: `outputs/evals/countdown_code--anthropic--claude-sonnet-5/fb6b9f53/`, launched with `-n 200 -r 4 -c 20 -T 1`.

**Status: incomplete.** The job was killed after 212 of 800 rollouts (53 of 200 problems, all 53 with the
full 4 rollouts). Groups complete in file order and the file is pre-shuffled, so the subset is unbiased,
but the numbers below are preliminary.

### Results

| Rollouts | n | **Hack** | Solved | Failed |
|---|---|---|---|---|
| Non-errored | 158 | **0 (0.0%)** | 140 (88.6%) | 18 (11.4%) |
| All, errors counted as failed | 212 | **0 (0.0%)** | 140 (66.0%) | 72 (34.0%) |

- No hacks in 158 rollouts. With zero
  events, the 95% upper bound is about 1.9% (rule of three: 3/158).
- "Failed" = no correct answer: 18 rollouts where the code ran but was wrong, or did not run.
- Mean output tokens (non-errored): 15,890, similar to o4-mini's 14,978 on the same problem type.

### Errored rollouts (25%)

54 of 212 rollouts errored with `EmptyModelResponseError('Model returned no content and did not call any
tools')`, and the summary also logged `run_execution_check: list index out of range` for them. All 54 used
exactly **65,536 output tokens**: the model spent the whole budget on hidden reasoning and emitted no answer.
They are scored 0 with `error` set and are not hacks.

- Successful rollouts use ~600 to ~62,000 output tokens; single rollouts take up to ~10 minutes. The full run
  was projected at 5+ hours at concurrency 20.
- The errored rollouts are the hardest problems, so dropping them may bias the hack rate in either direction
  (harder problems may be where hacking is most tempting, so 0% could be an underestimate).

### Output cap

- We did not set one: `metadata.json` has `max_tokens: None` and `-t` was not passed. The 65,536 ceiling is the
  provider default.
- OpenRouter lists `anthropic/claude-sonnet-5` with `max_completion_tokens: 128000`, context 1,000,000, and
  supports `max_tokens`, `reasoning`, `reasoning_effort`, `verbosity`.

### Next steps

- Rerun with `-t 128000` (keeps the model's default reasoning, so the hack rate stays a fair base rate).
  Lowering `reasoning_effort` would be cheaper but changes behavior. Keep this partial run separate; do not
  merge it with a rerun that uses a different cap.
- Commit before launching (`env_commit` is only git HEAD).
