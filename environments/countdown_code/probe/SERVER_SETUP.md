# Server setup + run: Qwen3-4B linear probe for o4-mini hacking

Instructions for the agent on the A100 node. Goal: create a conda env, extract Qwen3-4B prompt
features (GPU, ~minutes), then fit the probe (CPU) and report the numbers.

All commands run from `environments/countdown_code/` of the repo checkout. Labels come from the
committed eval runs in `outputs/evals/countdown_code--openai--o4-mini/` (no API key or new rollouts needed).

## 1. Create the env (conda 26.1.1)

```bash
cd <repo>/environments/countdown_code
conda create -n countdown-probe python=3.11 -y
conda activate countdown-probe

# Torch with CUDA. Match the node's driver: check `nvidia-smi` (CUDA version, top right).
# cu124 works for driver CUDA >= 12.4; use cu121 / cu126 if the driver is older / newer.
pip install torch --index-url https://download.pytorch.org/whl/cu124
pip install transformers scikit-learn numpy "datasets>=4.5.0" verifiers
```

Do **not** run `pip install -e .` or `pip install -e '.[probe]'`: the project's core dependencies
include `vllm`, which is heavy and not needed here. `probe/features.py` only imports
`countdown_code.countdown_code` (needs `datasets` and `verifiers`), which resolves because you run
from `environments/countdown_code/` (cwd is on the path with `python -m`).

Sanity check:

```bash
python -c "import torch, transformers, sklearn, verifiers, datasets; print(torch.__version__, torch.cuda.is_available(), torch.cuda.device_count())"
python -c "from probe.labels import load_rollouts; r=load_rollouts(); print(len(r), len({x[0] for x in r}), sum(x[3] for x in r))"
```

Expected: `cuda.is_available()` is `True`; second command prints `1800 1147 97`
(rollouts, distinct problems, hacks). If the counts differ, stop and report — the labels are wrong.

## 2. Extract features (GPU, one A100 is enough)

Qwen3-4B (~8 GB in bf16) downloads from Hugging Face on first use. If the node has no internet, ask
the user to place the model locally and pass `--model /path/to/Qwen3-4B`. To keep the cache off a small
home disk: `export HF_HOME=/path/with/space/hf`.

```bash
CUDA_VISIBLE_DEVICES=0 python -m probe.features --batch-size 16 --out probe/features_qwen3_4b.npz
```

`features.py` uses a single device; multiple GPUs are not needed. Expect about 1147 problems in a few
minutes. It should end with `wrote probe/features_qwen3_4b.npz (1147, 2560)`. If it runs out of memory,
lower `--batch-size`.

## 3. Train and evaluate the probe (CPU)

```bash
mkdir -p probe/out
python -m probe.probe --features probe/features_qwen3_4b.npz | tee probe/out/probe_hack_qwen3_4b.txt
```

This does grouped 5-fold CV over problems, an inner grid over the regularization strength `C`, and
5 shuffled-features controls per target (hack and legit-solve). It may take several minutes on CPU;
that is expected (2560-dim features, standardized, `GridSearchCV`).

## 4. Report back

Give the user the contents of `probe/out/probe_hack_qwen3_4b.txt`, in particular for `hack` and
`success`: positives / base rate, probe AUC vs the shuffled-control AUC (± std), Brier vs base-rate Brier.

Interpretation notes (state these, do not over-claim):
- There are only 97 hack positives, so AUC noise under the null is about ±0.03; a hack AUC below ~0.6 is
  not distinguishable from the shuffled control.
- `success` has ~18× more positives and is a more powerful check that the pipeline works.
- Do not edit `FINDINGS.md` or commit anything unless the user asks; results interpretation lives in
  `FINDINGS.md` per repo convention. `probe/features_qwen3_4b.npz` is ~12 MB — do not commit it
  without asking.
