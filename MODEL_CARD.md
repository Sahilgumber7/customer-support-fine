# Model card — Northwind Support 3B (planned)

**Status: `NOT RUN`.** No adapter and no GGUF exist. This card documents the model that the pipeline is
built around, the exact training recipe, and what will be measured. Nothing here is a result.

| Field | Value |
|---|---|
| Base model | `Qwen/Qwen2.5-3B-Instruct` (Apache-2.0) |
| Adaptation | QLoRA, 4-bit NF4, double quantisation |
| Target modules | q, k, v, o, gate, up, down projections |
| LoRA r / alpha / dropout | 16 / 32 / 0.05 |
| Trainable parameters | recorded in `run_manifest.json` at run time |
| Sequence length | 2048 |
| Batch / grad-accum | 2 / 8 (effective 16) |
| Epochs / LR | 2 / 1e-4, cosine, 3% warmup |
| Precision | fp16 (T4 has no bf16); gradient checkpointing on |
| Serving format | GGUF Q4_K_M via llama.cpp, CPU, `n_ctx=4096` |
| Teacher for SFT labels | rules baseline + policy engine (no larger model) |

## Intended use

Customer-support triage and action *proposals* for a fictional retailer: order status, returns,
replacements, refunds, cancellations, warranty claims, product questions. The model's output is always
validated by `schemas.py` and gated by `policy.py`; it is not trusted with identity, amounts, or
eligibility.

**Not intended for:** real payment processing, legal or medical advice, any deployment where a wrong
refund is unrecoverable, or use without the deterministic policy layer.

## Training data

3,156 train / 312 dev examples derived from 310 synthetic scenarios across 15 families, split by family so
the dev set contains three unseen task types. See `DATASET_CARD.md`.

## Evaluation plan (none of it has run)

1. `python -m eval.harness --backend llamacpp` on the same 310 frozen cases.
2. Same metrics as the baseline: pass rate, safety violations, p50/p95 latency.
3. Intent/entity accuracy against the gold `understand` labels.
4. Base-model (untuned Qwen2.5-3B-Instruct) run on the same harness for a paired comparison.
5. CPU RSS and tokens/sec on the build machine with the Q4_K_M GGUF.

A claim such as "improves over baseline" is only permissible after (1)–(4) exist as JSON artefacts.

## Known limitations (expected, to be confirmed empirically)

- 3B parameters and 4-bit quantisation will degrade on long, multi-intent messages.
- Training data is templated; paraphrase robustness outside the templates is unknown.
- JSON-only output needs a parse-retry path; a malformed plan currently escalates rather than guessing.
- The rules baseline is keyword-driven and will beat the model on canonical phrasings it was written for.
- Retrieval is lexical; no embedding model is used.

## Safety posture

The model cannot widen its own authority. Identity is server-side, refund amounts are computed from
order lines, actions are allowlisted by intent, policy is re-checked inside each tool, and state is
re-read before success is reported. A fully compromised model still cannot approve an ineligible refund;
it can only produce worse language and more escalations.

## Ethical and legal notes

- All customers, orders, products and addresses are synthetic (`example.test` emails). No real PII.
- No payment credentials are stored; `provider_ref` values are mock strings.
- Base model licence (Apache-2.0) must be carried into any redistributed adapter or GGUF.
- A production deployment would need data-retention review, human-in-the-loop for all financial actions,
  and locale-specific consumer-law review of the return windows.

## Artefacts that a completed run must produce

```
artifacts/qwen3b-support-lora/
  adapter_config.json
  adapter_model.safetensors
  run_manifest.json        # base, LoRA config, losses, GPU, peak VRAM, data hashes, wall time
artifacts/merged/
  merge_manifest.json      # merged + GGUF hashes, quant type
  qwen2.5-3b-support-q4_k_m.gguf
```

Until those files exist, every status field in this repository stays `NOT RUN`.
