# Training on a free GPU (Kaggle / Colab)

This machine has **no GPU** (see `../ENVIRONMENT_FACTS.md`), so training runs on a notebook GPU.
Nothing here executes locally.

## Why these settings

| Constraint | Choice |
|---|---|
| T4 = 16 GB VRAM | QLoRA 4-bit NF4, r=16, batch 2, grad-accum 8 |
| T4 has no bf16 | `fp16=True`, `bf16=False` |
| 3B weights | gradient checkpointing on, `use_cache=False` |
| ~3.7k examples | 2 epochs, cosine, lr 1e-4 |

## Kaggle, step by step

1. Create a notebook, set **Accelerator → GPU T4 x2** (use one; the script pins `device_map={"":0}`).
2. Upload this repo (or clone it), and the generated data (`data/sft/train.jsonl`, `dev.jsonl`).
   Regenerate if missing: `python -m data_gen.generate --variants 4`.
3. Install:
   ```bash
   pip install -q -r training/requirements-train.txt
   ```
4. Smoke test (20 steps, catches shape/config errors in ~3 minutes):
   ```bash
   python training/train_qlora.py --max-steps 20 --out /kaggle/working/smoke
   ```
5. Full run (~1.5–3 h on a T4, depending on sequence lengths):
   ```bash
   python training/train_qlora.py --epochs 2 --out /kaggle/working/qwen3b-support-lora
   ```
6. Merge and quantise (CPU is fine for the merge if you have ~8 GB RAM; do it on the GPU host):
   ```bash
   python training/merge_and_export.py \
     --adapter /kaggle/working/qwen3b-support-lora \
     --out /kaggle/working/merged
   ```
   For GGUF you need llama.cpp built in the notebook:
   ```bash
   git clone https://github.com/ggerganov/llama.cpp && cd llama.cpp && cmake -B build && cmake --build build -j --target llama-quantize
   ```
7. Download `/kaggle/working/qwen3b-support-lora/run_manifest.json` and the `*.gguf`, then record
   both in `../EXPERIMENT_LOG.md`. **Do not write results until the file exists.**

## Serving locally

```bash
# put the GGUF here (gitignored):
#   models/qwen2.5-3b-support-q4_k_m.gguf
pip install llama-cpp-python
set SUPPORT_AI_BACKEND=llamacpp
uvicorn support_ai.api:app --port 8000
```

Startup prints the model id; `/api/model-info` reports exactly what is being served.

## Expected artefacts

```
run_manifest.json        base model, LoRA config, losses, GPU, peak VRAM, data hashes
adapter_model.safetensors
adapter_config.json
merge_manifest.json      merged hashes + GGUF hash and quant type
```

If a run fails, log the failure and the error in `EXPERIMENT_LOG.md` rather than deleting the
attempt. A documented OOM at batch 2 with the reduced config is a legitimate result.
