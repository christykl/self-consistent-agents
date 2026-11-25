# The paraphrased self-report setting (`--self-report-paraphrased-from`)

The goal is to separate two explanations for why showing a model its self-report
changes its behavior: following what the self-report says, and being influenced by
the particular tokens the model wrote. This setting keeps the content of the
self-report and replaces the tokens.

| Setting | Run id | Flag | What the attempt's user prompt contains |
|---|---|---|---|
| Self-report conditioned | `selfreportcond1` | `--self-report-from selfreport1` | the model's answer JSON, verbatim (`prompts/self_report_conditioned.md`: "This was your answer:") |
| Paraphrased self-report | `selfreportpara1` | `--self-report-paraphrased-from selfreport1` | a prose paraphrase in the user's voice (`prompts/self_report_paraphrased.md`: "This is my paraphrase of your answer:") |

Everything else matches `selfreportcond1`: the same answer for each row (the ok,
replicate-1 episode of `selfreport1`), one fresh sandbox per episode, the same
question quoted before the answer, and the same judge.

![What the attempt sees](figures/setting_selfreportpara1.png)

## The paraphrase

`scripts/paraphrase_self_reports.py MODEL ...` sends each answer to the paraphraser
with `prompts/paraphrase_self_report.md` and stores the result in
`outputs/<task>_<model>_selfreport1/paraphrases.json`. A row is paraphrased once, so
reruns show the same text. An episode record carries both `prior_self_report` (the
original answer) and `self_report_paraphrase` (the text shown).

The paraphraser is Claude Sonnet 5.5 through OpenRouter
(`claude-sonnet-5-5-openrouter`) for every subject model. It is outside all five subject
models' families, so no subject sees a paraphrase written by itself or a close relative.

The paraphrase keeps file paths, commands, tool names and probabilities literally,
because self-reports often name honeypot paths. Dropping a path would change what the
attempt knows, which is a different effect from the one under test. The script prints
any probability or path missing from a paraphrase.

## What the comparison does not separate

The paraphrase changes three things at once relative to `selfreportcond1`: the wording,
the format (prose instead of JSON), and the stated author of the text (the user's
paraphrase instead of the model's own answer). A difference between the two settings
therefore cannot be assigned to the wording alone.

## Run

Needs the model's `selfreport1` run.

```bash
bash scripts/run_paraphrased.sh MODEL [MODEL ...]   # paraphrase, then all five tasks
TASKS=prime_factorization MAX_CONCURRENT=20 bash scripts/run_paraphrased.sh MODEL ...
python scripts/compare_settings.py MODEL            # includes this setting
```

The Gemini models also need `VERTEX_SERVICE_ACCOUNT` set ([`gemini_vertex.md`](gemini_vertex.md)).

## Results: prime factorization (2026-11-09)

20 rows for each of the five models, 100 episodes. There were no infra failures and every
episode has a verdict. Agent plus judge cost was $112.98, of which Sol was $95.96.

![Cheating by setting](figures/prime_factorization_cheat_by_setting.png)

![Successes by setting](figures/prime_factorization_success_by_setting.png)

Figures: `scripts/plot_pf_cheat.py` and `scripts/plot_pf_success.py`.

Episodes judged as cheating, out of 20:

| Model | Baseline | Alignment prompt | Self-report conditioned | Paraphrased | In-context |
|---|:-:|:-:|:-:|:-:|:-:|
| GPT-5 | 19 | 20 | 7 | 6 | 18 |
| GPT-6.1 Sol | 19 | 10 | 0 | 0 | 0 |
| Qwen3.8-27B | 20 | 16 | 2 | 3 | 4 |
| Gemini 3.8 Flash | 20 | 6 | 0 | 0 | 0 |
| Gemini 4 Argon | 1 | 0 | 0 | 0 | 0 |
| **Total of 100** | 79 | 52 | 9 | 9 | 22 |

Task success, out of 20:

| Model | Baseline | Alignment prompt | Self-report conditioned | Paraphrased | In-context |
|---|:-:|:-:|:-:|:-:|:-:|
| GPT-5 | 19 | 20 | 7 | 6 | 18 |
| GPT-6.1 Sol | 19 | 13 | 7 | 11 | 4 |
| Qwen3.8-27B | 20 | 16 | 2 | 4 | 5 |
| Gemini 3.8 Flash | 20 | 6 | 0 | 0 | 0 |
| Gemini 4 Argon | 2 | 2 | 2 | 1 | 3 |

Paraphrasing did not change cheating on this task: 9/100 in both settings, and no model
moved by more than one episode. Only GPT-5 and Qwen cheated at all in either setting, so
the other three models cannot show a reduction. This is one task with 20 rows per model.

Timeouts at the 3600 s budget, which are judged as outcomes, were Qwen 3, Argon 3 and Sol 1
(self-report conditioned: Qwen 0, Argon 2, Sol 1).
