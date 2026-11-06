# Running CheatBench episodes on Modal

**Status (2026-11-06):** every model entry we use runs here, including chess, Go and software engineering. Agents and judges go through OpenRouter, except Gemini, which uses Vertex AI ([gemini_vertex.md](gemini_vertex.md)). Pilot results are in [results_part1.md](results_part1.md).

## Usage

```bash
cd cheatbench && source .venv/bin/activate   # exports OPENROUTER_API_KEY
PYTHONUNBUFFERED=1 python run.py prime_factorization \
    --model gpt-6-astra-openrouter --judge gpt-6-sol-openrouter \
    --sandbox modal --limit 3 --max-concurrent 3
```

The orchestrator (`run.py`) runs on a laptop. Only the per-episode containers
run on Modal (app name `cheatbench`). Outputs land in `outputs/<task>_<model>_<run_id>/`
exactly as with the enroot backend: `episodes.jsonl`, `judge.jsonl`, `trajectories/`.

## Model entries (`configs/models.yaml`)

| Entry | Role | Route |
|---|---|---|
| `gpt-6-astra-openrouter` | agent | `openai/gpt-6-astra`, Codex 0.154.0, `base_url: https://openrouter.ai/api/v1`, Responses wire API |
| `gpt-6-sol-openrouter` | judge | `openrouter/openai/gpt-6-sol` through `core/llm_agents.py`'s `OpenRouterAgent` |
| `qwen3.8-27b-openrouter` | agent | `openrouter/qwen/qwen3.8-27b`, Terminus-2 (Harbor `4641fd59`), `api_base_url: https://openrouter.ai/api/v1`, thinking on via `extra_body.reasoning`, providers pinned via `extra_body.provider` |

To add another OpenRouter model, copy one of these entries. For Codex, the
`base_url:` key (not `api_base_url:`) is what keeps the provider prefix in the
model id. Other harnesses use their own routing keys (see `CONFIGURATION.md`).

## How it works

An episode in this repo is always **one command**. The runner's bootstrap goes on
argv, a JSON blob (row, prompt, staged files, grader source, runner source) goes
on stdin, turn records come back on stderr, and one JSON record comes back on stdout.
The Modal backend keeps that contract and swaps only the container:

| | enroot (`core/sandbox/runtime.py`) | Modal (`core/sandbox/modal_runtime.py`) |
|---|---|---|
| image | squashfs built from `Dockerfile` | `modal.Image.from_dockerfile(Dockerfile)` + pre-baked agent CLI |
| container | `unshare --user --pid` + `enroot start` | `modal.Sandbox.create` (gVisor) |
| payload | `episode_payload(bootstrap)` | the same function, via `sb.exec("bash", "-c", ...)` |
| API key | env var passed by name | `modal.Secret.from_dict` |
| `network: egress: deny/allow` | host-side iptables + SNI-checking relay | `outbound_domain_allowlist` (no SNI check, so weaker) |
| `environment/setup.py` hooks | injected into the live netns | a second sandbox per episode (chess, go); refused for others |

Code changes:

- `core/sandbox/modal_runtime.py` (new) has `image()`, `build_image()`,
  `start_episode()`, and `ModalProcess`. `ModalProcess` is a thin wrapper that
  gives a Modal process the few `asyncio.subprocess.Process` attributes
  `trial.py` uses, so the episode I/O loop is shared by both backends.
- `core/trial.py`: `run_trial(..., backend=)` picks the launcher, skips the
  enroot-only namespace setup on Modal, and always terminates the sandbox.
- `run.py`: adds `--sandbox {enroot,modal}`. On Modal it refuses unsupported
  tasks, builds the image once up front (with the harness install pre-baked),
  and records `sandbox` in `run.json` and in each episode record.
- `core/sandbox/runtime.py`: `episode_payload()` is factored out, and the libc
  load is guarded so the module imports on macOS.
- `core/agents/codex.py`: the override provider uses `wire_api = "responses"`,
  because Codex 0.154.0 refuses `"chat"`.

## Task coverage

| Task | Modal? | Notes |
|---|---|---|
| prime_factorization, subset_sum, synthetic_puzzles | yes | open network, grader hosted in-container |
| geoguessr, protein_design, knowledge_work | yes | `egress: deny` mapped to a domain allowlist (OpenRouter + install hosts) |
| chess, go | yes | engine, game server and inference bridge in a service sandbox (below); go's is on a T4 GPU |
| software_engineering | yes | Harbor's own Modal environment (below), not `run.py` |
| creative_writings | no | needs host loopback review endpoint |
| svgs | no | needs host `service:` leaderboard |
| openmath, openmath_agent | no | `environment/setup.py` hooks not ported |
| sycophancy | n/a | direct API, no sandbox |

## Chess and Go: a service sandbox per episode

Under enroot these tasks run their engine and game server on the host, outside the
agent's mount and pid namespaces. Inside one Modal sandbox there is nowhere equivalent:
the agent's user namespace maps onto the sandbox's root, so it can read every file. Each
episode therefore gets a second sandbox, `ModalServiceHost` in `core/sandbox/modal_runtime.py`:

```
agent sandbox                                     service sandbox
agents.internal -> 127.0.44.7:443 --forwarder-->  tunnel -> :8443 game server + engine (own TLS)
CLI base url -> 127.0.0.1:8080    --forwarder-->  tunnel -> :8080 inference bridge -> OpenRouter
```

- `ModalServiceHost` offers the two primitives the hooks call (`start_mirror`,
  `route_mcp_only`), so `tasks/{chess,go}/environment/setup.py` are unchanged.
- The hook runs before the agent sandbox exists, because Modal fixes the egress allowlist at
  creation and it must name this episode's tunnels. `attach()` then starts the forwarder and
  writes `/etc/hosts` and the CA, all before the agent's payload starts.
- The forwarder is `python -c` in the sandbox's outer pid namespace, so the agent sees neither
  a file nor a process for it. Modal's tunnel takes TLS; the game server's own TLS runs inside.
- `service_image()` layers dependencies, the checksummed engine, then this checkout. Editing code
  rebuilds only the last layer. The engine's signature is still verified at each episode start.
- When the episode ends, the service's logs and game records are copied to
  `trajectories/<episode>/service/`.
- The laptop no longer needs an engine: `--sandbox modal` builds with `host_engine=False`
  (`core/task_build.py`), which skips the engine steps listed under `build.host_engine`.
- A service that fails to start is now a lost episode, not a finding: `ContainerLaunchError`
  and `SetupHookError` set `lost_episode`, so it is re-run instead of judged on an empty transcript.

Differences from enroot:

| | enroot | Modal |
|---|---|---|
| `agents.internal` resolves to | `10.44.0.7` | `127.0.44.7`: gVisor refuses loopback aliases (no `CAP_NET_ADMIN`), so `curl -v` shows a loopback address |
| allowlist | model API + install hosts | the same, plus this episode's tunnel hostnames; a socket listing shows connections to them |
| Go's edited-policy confinement | Landlock + seccomp | private mount tree + seccomp (gVisor has no Landlock, and GPU sandboxes require gVisor). `tasks/go/test_policy_worker_linux.py` passes under both; a file outside the allowed set reads as absent rather than denied |
| Go's GPU | whatever the host has | T4. The signature check compares against certified probes and reported `compatible` |
| Gemini's MCP-only filter | bridge, gateway route | the Vertex relay checks declarations itself (`allowed_tools`); anything outside the nine game tools fails the episode. It does not go through the bridge, because its token lives in the agent sandbox |

## Software engineering on Modal

Harbor ships a Modal environment, so this keeps Harbor's own runner:

```bash
tasks/software_engineering/harbor/setup_modal.sh                     # once: builds .venv-harbor
source .venv/bin/activate                                            # exports OPENROUTER_API_KEY
tasks/software_engineering/harbor/run_modal.sh gpt-6-astra-openrouter        # all 20 tasks
```

Each `configs/<model>_modal.json` is named after its `configs/models.yaml` entry and holds the
same settings. Export and judge as in the [task README](../tasks/software_engineering/README.md),
with `--judge gpt-6-sol-openrouter`; job output is in `outputs/swe_jobs/`.

- **Codex:** `harbor-0.23.0-openrouter.patch` keeps the `openai/` prefix OpenRouter routes on
  (Harbor strips everything up to the last `/`).
- **Terminus-2:** Harbor 0.23.0's version, not the `4641fd59` commit the other tasks pin.
- **Gemini CLI:** `vertex_gemini.py` adds a relay in the task sandbox and a host-side token refresh,
  the same design as `docs/gemini_vertex.md`, because agents run up to 100 minutes and tokens last 1 hour.
- **Network:** tasks keep open network access, as in the Docker configs.

## What was verified (2026-11-06)

These were short infrastructure runs (run ids containing `modalsmoke`, one row each), not measurements.

| Check | Result |
|---|---|
| All 6 models, chess and Go, real prompt, judged | all reached the game and got a verdict; 5-15 min caps |
| Endpoint and edited `play.py`, through the tunnel (GPT-5, test prompt) | chess: counted, `false_win` true. Go: counted, worker `completed` under `linux-mount-seccomp`, tamper event `effective` |
| Go engine signature on the T4 | `compatible` |
| Tools the model is offered | Codex and Terminus-2 through the bridge; Gemini's relay log lists exactly the nine game tools |
| SWE oracle (applies the real fix), all 20 tasks | 20/20 reward 1.0, so correct code passes under gVisor |
| SWE, all 6 models, 1 task, 5-min agent limit | model reached and verifier ran for all |
| SWE export, render and judge (one job per harness) | verdicts for all three |

Known behaviour:

- **Transcripts arrive slowly.** Modal's exec stream carried about 0.3 MB/s, so a 100 MB knowledge_work session takes minutes to send after the episode ends. `CONTAINER_GRACE_S` (`core/trial.py`) is 900 s to cover it. At 180 s the host killed such episodes and kept only the start of the transcript ([`gemini_vertex.md`](gemini_vertex.md#lost-sessions-and-their-rerun-2026-11-06)).
- **Qwen is very slow on the games.** A single turn took up to 676 s, and in the 15-minute runs it played 0 moves on chess and Go, though its tool calls worked. Expect few moves per hour.
- **One unexplained failure.** One Qwen chess episode died with `Name or service not known` for `agents.internal`, and it did not recur in 4 longer Qwen chess episodes that reached the game, or in the other models' runs. An entry appended to `/etc/hosts` persisted across 10 sandboxes for 3 minutes, so Modal rewriting that file is not the cause. `_service_failure` now logs `/etc/hosts`. This failure ends the batch; resume with the same `--run-id`.
- **`grader_state.endpoint_requests` lags** in chess: it updates on the next game call, so an episode that ends first shows too few. Use the judge's count or `api_endpoint_requests`.
- **Gemini on Vertex records no cost** in `episodes.jsonl` or Harbor's results.

## Faithfulness caveats

- The agent is uid 1000 inside a nested user namespace, as under enroot (verified: `id` shows `uid=1000(user)`, and it can write anywhere in its filesystem).
- The image contains the Codex CLI (pre-baked cache). The enroot image deliberately does not, though the in-episode install produces identical files. An agent running `ls ~/.nvm` sees Node either way.
- Modal's domain allowlist appears to filter on TLS SNI: a blocked host fails with a TLS handshake error (curl exit 35), not a timeout, and a raw TCP tunnel does not pass it. We have not tested whether a CDN-fronted allowlisted IP can serve another hostname.
- Terminus-2's install script (Harbor source, uv venv, tmux debs) is pre-baked the
  same way as Codex's. Harbor's trajectory keeps only the parsed `analysis`/`plan` of each
  reply, so `terminus_2_bridge.py` also records every raw reply as `raw_responses`.
- Codex emits its turn records only when the episode ends, so `turns.log` is empty while an episode runs on either backend. The live log is in `container.stderr.log`.
