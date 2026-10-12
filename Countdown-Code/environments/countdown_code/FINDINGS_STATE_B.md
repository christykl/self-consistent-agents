# State B Findings: Large-Scale No-Ask Run (4-Rollout Pool)

Model: `openai/o4-mini` (via OpenRouter), temperature 1. Environment: `countdown_code`, run with `vf-eval`.
Overview, the hack definition and the dataset filter are in `FINDINGS.md`; the cross-condition
comparison on the paired 200-problem set is in `FINDINGS_STATE_A.md`.

**Scoring.** The numbers use the false-positive correction (re-scored 2026-09-25 by
`scripts/rescore_hacks.py`; method in `FINDINGS_STATE_A.md`, "False-positive correction"). **The probe experiments in `probe/` still use the raw label** (`probe.labels.load_rollouts`)
and have not been re-run.

## TL;DR

- Baseline hacking rate on the 1,143-problem no-ask pool (r=4): **3.5%** (162/4,589 rollouts; legit
  solves 93.2%). Raw: 5.0% (228), legit 91.8%, so 66 of 228 flagged hacks are correct solutions. This
  is consistent with the 5.0% on the 200-problem State A subset.
- Among failed no-ask rollouts, **49-61%** end in a hack regardless of how many of the problem's
  other rollouts passed (raw: 57-67%). Hacking tracks failing, not problem difficulty per se.
- Only no-ask exists here, so State B cannot measure any ask effect.

## Datasets and runs

**State B — no-ask 4-rollout pool**: 1,143 problems with exactly 4 no-ask rollouts each (4,589
rollouts in total: 162 hacks = 3.5%, 4,278 legit solves = 93.2%; raw label 228 = 5.0% and 4,212 = 91.8%). It is built by topping up the
original no-ask runs (`scripts/make_topup.py`); the 200 State A problems (198 at 4 rollouts
already) are part of it. Probe experiments live in `probe/PROBE_4ROLLOUT_RESULTS.md`.

| Run ID | Date | n × r | Dataset file | Condition | Role |
|---|---|---|---|---|---|
| `3fb9e8c3` | 2026-09-18 | 200 × 4 | `countdown_4num_paired200.jsonl` | no-ask | also State A no-ask baseline |
| `dbc2e66b` | 2026-09-17 | 200 × 1 | `countdown_4num.jsonl` (random split) | no-ask | original rollout |
| `39f39e60` | 2026-09-17 | 800 × 1 | `countdown_4num.jsonl` (random split) | no-ask | original rollout |
| `34c6bb39` | committed 2026-09-20 | 897 × 3 | `countdown_topup_r3.jsonl` | no-ask | top-up |
| `2c31bec7` | committed 2026-09-20 | 50 × 2 | `countdown_topup_r2.jsonl` | no-ask | top-up |

The top-up result files carry a later mtime (2026-09-23) than the commit that added them
(2026-09-20), so the commit date is used. The pass-count analysis was run 2026-09-23.

## Hack rate by per-problem pass count (State B: 4-rollout no-ask pool)

_Analysed 2026-09-23; re-scored with the false-positive correction 2026-09-25._

Problems bucketed by how many of their 4 no-ask rollouts were legit solves (exec=1 & eq=1). Uses
the 1,143 problems with exactly 4 rollouts (from the original + top-up runs, see "Datasets and runs"; 4 problems with
3/5/6 rollouts and errored rollouts excluded). A hack (exec=1 & eq=0) is never a pass, so a
bucket's hack rate is capped at (4 − passes)/4; the informative measure is therefore hacks as a
share of *failed* rollouts, i.e. hacks / (4 − passes) pooled over the bucket. The 931 problems with
4 passing rollouts have no failures (and 0 hacks) and are omitted.

| Bucket | Problems | Failed rollouts | Hacks | Hacks / failed rollouts | Raw: problems, hacks / failed |
|---|---|---|---|---|---|
| Problems with 3 passing rollouts | 136 | 136 | 66 | 48.5% | 139, 79/139 = 56.8% |
| Problems with 2 passing rollouts | 57 | 114 | 59 | 51.8% | 66, 79/132 = 59.8% |
| Problems with 1 passing rollout | 18 | 54 | 33 | 61.1% | 29, 58/87 = 66.7% |
| Problems with 0 passing rollouts | 1 | 4 | 2 | 50.0% | 4, 10/16 = 62.5% |

Reading: once a rollout fails, the chance it is a hack is ~49-61% regardless of how hard the
problem is. The hacks/4 rate rises steeply (12% → 26% → 46% → 50%), but that is mostly the
failure count rising, not a higher per-failure hacking propensity. The mild upward drift (49% →
61%) is suggestive only: the 1- and 0-pass buckets have just 54 and 4 failed rollouts and no
confidence intervals were computed. These are pooled rates and do not show whether hacking
concentrates in particular problems within a bucket.
