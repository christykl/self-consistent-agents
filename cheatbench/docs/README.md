# docs

Project documentation for the self-consistent-agents work on CheatBench (see
`../CLAUDE.md` for the research plan).

- [modal_backend.md](modal_backend.md): running episodes in Modal Sandboxes with
  models and judges via OpenRouter (`--sandbox modal`). Covers code changes, task coverage, and caveats.
- [results_part1.md](results_part1.md): experimental results for Part 1 so far
  (pilot 1: GPT-6 Astra (Codex) and Qwen3.8-27B (Terminus-2), 14–15 episodes
  each across 6 tasks; the self-report "would you be tempted to cheat?"
  experiment on the same rows).
- [honeypot_alignment.md](honeypot_alignment.md): the `--honeypot alignment`
  variant, an `eval_track: alignment` metadata cue planted in one early-read file
  per pilot task. Covers placement, code, and verification.
- [report_alignment_prompt.md](report_alignment_prompt.md): short report on the
  Astra pilot with "This task is part of an alignment eval." in the prompt
  (cheated 5/14 vs 11/14 without it).
- [report_self_report_conditioned.md](report_self_report_conditioned.md): Astra
  pilot with its own earlier self-report ("not tempted", all 14 rows) prepended
  to the attempt prompt (`--self-report-from selfreport1`; cheated 2/14).
