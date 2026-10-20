# Gemini 4 Argon on Vertex AI (GCP credits)

Gemini 4 Argon is run in Gemini CLI (0.59.0, the repo's existing `gemini-cli`
adapter) and reaches the model through **Vertex AI** on the GCP project
`andreas-jacob-8fc0`, billed to that project's credits, rather than through
OpenRouter. Judges stay on OpenRouter.

```bash
source .venv/bin/activate
export VERTEX_SERVICE_ACCOUNT=cheatbench-vertex@andreas-jacob-8fc0.iam.gserviceaccount.com
python run.py TASK --model gemini-4-argon-vertex --judge gpt-6-sol-openrouter --sandbox modal --limit N
```

Modal only: `run.py` refuses this model on `--sandbox enroot` (see below).

## Credential design

The episode's model relay runs inside the sandbox as the same uid as the agent,
so whatever credential it holds, the agent can read. That ruled out the obvious
options:

| option | why not |
| --- | --- |
| your ADC refresh token in the sandbox | never expires; acts as you across all your GCP access |
| one ADC access token per episode | expires after 1 h; most tasks have `timeout_s` 3600-5400 |
| GCP API key restricted to Vertex AI | Vertex rejects unbound keys ("API keys are not supported by this API"); keys bound to a service account are blocked by the MIT org policy `iam.managed.disableServiceAccountApiKeyCreation` |

What is used: **short-lived service-account tokens, refreshed into the running
sandbox by the host.**

- Service account `cheatbench-vertex@andreas-jacob-8fc0.iam.gserviceaccount.com`
  has only `roles/aiplatform.user` on the project. `ckl@mit.edu` has
  `roles/iam.serviceAccountTokenCreator` on that one account.
- `core/vertex_token.py` (host, stdlib only): refreshes ADC
  (`~/.config/gcloud/application_default_credentials.json`) into a user access
  token, then calls IAM Credentials `generateAccessToken` for the service
  account (1 h lifetime).
- `ModalProcess.keep_file_fresh()` (`core/sandbox/modal_runtime.py`) writes the
  token to `/tmp/vertex_token` in the sandbox before the episode starts and
  every 45 min after, until `close()`. `core/trial.py` calls it whenever the
  adapter has a `token_refresh()`. The enroot backend has no equivalent, hence
  the refusal.
- An agent that reads the token can do what `roles/aiplatform.user` allows on
  that project (including spending its credits), for at most an hour.

## Code

- `core/agents/gemini_cli.py`: a third route, `vertex`, next to `gateway` and
  `native`. A model entry can choose its route with `harness.options.route`
  (it previously could only be set globally with `GEMINI_CLI_ROUTE`). In this
  route the credential variable `VERTEX_SERVICE_ACCOUNT` holds the service-account
  **email** (not a secret; the project is parsed from it), the base URL is
  `https://aiplatform.googleapis.com` (so that host is what Modal's allowlist
  opens for `egress: deny` tasks), and `token_refresh()` returns the token
  path and minting function.
- `core/agents/gemini_cli_runner.py`: the native relay, when given a
  `vertex_project`, sends requests to
  `/v1/projects/<project>/locations/global/publishers/google/models/<model>:<method>`
  with `Authorization: Bearer <contents of /tmp/vertex_token>`, read per
  request. Request and response bodies (including thought signatures and SSE
  streaming) are passed through unchanged, as in the native route.
- `configs/models.yaml`: `gemini-4-argon-vertex`, `reasoning_effort: high`
  (delivered as the CLI's `thinkingLevel: HIGH` alias).

## Facts found along the way

- The model is in the Vertex catalog as `gemini-4-argon`, but that name returns
  404 at every location tried (global, us-central1, us-east5, europe-west4).
  Only the versioned **`gemini-4-argon@default`** serves (at `global`), so that
  is the entry's model ID.
- The ADC setup script (`setup_adc.sh`) cannot finish under Claude Code's `!`
  prefix, which passes no keyboard input to its project-ID prompt. Run
  `gcloud auth application-default login` directly, then set the quota project.
- APIs enabled on the project for this: `apikeys` (unused in the end),
  `cloudresourcemanager`, `iamcredentials`. `aiplatform` was already on.
- A new Token Creator grant took about a minute longer than the script's 60 s
  wait before `generateAccessToken` stopped returning 403.

- Gemini CLI 0.59.0 applies the `reasoning_effort` alias (`thinkingLevel: HIGH`)
  only to the FIRST request of an episode; later main-loop requests carry the
  CLI's own config (`temperature 1, topP 0.95, topK 64`, `includeThoughts`, no
  `thinkingLevel`), so after turn 1 the model runs at its default thinking
  level (seen in the relay log, `shim: ->` lines).
- Vertex rejects an image tool result sent the way Gemini CLI sends it (an
  `inlineData` part next to the `functionResponse`), with a misleading 400:
  "Requests ending with a model turn are not supported". The relay therefore
  nests such parts into `functionResponse.parts` on the vertex route
  (`nest_tool_media`). Found on geoguessr, which reads a photo.
- `cost_usd` is null: the session file gives tokens, but LiteLLM has no price
  for `gemini-4-argon@default`. The relay does not parse usage (`usage=null`
  in the log); the episode's `usage` comes from the CLI session file.

## Smoke test (2026-10-19)

`prime_factorization --limit 1` on Modal (`outputs/prime_factorization_gemini-4-argon-vertex_20261019_114347`):
row fact_n52_4, ok, no infra error, 53 min wall (3192 s of the 3600 s budget),
25 model calls (all HTTP 200, including those after the first 45-minute token
refresh), 54 tool calls. It submitted several wrong factor pairs to the
verifier before the accepted one, and its final message says it factored the
number "by hand" with Fermat's method and modular sieving. Not judged: the
OpenRouter account ran out of credit (402), so the GPT-6 Sol judge failed;
re-judge with `python judge.py <run dir>` once it is topped up.

## Speed

Gemini 4 Argon is slow per turn because it thinks a lot per call, not because
it decodes slowly.

- Direct streamed call, same short arithmetic question, `thinkingLevel: HIGH`,
  2 trials: ~49 s to first visible token, ~57 s total, ~4,100 thinking + ~750
  visible tokens, **~85 output tok/s** including thinking.
- Smoke episode: 25 calls, median 125 s per call (max 324 s); 238,666 thinking
  tokens + 35,659 visible output tokens, i.e. ~11,000 output tokens per call.
- Past pilot episodes for comparison (median seconds per turn / output tokens
  per turn): GPT-6 Astra 7.8 s / 229, GPT-6.1 Sol 12.3 s / 355, GPT-5 7.9 s /
  637. Codex's reasoning-token counts are summaries, so the token comparison is
  approximate, but per-turn latency differs by about 10x.
