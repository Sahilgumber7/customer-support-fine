"""QLoRA fine-tune of Qwen2.5-3B-Instruct for this support agent.

Designed to run top-to-bottom on a free Kaggle/Colab T4 (16 GB). It is NOT runnable on a
CPU-only laptop, and the repo's local machine has no GPU — see ENVIRONMENT_FACTS.md.

Smoke test first:
    python train_qlora.py --max-steps 20 --out /kaggle/working/smoke
Full run:
    python train_qlora.py --epochs 2 --out /kaggle/working/qwen3b-support-lora
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from pathlib import Path

import torch
from datasets import load_dataset
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    BitsAndBytesConfig,
    TrainerCallback,
)
from trl import SFTConfig, SFTTrainer

BASE = "Qwen/Qwen2.5-3B-Instruct"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def render(example: dict, tokenizer) -> dict:
    """Fold the task prompt + gold response into one chat sequence."""
    messages = list(example["messages"])
    messages.append({"role": "assistant", "content": example["response"]})
    text = tokenizer.apply_chat_template(messages, tokenize=False)
    return {"text": text}


class MemoryCallback(TrainerCallback):
    def on_log(self, args, state, control, logs=None, **kwargs):
        if logs and torch.cuda.is_available():
            logs["gpu_peak_gb"] = round(torch.cuda.max_memory_allocated() / 1e9, 2)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", default="data/sft")
    parser.add_argument("--model", default=BASE)
    parser.add_argument("--out", default="artifacts/qwen3b-support-lora")
    parser.add_argument("--epochs", type=float, default=2.0)
    parser.add_argument("--lr", type=float, default=1e-4)
    parser.add_argument("--r", type=int, default=16)
    parser.add_argument("--alpha", type=int, default=32)
    parser.add_argument("--dropout", type=float, default=0.05)
    parser.add_argument("--max-len", type=int, default=2048)
    parser.add_argument("--bs", type=int, default=2)
    parser.add_argument("--grad-accum", type=int, default=8)
    parser.add_argument("--max-steps", type=int, default=-1)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    if not torch.cuda.is_available():
        raise SystemExit(
            "No CUDA device. This training script requires a GPU (T4 or better). "
            "Run it on Kaggle/Colab; see training/README.md. Do not run on CPU."
        )

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    tokenizer = AutoTokenizer.from_pretrained(args.model, trust_remote_code=False)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    bnb = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.float16,
        bnb_4bit_use_double_quant=True,
    )
    model = AutoModelForCausalLM.from_pretrained(
        args.model,
        quantization_config=bnb,
        device_map={"": 0},
        torch_dtype=torch.float16,
    )
    model = prepare_model_for_kbit_training(model, use_gradient_checkpointing=True)
    model.config.use_cache = False

    lora = LoraConfig(
        r=args.r,
        lora_alpha=args.alpha,
        lora_dropout=args.dropout,
        bias="none",
        task_type="CAUSAL_LM",
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
    )
    model = get_peft_model(model, lora)
    trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)

    data_files = {"train": str(Path(args.data_dir) / "train.jsonl"),
                  "dev": str(Path(args.data_dir) / "dev.jsonl")}
    ds = load_dataset("json", data_files=data_files)
    ds = ds.map(lambda ex: render(ex, tokenizer), remove_columns=ds["train"].column_names)

    cfg = SFTConfig(
        output_dir=str(out / "checkpoints"),
        num_train_epochs=args.epochs,
        max_steps=args.max_steps,
        per_device_train_batch_size=args.bs,
        per_device_eval_batch_size=args.bs,
        gradient_accumulation_steps=args.grad_accum,
        gradient_checkpointing=True,
        learning_rate=args.lr,
        lr_scheduler_type="cosine",
        warmup_ratio=0.03,
        logging_steps=10,
        eval_strategy="steps" if args.max_steps > 0 else "epoch",
        eval_steps=50 if args.max_steps > 0 else None,
        save_strategy="epoch",
        save_total_limit=2,
        fp16=True,
        bf16=False,
        max_length=args.max_len,
        dataset_text_field="text",
        packing=False,
        seed=args.seed,
        report_to=[],
    )

    trainer = SFTTrainer(
        model=model,
        args=cfg,
        train_dataset=ds["train"],
        eval_dataset=ds["dev"],
        processing_class=tokenizer,
        callbacks=[MemoryCallback()],
    )

    started = time.time()
    trainer.train()
    wall = round(time.time() - started, 1)
    trainer.save_model(str(out))
    tokenizer.save_pretrained(str(out))

    manifest = {
        "base_model": args.model,
        "method": "qlora",
        "lora": {"r": args.r, "alpha": args.alpha, "dropout": args.dropout},
        "trainable_params": trainable,
        "train_examples": len(ds["train"]),
        "dev_examples": len(ds["dev"]),
        "epochs": args.epochs,
        "max_steps": args.max_steps,
        "lr": args.lr,
        "batch_size": args.bs,
        "grad_accum": args.grad_accum,
        "max_len": args.max_len,
        "seed": args.seed,
        "wall_clock_s": wall,
        "gpu": torch.cuda.get_device_name(0),
        "gpu_peak_gb": round(torch.cuda.max_memory_allocated() / 1e9, 2),
        "final_train_loss": next(
            (h["loss"] for h in reversed(trainer.state.log_history) if "loss" in h), None
        ),
        "final_eval_loss": next(
            (h["eval_loss"] for h in reversed(trainer.state.log_history) if "eval_loss" in h), None
        ),
        "data_sha256": {
            name: sha256(Path(args.data_dir) / f"{name}.jsonl") for name in ("train", "dev")
        },
        "adapter_files": sorted(p.name for p in out.glob("adapter_*")),
        "env": {"torch": torch.__version__, "cuda": torch.version.cuda},
    }
    (out / "run_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
    main()
