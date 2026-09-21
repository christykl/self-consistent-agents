# Qwen3-4B linear probe for o4-mini hacking: 4 rollouts per problem

Follow-up to the first probe run (see `SERVER_SETUP.md`). The first run used mostly one rollout per
problem and found no signal. This experiment tops every problem up to 4 rollouts, checks how much
problem-level structure there is in hacking, and reruns the probe.

**Result: still a null.** The probe does not beat the shuffled-features control for either `hack` or
`success`. Hacking *is* clustered by problem (so there is something to predict), but Qwen3-4B
last-layer mean-pooled prompt features do not linearly expose it.

Interpretation of results otherwise lives in `../FINDINGS.md` per repo convention; this file is the
record of this specific experiment.

## Question

Is o4-mini hacking (exec check = 1 and equation check = 0) predictable from Qwen3-4B's representation
of the task prompt alone? The first run (1800 rollouts, 1147 problems, 897 of them with a single
rollout) gave AUC 0.492 for `hack` vs a shuffled control of 0.471 ± 0.068. With only ~5% hack rate,
a single Bernoulli rollout is a very noisy label, so a null there was weak evidence. More rollouts
per problem reduce label noise and also make the per-problem metrics meaningful.

## Method

### 1. Top up rollouts

`scripts/make_topup.py` counts existing rollouts per problem (`target|numbers`) across the original
no-ask runs and writes eval-only problem files for the missing rollouts, shuffled with a fixed seed:

| File | Problems | Rollouts each | Total | Run ID |
|---|---|---|---|---|
| `data/countdown_topup_r3.jsonl` | 897 (had 1 rollout) | 3 | 2691 | `34c6bb39` |
| `data/countdown_topup_r2.jsonl` | 50 (had 2 rollouts) | 2 | 100 | `2c31bec7` |

Problems already at 4 or more rollouts (198 from the paired200 run, plus 2 odd ones) were skipped.

Same setup as the original no-ask runs: `openai/o4-mini` via OpenRouter, temperature 1, `eval_only:
true`, `ask_before_hacking: false`, `num_samples: 0`. Concurrency 40 (r=3) and 10 (r=2). Cost about
$70; the full set took roughly 2 hours.

```bash
python -m scripts.make_topup     # from environments/countdown_code, in an env where `probe` is importable
vf-eval countdown_code -m "openai/o4-mini" -b https://openrouter.ai/api/v1 -k OPENROUTER_API_KEY \
  -a '{"local_file": "data/countdown_topup_r3.jsonl", "num_samples": 0, "eval_only": true, "ask_before_hacking": false}' \
  -n 897 -r 3 -c 40 -T 1 --save-results
# and the same with countdown_topup_r2.jsonl, -n 50 -r 2
```

### 2. Labels

`probe/labels.py` now loads `ORIGINAL_RUNS + TOPUP_RUNS` (`NO_ASK_RUNS`) and **skips rollouts with an
`error` field**. Two rollouts in the r=3 run returned `EmptyModelResponseError` (no content); they
have exec=0 and eq=0, which the old loader would have counted as a legitimate failure. Skipping
them leaves the original counts unchanged (1800 rollouts, 1147 problems, 97 hacks).

Combined labels: **4589 rollouts on 1147 problems, 228 hacks (5.0%), 4212 legit solves (91.8%)**.
1143 problems have exactly 4 rollouts; 2 have 3 (the errored ones); 1 has 5 and 1 has 6.

### 3. Probe

Unchanged from the first run (`probe/probe.py`): L2 logistic regression on standardized 2560-dim
mean-pooled last-layer Qwen3-4B features of the user-message tokens, outer `GroupKFold(5)` over
problems, inner grouped 3-fold CV over C in {1e-4 ... 1} scored by AUC, and a shuffled-features
control (5 seeds). The features file (`features_qwen3_4b.npz`) is keyed by problem and did not need
regenerating. With 4 rollouts per problem, each problem's feature vector now appears with four
different labels, which acts as a soft label.

```bash
python -m probe.probe --features probe/features_qwen3_4b.npz | tee probe/out/probe_hack_qwen3_4b_4roll.txt
```

## Results

### Probe (grouped 5-fold CV, pooled out-of-fold predictions)

| Target | Positives / base rate | Probe AUC | Shuffled-control AUC | Probe Brier | Base-rate Brier | Per-problem corr |
|---|---|---|---|---|---|---|
| `hack` | 228 / 0.050 | 0.500 | 0.508 ± 0.031 | 0.049 | 0.047 | 0.023 |
| `success` | 4212 / 0.918 | 0.524 | 0.516 ± 0.025 | 0.087 | 0.075 | 0.036 |

Before (first run, mostly 1 rollout per problem): `hack` 0.492 vs 0.471 ± 0.068, `success` 0.417 vs
0.477 ± 0.054.

- Neither target beats the shuffled control, and both Brier scores are worse than always predicting
  the base rate.
- The control std for `hack` halved (0.068 to 0.031), so the null is tighter: an AUC of about 0.56
  or more would now be distinguishable from the control (roughly 2 sd).
- The first run's below-chance `success` AUC (0.417) was noise; it is now at chance.

### Structure of hacking across problems (1143 problems with exactly 4 clean rollouts)

Hack count per problem (0 to 4 of 4): 979, 113, 41, 9, 1.

| Statistic | Value |
|---|---|
| Problems with any hack | 14.3% |
| Problems with 2 or more hacks | 4.5% |
| Problems with a majority of hacks (3 or more) | 0.9% |
| Problems with all 4 hacked | 0.1% (1 problem) |
| Share of all hacks in the top 1% / 5% / 10% / 20% of problems | 15% / 53% / 78% / 100% |

- **Hacking is clustered, not iid.** Variance of the per-problem hack count is 0.288 vs 0.188
  expected if every rollout hacked independently at the pooled 4.9% rate (permutation test,
  p < 0.0001; 2000 shuffles). Under a binomial mixture the implied sd of the true per-problem hack
  probability is about 0.09. Compare iid expectations for counts 0 to 2: 933 / 194 / 15 vs observed
  979 / 113 / 41. The observed data has fewer singletons and more repeat-hackers.
- **Reliability.** Split-half correlation of hack counts (2 random rollouts vs the other 2) is 0.33,
  i.e. about 0.50 for a 4-rollout count (Spearman-Brown). This bounds how well any predictor can do
  against these labels. The same figure for legit-success counts is 0.41 (split-half).
- **Not confined to the hardest problems.** The top 5% of problems hold about half of the hacks, so
  hacking is concentrated but not limited to a tiny slice; 14% of problems have at least one hack.
- **Target size does not explain it.** Correlation of hack count with the target value is -0.066.
  In the earlier 198-problem subset, hack rate by target-size quartile rose slightly (5.0% to 7.1%);
  that did not hold up at 1143 problems.
- 20.8% of problems have at least one legitimate failure among their 4 rollouts.

### Class-imbalance check

Concern: with a 5% hack rate (and 92% success), is the probe just collapsing to "no hack" / "yes
success"? Checked by rerunning the same grouped CV with and without `class_weight="balanced"` and
reporting threshold-free and imbalance-robust metrics (pooled out-of-fold predictions, all 4589
rollouts).

`class_weight="balanced"` does **not** subsample. It keeps every rollout and reweights the loss so
each class contributes equally in total: weight = `n_samples / (n_classes * n_class_samples)`, i.e.
about 10.1 per hack rollout and 0.53 per non-hack rollout (`success`: 0.54 per success, 6.1 per
non-success). This is roughly equivalent to oversampling the minority class. It also shifts the
intercept, so the outputs are no longer calibrated probabilities (mean `hack` score 0.324 instead of
0.046); this does not affect AUC, which only uses the ranking.

| Target (base rate) | Setup | Pred std | AUC | Avg precision (chance = base rate) | Balanced acc (chance 0.5) | Positive rate in top-10% scored |
|---|---|---|---|---|---|---|
| `hack` (0.050) | default | 0.049 | 0.500 | 0.052 (0.050) | 0.503 | 0.050 |
| `hack` | balanced | 0.225 | 0.513 | 0.050 (0.050) | 0.494 | 0.046 |
| `success` (0.918) | default | 0.113 | 0.524 | 0.922 (0.918) | 0.506 | 0.922 |
| `success` | balanced | 0.254 | 0.512 | 0.920 (0.918) | 0.508 | 0.899 |

Chosen C per outer fold (inner-CV): `hack` default [1e-4, 1e-4, 1e-4, 1e-4, 1.0], `hack` balanced
[1e-4, 1e-4, 1e-2, 1e-4, 1.0], `success` default [1.0, 1e-4, 1e-2, 1e-3, 1.0], `success` balanced
[1.0, 1.0, 1e-3, 1e-4, 1.0].

- **Partly right:** accuracy at a 0.5 threshold is uninformative (0.948 for `hack` is just the
  majority class; only 0.3% of default `hack` predictions reach 0.5, 98% of default `success`
  predictions do). For `hack`, inner CV picked the strongest regularization (C = 1e-4) in 4 of 5
  folds, where the model outputs almost exactly the base rate.
- **But not a constant predictor:** default `hack` predictions range from 0 to 0.69 (std 0.049); the
  scores just carry no information.
- **Balancing does not reveal signal:** the predictions spread out (21% of `hack` predictions at or
  above 0.5, up from 0.3%), but AUC stays at 0.513, average precision equals the base rate, balanced
  accuracy is 0.494, and the top 10% of `hack` scores contain 4.6% hacks vs 5.0% overall.
  Imbalance is not what is hiding a signal; AUC does not depend on it.
- **Side effect worth knowing:** because inner CV picks a different C per fold when there is no
  signal, pooling out-of-fold scores mixes differently scaled probabilities. Per-fold AUC would be
  cleaner (not run); I do not expect it to change the conclusion.

## Interpretation

- There is real problem-level structure in o4-mini hacking (reliability about 0.5), so a null probe
  is not simply "hacking is random". Most of that structure is not linearly readable from
  mean-pooled last-layer Qwen3-4B features of the prompt.
- The `success` target, which was meant as a positive control for the pipeline, is also at chance. So
  this experiment does **not** show the pipeline can find signal on Countdown at all. In the
  predictive-contracts LeetCode work, `success` was clearly predictable (AUC about 0.75) while `hack`
  for the base model was not (0.495). The Countdown `success` null is the anomaly here.
- Plausible reasons (all untested): the prompt is a template plus four numbers and a target, so LM
  features may encode little arithmetic structure; difficulty for o4-mini may depend on things like
  solution rarity rather than surface features; and features come from Qwen3-4B while the labels are
  from a different model (o4-mini).
- A separate caveat on the "success vs hack" relationship: the two labels are mutually exclusive by
  construction, so comparisons like "hack rate given the other rollouts failed legitimately" are
  confounded. An earlier exploratory version of that table is not reported here for that reason.

## Caveats

- **Version mismatch between envs.** The top-up rollouts were run in a dedicated `countdown-eval`
  conda env with `verifiers==0.1.10` (matching `metadata.json` of every earlier run) installed with
  `pip install --no-deps -e .` to avoid `vllm`. The `openai` client there is 3.16.2, whereas
  `uv.lock` pins 2.15.0; I did not verify that this has no effect on requests. The probe runs in
  the separate `countdown-probe` env (verifiers 0.3.1), which is fine since it only reads results.
- `env_commit` in the new `metadata.json` files is HEAD (`170ee81`) while the tree was dirty (see
  CLAUDE.md gotcha). The environment code itself was unchanged.
- The original three runs and the top-up runs draw different rollouts of the same problems, but the
  original `dbc2e66b` and `39f39e60` used an unseeded split of `countdown_4num.jsonl`; problems are
  identified purely by `target|numbers`, so this does not matter for grouping.
- The concentration / reliability numbers and the class-imbalance check above came from inline
  analysis scripts that were not saved to the repo; only the probe output is in `probe/out/`.
- A 3-problem smoke test was run and its output directory deleted; it is not part of any results.

## Suggested next steps

1. **Hand-computed features as a positive control.** Brute-force each problem's number of valid
   solutions and the simplest solution's size; check whether they predict hack rate and success. If
   yes, hackability tracks solution rarity and the question becomes why LM features miss it. If no,
   the signal probably lives in o4-mini's own reasoning rather than the prompt.
2. Other layers or last-token pooling for the Qwen3-4B features.
3. Only after that, consider going to 8 rollouts per problem (reliability would rise from about 0.5
   to about 0.67).

## Files

- `scripts/make_topup.py`, `data/countdown_topup_r3.jsonl`, `data/countdown_topup_r2.jsonl`
- `outputs/evals/countdown_code--openai--o4-mini/34c6bb39/` (r=3) and `.../2c31bec7/` (r=2)
- `probe/labels.py` (`ORIGINAL_RUNS`, `TOPUP_RUNS`, error skipping)
- `probe/out/probe_hack_qwen3_4b.txt` (first run) and `probe/out/probe_hack_qwen3_4b_4roll.txt` (this run)
