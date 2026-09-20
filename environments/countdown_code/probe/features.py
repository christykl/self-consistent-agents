"""Mean-pooled final-layer Qwen3-4B representations of each countdown-code task prompt (GPU).

    python -m probe.features --out probe/features_qwen3_4b.npz

Builds the same system + user chat the no-ask o4-mini runs saw, runs the model once, and averages
the last hidden layer over the user-message tokens.  Output npz: `ids` (problem keys) and `X`.
"""
import argparse

import numpy as np
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

from countdown_code.countdown_code import SYSTEM_PROMPT, build_task_prompt
from probe.labels import load_rollouts


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--model", default="Qwen/Qwen3-4B")
    p.add_argument("--batch-size", type=int, default=8)
    p.add_argument("--out", required=True)
    args = p.parse_args()

    device = "cuda" if torch.cuda.is_available() else "cpu"
    tok = AutoTokenizer.from_pretrained(args.model)
    tok.padding_side = "right"
    model = AutoModelForCausalLM.from_pretrained(args.model, dtype=torch.bfloat16).to(device).eval()

    problems = {key: (numbers, target) for key, numbers, target, _, _ in load_rollouts()}
    keys = sorted(problems)
    feats = []
    for i in range(0, len(keys), args.batch_size):
        texts, spans = [], []
        for key in keys[i : i + args.batch_size]:
            user = build_task_prompt(*problems[key])
            messages = [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user}]
            text = tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=True, enable_thinking=False)
            start = text.index(user)
            texts.append(text)
            spans.append((start, start + len(user)))
        enc = tok(texts, return_tensors="pt", padding=True, return_offsets_mapping=True)
        offsets = enc.pop("offset_mapping")
        with torch.no_grad():
            h = model(**{k: v.to(device) for k, v in enc.items()}, output_hidden_states=True).hidden_states[-1]
        for b, (s, e) in enumerate(spans):
            inside = (offsets[b, :, 0] >= s) & (offsets[b, :, 1] <= e) & (offsets[b, :, 1] > offsets[b, :, 0])
            feats.append(h[b][inside.to(device)].float().mean(0).cpu().numpy())
        print(f"{len(feats)}/{len(keys)}", flush=True)
    np.savez(args.out, ids=np.array(keys), X=np.stack(feats).astype(np.float32))
    print("wrote", args.out, np.stack(feats).shape)


if __name__ == "__main__":
    main()
