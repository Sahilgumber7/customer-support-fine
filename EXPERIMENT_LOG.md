# EXPERIMENT_LOG.md

Append-only. One block per run. Never edit a past entry — add a new one and reference the old.

Template:

```
## EXP-000 — <short name>
- Date:
- Purpose:
- Hardware: <GPU/RAM/CPU> | host: <local|kaggle|colab|rental>
- Dataset: <version, hash, n_train/n_dev>
- Config: <base model + revision, quant, r, alpha, lr, bs, grad-accum, max_len, epochs, seed>
- Command:
- Artifacts: <paths + sha256>
- Results: <loss, dev metrics, eval report path>
- Verdict: <keep|discard|revise> + why
- Notes / failures:
```

---

## EXP-000 — environment baseline (not a training run)
- Date: 2026-10-23
- Purpose: establish what hardware can actually do before planning compute
- Hardware: 4 logical CPUs, 8.0 GB RAM, no NVIDIA GPU, 14.7 GB free disk | host: local Windows
- Result: local 3B training ruled out; serving limited to CPU GGUF
- Verdict: revise plan → QLoRA on free-tier T4, GGUF Q4_K_M serving
- Artefacts: `ENVIRONMENT_FACTS.md`
