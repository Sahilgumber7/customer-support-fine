# ENVIRONMENT_FACTS.md — measured, not assumed

Recorded by direct inspection on 2026-10-23. Re-verify at session start with the commands at the bottom.

## Host machine (development)

| Property | Value |
|---|---|
| OS | Windows (win32), PowerShell |
| Python | 3.12.6 |
| Git | 2.50.1.windows.1 |
| CPU | 4 logical processors |
| RAM | 8.0 GB total (8,267,358,208 bytes) |
| GPU | **None detected** — `nvidia-smi` not found |
| Free disk (C:) | **14.7 GB** |
| Working dir | `C:\Users\muska\support-llm-3b` |

## What this means — binding constraints

1. **No local training. Do not attempt it.** Full fine-tuning, LoRA, and even QLoRA of a 3B model are not viable on 4 cores / 8 GB RAM / no GPU. Any attempt will either OOM, thrash swap, or take days. Do not "try anyway to see" — that wastes the session.
2. **No local model download.** Qwen2.5-3B-Instruct in bf16 is ~6.2 GB of weights, plus a duplicate during training. With 14.7 GB free and no GPU, download + training artifacts on this disk is a dead end.
3. **Training happens on rented/notebook GPUs.** Use a reproducible notebook/script workflow:
   - Primary: **Kaggle Notebooks** (free T4×2 or P100, 16 GB VRAM each) — good for QLoRA on 3B.
   - Alternate: **Colab** (free T4 16 GB) or a paid single-GPU rental (RunPod / Vast / Lightning) only if the user approves spend.
   - The repo must contain a `notebooks/` or `training/` bundle that can be uploaded and run top-to-bottom, plus the exact `!pip install` pins.
4. **Local serving must be CPU-feasible.** Final artifact served locally = **merged, 4-bit quantized GGUF** (Q4_K_M ≈ 1.9–2.2 GB) via `llama.cpp` / `llama-cpp-python`. Target ≤ 4.5 GB RSS so it coexists with FastAPI + Postgres-free (SQLite) backend inside 8 GB.
   - Do **not** plan to serve the 3B bf16 checkpoint locally.
   - Full-precision/vLLM serving may be *documented* as the production path and benchmarked only if a GPU is available; label it clearly as not locally measured.
5. **Database: SQLite, not PostgreSQL.** 8 GB RAM and a single dev box. Use SQLAlchemy so the Postgres URL remains a config swap, and say so in DECISIONS.md. Do not spend time on Docker/Postgres/Redis for v1.
6. **Keep the disk cool.** Any model/large-artifact write must go to an ignored path (`artifacts/`, `models/`), and the agent must check free space before writing files > 500 MB. Delete intermediate checkpoints after merge+quantize.
7. **UI: single-page local app.** Next.js is fine only if `node` is present and the install stays under ~1 GB. Otherwise FastAPI + Jinja/HTMX or a static HTML+JS client. Verify `node --version` before committing to a stack; do not install a toolchain speculatively.

## Consequence for the deliverable

The resume claim must be defensible: *"Fine-tuned Qwen2.5-3B-Instruct with QLoRA on a rented/free-tier T4, evaluated against the base model on a held-out 300-case benchmark, served locally as a 4-bit GGUF behind a policy-gated tool-calling agent."* That is a strong, honest story. "Trained and served on my laptop" is not available here.

## Re-verification commands

```powershell
nvidia-smi --query-gpu=name,memory.total --format=csv   # expect: not found
python --version
git --version
(Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory
Get-PSDrive C | Select-Object Free
node --version   # optional, check before choosing the frontend stack
```

If any of these differ at a later session, update this file and the affected decisions in `DECISIONS.md` before proceeding.
