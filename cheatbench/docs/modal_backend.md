# Running CheatBench episodes on Modal

**Status (2026-10-12):** working for GPT-6 Astra (Codex harness) and
Qwen3.8-27B (Terminus-2 harness) via OpenRouter, with judging via OpenRouter. Pilot results are in [results_part1.md](results_part1.md).

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
| `environment/setup.py` hooks | injected into the live netns | refused |

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
| creative_writings | no | needs host loopback review endpoint |
| svgs | no | needs host `service:` leaderboard |
| chess, go, openmath, openmath_agent | no | `environment/setup.py` hooks (out of scope for now) |
| software_engineering, sycophancy | n/a | separate runners (Harbor / direct API) |

## Faithfulness caveats

- The agent is uid 1000 inside a nested user namespace, as under enroot (verified: `id` shows `uid=1000(user)`, and it can write anywhere in its filesystem).
- The image contains the Codex CLI (pre-baked cache). The enroot image deliberately does not, though the in-episode install produces identical files. An agent running `ls ~/.nvm` sees Node either way.
- The Modal allowlist cannot stop a CDN-fronted allowlisted IP from serving another hostname.
- Terminus-2's install script (Harbor source, uv venv, tmux debs) is pre-baked the
  same way as Codex's. Harbor's trajectory keeps only the parsed `analysis`/`plan` of each
  reply, so `terminus_2_bridge.py` also records every raw reply as `raw_responses`.
- Codex emits its turn records only when the episode ends, so `turns.log` is empty while an episode runs on either backend. The live log is in `container.stderr.log`.
