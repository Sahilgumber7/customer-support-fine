# Deployment

Two modes: the **rules baseline**, which runs anywhere and is what this machine demonstrates, and the
**fine-tuned GGUF**, which needs an artefact that does not exist yet.

## Requirements

| Mode | Needs |
|---|---|
| Baseline | Python ≥3.11, ~200 MB deps, ~50 MB disk for the SQLite database |
| GGUF serving | the Q4_K_M file (~1.9 GB), `llama-cpp-python`, ~3–4 GB free RAM for 3B Q4 + 4k context |

Measured on the build machine: Python 3.12.6, Windows 11, 8 GB RAM, no CUDA. The baseline benchmark
(310 cases) runs in ~27 s, p50 16 ms / p95 25 ms per turn.

## Install

```powershell
git clone <repo> ; cd support-llm-3b
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .
```

Optional extras:

```powershell
pip install pytest httpx     # tests
pip install ruff             # lint
pip install llama-cpp-python # only for GGUF serving
```

## Configure

Environment variables use the `SUPPORT_AI_` prefix (see `src/support_ai/config.py`).

| Variable | Default | Notes |
|---|---|---|
| `SUPPORT_AI_DB_URL` | `sqlite:///./support.db` | any SQLAlchemy URL, e.g. `postgresql+psycopg://…` |
| `SUPPORT_AI_BACKEND` | `mock` | `mock` (rules) or `llamacpp` |
| `SUPPORT_AI_GGUF_PATH` | `models/qwen2.5-3b-support-q4_k_m.gguf` | used when backend is `llamacpp` |
| `SUPPORT_AI_N_THREADS` | `4` | CPU threads for llama.cpp |
| `SUPPORT_AI_N_CTX` | `4096` | context window |
| `SUPPORT_AI_REFUND_APPROVAL_THRESHOLD_CENTS` | `15000` | policy constant |
| `SUPPORT_AI_DEMO_MODE` | `true` | relaxes the ops token check for local use |

Policy constants are versioned with `SUPPORT_AI_POLICY_VERSION` (default `2026.1`) and appear in
`/api/model-info` and every audit row.

## Run

```powershell
$env:PYTHONPATH="src;."
python -m support_ai.seed                     # rebuild synthetic data (drops and recreates tables)
uvicorn support_ai.api:app --host 127.0.0.1 --port 8000
```

- `/` — customer chat (pick a demo customer, ask about `ORD-1001` … `ORD-5001`)
- `/ops` — approvals, escalations, audit trail
- `/healthz` — liveness; `/readyz` — 503 until seeded
- `/api/model-info` — exactly which backend and policy version is live

Startup seeds automatically only when the `customers` table is empty. To reset, run the seed module or
delete `support.db`.

## Serving the fine-tuned model

```powershell
# after training/merge_and_export.py has produced the GGUF
$env:SUPPORT_AI_BACKEND="llamacpp"
$env:SUPPORT_AI_GGUF_PATH="models/qwen2.5-3b-support-q4_k_m.gguf"
uvicorn support_ai.api:app --port 8000
```

`/api/model-info` will then report `backend: llamacpp` and the model id from the backend. If the file is
missing or `llama-cpp-python` is not installed, startup fails loudly rather than silently falling back to
the rules baseline — a silent fallback would misrepresent what is serving traffic.

## Postgres

```powershell
$env:SUPPORT_AI_DB_URL="postgresql+psycopg://user:pass@localhost:5432/support"
pip install "psycopg[binary]"
python -m support_ai.seed
```

The schema is plain SQLAlchemy 2.0 and creates cleanly on Postgres. No SQLite-specific types are used.
For production, replace `Base.metadata.create_all` with Alembic migrations.

## Containers

Not included. The service is a single process with one dependency (a database) and no Node toolchain, so
a three-line `Dockerfile` (`python:3.12-slim`, `pip install -e .`, `uvicorn …`) is sufficient when needed;
the GGUF is mounted as a volume rather than baked into the image.

## Operational checks

| Check | Command |
|---|---|
| Tests | `python -m pytest -q` (78 expected) |
| Lint | `python -m ruff check src tests eval data_gen` |
| Benchmark | `python -m eval.harness` |
| Retrieval | `python -m eval.retrieval_eval` |
| Dataset | `python -m data_gen.validate` |
| Scorecard | `python -m eval.scorecard` |

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `ModuleNotFoundError: support_ai` | `pip install -e .` or set `PYTHONPATH=src;.` |
| `/readyz` returns 503 | database not seeded — `python -m support_ai.seed` |
| 401 on chat routes | sign in first; the token is required on every call |
| `RuntimeError: llama-cpp-python is not installed` | install it, or unset `SUPPORT_AI_BACKEND` |
| Order "not found" for an id you can see | you are signed in as a different customer; ownership is enforced |
| Tests mutate demo data | `test_api.py` reseeds the file database at session start; run `python -m support_ai.seed` afterwards if you want a clean demo |
