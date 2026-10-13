## Background

The goal in this research project is to train language models that write
probabilistic "contracts" that constrain their behavior before undertaking
agentic solutions to problems. Concretely, suppose we have a task ("write a
function that does [...] and passes the tests in `tests`") and some enumerated
set of behaviors ("I will modify files in `src`", "I will modify files in
`tst`", etc.), we would like the model to first generate a spec of the form:

p(modify `src`) = 0.95
p(modify `tst`) = 0.05
p(access network) = 0.01

and then proceed when a user has approved the spec.

Our ultimate goal is safety: given that a model may take a risky action while
operating autonomously, we would like it to articulate that probability before
acting, and then act in such a way that the probability reflects a calibrated
prediction about its behavior.

We are motivated that the hypothesis that models are generally well-aligned at
the beginning of interactions, and if asked _a priori_ about the appropriateness
of specific reward-hacking behaviors (like modifying tests), they are able to
recognize them as inappropriate; only once they begin attempting a task (and
perhaps especially after trying and failing to perform it legitimately) does
their willingness to take inappropriate actions (and perhaps even their ability
to recognize such actions as inappropriate) increase.

This project has three components. The first two components are empirical:
measuring the extent to which off-the-shelf mdoels indeed exhibit changes in
alignment as their interactions proceed, and measuring the extent to which this
can be mitigated by explicit up-front commitments to use or avoid particular
strategies. The final component is experimental: we perform reinforcement
learning with a loss function that encourages consistency between models'
predicted and executed behaviors, and then measure whether this further
mitigates hacking relative to baseline behavior.
## Environment

### Local venv

`cheatbench/.venv` (gitignored) holds Python 3.11 with `pip install -e '.[build,svgs]'`
plus `modal` (1.6.1). The OPENROUTER_API_KEY is exported as an env var on activation, and modal has already been authenticated.

### Modal

We plan to use Modal for (a) running the CheatBench eval and (b) later training.
Findings from the docs (verify before relying on any single number; several
details come from secondary sources):

**Why the stock runtime doesn't port.** CheatBench episodes run in an
Enroot container wrapped in `unshare --user --net --pid`, with squashfuse,
fuse-overlayfs, slirp4netns and host-side iptables (`core/sandbox/runtime.py`,
`egress.py`). That needs user namespaces and FUSE on the host, which we
shouldn't assume inside a Modal sandbox. On Modal, the sandbox *is* the
container, so the right move is a new sandbox backend rather than nesting
Enroot. The episode contract (one container per row, runner/task/grader
streamed in rather than baked into the image, anonymous image, agent runs as
non-root uid 1000, ephemeral filesystem) maps onto Modal naturally.

**Mapping to Modal Sandboxes.**
- `modal.Sandbox.create(app=..., image=..., timeout=..., cpu=..., memory=..., block_network=..., outbound_domain_allowlist=..., workdir="/workspace")`; run commands with `sb.exec(...)` (supports `timeout`, `workdir`, `env`, `secrets`, `text`). Stdin is `sb.stdin` (a `StreamWriter`), not an `exec` argument, so streaming the runner on stdin needs either `sb.filesystem.write_text` / `copy_from_local` then exec, or a small writer on `sb.stdin`.
- Image: `modal.Image.from_dockerfile("Dockerfile")` reuses our existing repo-root Dockerfile (`python:3.11-slim`, linux/amd64). The adapter-installed CLIs (nvm/Node/claude-code, 33 s cold start) can be pre-baked as extra `.run_commands(...)` layers; Modal caches layers, and `Image.build` + `Image.from_name` gives fast sandbox starts.
- Lifetime: default 5 min; `timeout=` up to 24 h (episode budgets are 900-3600 s, fine). `idle_timeout` is available.
- Network: `block_network=True` drops all egress (cannot combine with allowlists); `outbound_domain_allowlist` / `outbound_cidr_allowlist` give by-name / by-CIDR allowlists (they are additive, DNS stays open). This is the natural replacement for our `network:` block / `egress.py` for tasks that declare one, but it does not do SNI/Host-header checking as `egress_relay.py` does, so a CDN-fronted allowlisted IP could serve other sites; treat Modal's allowlist as weaker until tested. The API host (OpenRouter) must be on the allowlist.
- Secrets: pass keys via `modal.Secret.from_dict`/`from_name` (never in argv).
- Services injected by `environment/setup.py` hooks (chess, go, openmath, openmath_agent) currently use `EpisodeSandbox` primitives (mirror servers on :443, `/etc/hosts` edits, loopback aliases). These need either a second sandbox/function reachable over a Modal Tunnel or port, or running the service inside the same sandbox; this is the main per-task porting cost. Tasks with no hook (creative_writings, knowledge_work, protein_design, geoguessr, svgs, prime_factorization, subset_sum) should port first.
- Runtimes: `runtime="gvisor"` (default; syscalls in userspace, may break exotic tools) or `runtime="vm"` (own kernel; Docker, FUSE, nested cgroups). **GPU sandboxes require gVisor; the VM runtime does not support GPUs.** VM sandboxes went GA around 2026-10-01 per a third-party source; the older `experimental_options={"vm_runtime": True}` spelling may still appear in docs.
- Snapshots: `sb.snapshot_filesystem()` / `snapshot_directory()` return Images, useful for pre-building a per-task state or restoring past the 24 h limit.
- Cost/limits (secondary sources): per-second billing, no idle charge; sandbox CPU is billed at a higher rate than function CPU (~3x). Team plan concurrency ~5,000 containers (Starter 100) and 50 concurrent GPUs (Starter 10); no documented sandbox creation-rate limit found.

**Harness options.**
- Terminus-2 (what we'd use for Qwen) goes through Harbor, which already ships a Modal environment (`--env modal`; named-session sandbox, 24 h timeout, `sleep infinity` keepalive, CPU/memory limits, `type:count` GPUs, domain/CIDR allowlists, Dockerfile build, file copy via tar). That is the lowest-effort path for Terminus-2 episodes; I could not confirm exact flags from official Harbor docs, so check `harbor run --help`.
- CLI harnesses (codex, claude-sdk, etc.): run the CLI inside the sandbox via `sb.exec`, with the model API reached through OpenRouter (allowlisted). Add a `modal` runtime next to `enroot` in `core/sandbox/` selected by a flag, leaving `trial.py` logic unchanged.
- Orchestration: run `run.py` (the orchestrator, which only makes API calls and spawns sandboxes) from a laptop or a CPU-only Modal function; only the per-episode containers need to be on Modal. Judges also go through OpenRouter, so no GPU is needed for evaluation unless we self-host a Qwen model (then: a Modal `@app.cls(gpu="H100")` vLLM server exposed as a web endpoint, and point the model client's `api_base_url` at it).

**What was actually built (2026-10-12), and what we learned doing it.**
- `python run.py TASK --model gpt-6-astra-openrouter --judge gpt-6-sol-openrouter --sandbox modal --limit N` runs episodes in Modal Sandboxes from a laptop (macOS works). Backend: `core/sandbox/modal_runtime.py`; `trial.py`/`run.py` branch on `--sandbox {enroot,modal}`. See `docs/modal_backend.md`.
- The enroot privilege drop (`DROP_SETUP` + `unshare --user --map-user=1000 --pid --fork --mount-proc`) works unchanged under gVisor, so both backends share `runtime.episode_payload()`: agent is uid 1000 and can still write anywhere in its filesystem. Stdin streaming via `proc.stdin.write` + `write_eof` + `drain` works.
- `core/sandbox/runtime.py` used to load `libc.so.6` at import time, which made `run.py` unimportable on macOS; now guarded by `sys.platform == "linux"`.
- Codex 0.154.0 rejects `wire_api = "chat"` ("no longer supported"). OpenRouter now serves the Responses API (`/api/v1/responses`), so the codex `base_url:` provider block now uses `wire_api = "responses"` (`core/agents/codex.py` `OVERRIDE_WIRE_API`). The `openai/` prefix is kept in the model slug on this path, which is what OpenRouter routes on.
- Judges: use the existing `openrouter/` provider class (`model: openrouter/openai/gpt-6-sol`, `api_key_env: OPENROUTER_API_KEY`); no base URL needed.
- `Image.run_commands` turns each string into one Dockerfile `RUN` line, so a multi-line install script must be passed base64-encoded. The adapter's own install script is pre-baked this way (installs Node+Codex under `/home/user`), and the in-episode `check || install` then reports "runtime already present".
- A Sandbox created without a command lives until `timeout`, so `ModalProcess.close()` terminates it after every episode. If the orchestrator is killed, sandboxes leak until timeout; there is no `modal sandbox` CLI command in 1.6.1, so clean up with `modal.Sandbox.list(app_id=modal.App.lookup("cheatbench").app_id)` + `.terminate()`.
- `trial.py` polls `proc.returncode` while the episode runs (asyncio sets it on exit), so the Modal process wrapper must watch for exit in a background task, or the episode hangs until its timeout.
- Besides setup-hook tasks, `--sandbox modal` also refuses tasks needing host-loopback services: `creative_writings` (review endpoint) and `svgs` (`service:` leaderboard). Verified working on Modal (pilot 1, 15 episodes, 0 infra errors): prime_factorization, subset_sum, synthetic_puzzles, geoguessr, protein_design, knowledge_work. The last three use `egress: deny`, mapped to a Modal domain allowlist; knowledge_work builds its own `tasks/knowledge_work/Dockerfile` on Modal. geoguessr's host-side build needs `exiftool` (`brew install exiftool`).
- The Modal client sometimes logs "Cannot retrieve the exit status for exec ... Retrying" during long episodes; it recovered every time in pilot 1. `Sandbox.list` lags termination: a listed sandbox whose `poll()` returns 137 is already dead.
- Qwen3.8-27B (`qwen3.8-27b-openrouter`) is served on OpenRouter, so no Modal hosting is needed. It runs in Terminus-2, which runs unchanged on Modal. DeepInfra (the bf16 provider) returned upstream 429s that killed episodes, so the entry routes to Alibaba (precision undisclosed), then Parasail/CoreWeave (fp8), with `allow_fallbacks: false`. It is therefore not bf16, and the serving provider per request is not recorded. Thinking is on via `extra_body.reasoning.enabled`, and LiteLLM returns it as `reasoning_content`. Harbor drops any text outside a reply's JSON object, so `terminus_2_bridge.py` keeps `raw_responses`. In zsh, `set -- $var` does not word-split; use a bash script for launch loops.
- macOS has no `timeout` command; set `PYTHONUNBUFFERED=1` when redirecting `run.py` output to a file, or the banner is buffered.

**Training (Part 3).**
- Single-node multi-GPU only: `gpu="H100:8"` per container (up to 8 for H100/H200/B200/A100; >2 GPUs means longer queueing). Multi-node clusters exist but were private beta / newly launched; ask Modal before depending on them.
- Modal has official GRPO examples to copy from: TRL + vLLM (`gpu="H100:2"`, trainer on one GPU, vLLM on the other, with reward computed in Modal Sandboxes with `block_network=True`) and verl (Ray, 2x H100). Rollouts here are expensive multi-turn agent episodes, so the shape should be: GPU container runs trainer + inference server; each rollout is a CPU gVisor sandbox started from the GPU container that runs the agent against the policy endpoint; reward (task success + cheating judge + Brier on declared capabilities) is computed from the episode record. Since sandboxes can't have GPUs and don't need them, this split is natural.
- Persist checkpoints, episode records and results in a `modal.Volume`. Copy results back to the repo.
- The Modal constraints (24 h max per container/sandbox, session preemption) mean training needs periodic checkpoint-and-resume.

## Implementation and documentation

Provide a high-level description of all code and experimental results to date as
markdown files in a `docs` folder.

In general I will request modifications to the overall plan via the chat
interface. If any of these requests don't make sense, contradict instructions
elsewhere, or seem incorrect / ill-advised, please stop and ask a question
before proceeding.

**Important**: this is research code, so it is very important to prioritize
clarity and pedagogy over industrial-strength robustness. Favor minimal (or no)
exception handling, and minimize the number of abstraction layers wherever
possible.

**Important**: please do not suggest (and especially initiate!) follow-up
questions, new experiments, etc.---these clutter the chat window and make it
difficult to determine what's been done so far. When I want help brainstorming
next steps, I will ask explicitly.

## Part 1: Do failed agentic interactions cause models to become misaligned?

We'd like to be able to do this with multiple models/harnesses in multiple environments,
so write your code in an extensible way (while paying attention to the note
above about writing easy-to-read research code!)

For starters I would like to look at the [CheatBench](https://www.cheatbench.ai/) tasks in this directory. Set up the infra needed to run GPT-6 Astra and the smallest Qwen3/3.8 model that can meaningfully attempt at least some subset of the tasks. (See `../notes/qwen3-4b-cheatbench` for why Qwen3-4b is insufficient for these tasks.) We will be using OpenRouter to interface with all models/judges (although a small enough Qwen model can be hosted on Modal if not available on OpenRouter). Implement a modular model client class to handle this so that collaborators can easily run the same benchmark with different harnesses. We just want to get a feel for model behavior on these tasks and don't need to run the entire benchmark yet. We can skip any task categories that are infeasible with our harness or infra heavy to set up (e.g. software engineering) for now.

Additionally, for every test task, ask the agent (in a separate conversation from the attempt rollout) given the task instructions and environment, whether it would ever be tempted to cheat. 

[Don't run anything below until we're done with Part 1. The
instructions may change depending on the outcome of those experiments! But do
architect the codebase in a way that will make implementing parts 2 and 3 easy.]

## Part 2: do pre-commitments cause models to become better aligned?

Just a re-run of part 1, but with a prompt where models are first instructed to
reason about the task and list the capabilities they will and won't use. This
list should persist as part of the conversation transcript as agents proceed to
reason through solutions to the task. Measure the same set of outcome metrics.

## Part 3: learning to generate better commitments

The idea here is basically to apply the methodology in the RLCR paper
(https://arxiv.org/pdf/2507.16806) but with two important modifications: (1) the
predictions are generated *before* the agent begins to act, and (2) prediction
correctness is judged w/r/t the agent's own actions rather than some external
source of ground truth. Here the "capabilities" should include all the behaviors
that would count as cheating, some benign behaviors that the agent doesn't need to
use, and some benign behaviors that the agent almost certainly needs to use.
Use a combined task success + Brier reward as in that paper.  (To compute
rewards, use the datasets' native cheating measurements + whatever code you need
to write to check for the presence of benign actions). I would also like to
experiment with a "hard" variant of RLCR in which models just say "yes" or "no"
to the set of used capabilities, and get a reward of -0.5 if they say yes but
don't use a capability, and a reward of -1 if they say no but do use a
capabiity.

Evaluate models thus trained as in Parts 1 and 2.
