"""Merge the LoRA adapter into the base model and export a Q4_K_M GGUF for CPU serving.

Run after training, on the same GPU host (or any machine with enough RAM/disk):
    python merge_and_export.py --adapter artifacts/qwen3b-support-lora --out artifacts/merged
Then, if llama.cpp is available:
    python merge_and_export.py ... --quantize
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

import torch
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="Qwen/Qwen2.5-3B-Instruct")
    parser.add_argument("--adapter", required=True)
    parser.add_argument("--out", default="artifacts/merged")
    parser.add_argument("--quantize", action="store_true")
    parser.add_argument("--llama-cpp-dir", default="llama.cpp")
    args = parser.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    tokenizer = AutoTokenizer.from_pretrained(args.base)
    base = AutoModelForCausalLM.from_pretrained(args.base, torch_dtype=torch.float16)
    merged = PeftModel.from_pretrained(base, args.adapter).merge_and_unload()
    merged.save_pretrained(out, safe_serialization=True)
    tokenizer.save_pretrained(out)

    manifest = {
        "base_model": args.base,
        "adapter": args.adapter,
        "merged_dir": str(out),
        "merged_sha256": {p.name: sha256(p) for p in out.glob("*.safetensors")},
    }

    if args.quantize:
        cpp = Path(args.llama_cpp_dir)
        gguf_fp16 = out / "model-f16.gguf"
        subprocess.run(
            [
                "python",
                str(cpp / "convert_hf_to_gguf.py"),
                str(out),
                "--outfile",
                str(gguf_fp16),
                "--outtype",
                "f16",
            ],
            check=True,
        )
        gguf_q4 = out / "qwen2.5-3b-support-q4_k_m.gguf"
        subprocess.run(
            [str(cpp / "build" / "bin" / "llama-quantize"), str(gguf_fp16), str(gguf_q4), "Q4_K_M"],
            check=True,
        )
        gguf_fp16.unlink(missing_ok=True)
        manifest["gguf"] = {
            "path": str(gguf_q4),
            "quant": "Q4_K_M",
            "size_bytes": gguf_q4.stat().st_size,
            "sha256": sha256(gguf_q4),
        }

    (out / "merge_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
