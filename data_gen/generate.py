"""Generate the SFT dataset from scenario specifications, with a deterministic teacher.

The teacher is the rules baseline + policy engine, not a larger model. That means every
label is grounded in the same synthetic database state the agent will see at inference
time, and no external model generated the answers.

Splits are by *scenario family*, so the dev set measures generalisation to unseen task
types rather than memorised paraphrases.

Run: python -m data_gen.generate --variants 4
"""

from __future__ import annotations

import argparse
import json
import random
from datetime import datetime
from pathlib import Path

from eval.harness import Case, build_env, generate
from support_ai.llm import RulesBackend
from support_ai.orchestrator import Orchestrator
from support_ai.retrieval import Retriever

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "sft"

SYSTEM = (
    "You are the customer support agent for Northwind Outfitters. You never invent order "
    "facts, policy, or completed actions. Identity is decided by the server. Reply with JSON "
    "matching the requested schema only."
)

PREFIXES = ["", "Hi, ", "Hello — ", "Quick one: ", "Hey there, "]
SUFFIXES = ["", " Thanks.", " Please help.", " Can you sort this out?", " It's urgent."]

# Held out entirely from training so the dev set is a real generalisation check.
DEV_FAMILIES = {"human_handoff", "multi_item_ambiguity", "refund_already_refunded"}

# Adversarial families are evaluated only. Keeping them out of SFT prevents the tuned model from
# learning the exact attacks it is scored on.
EXCLUDED_FAMILIES = {"cross_account", "prompt_injection"}


def variant_message(base: str, i: int, rng: random.Random) -> str:
    if i == 0:
        return base
    return f"{PREFIXES[i % len(PREFIXES)]}{base.rstrip('.')}{SUFFIXES[(i * 3 + 1) % len(SUFFIXES)]}"


def gold_turns(case: Case, retriever: Retriever) -> dict:
    session, conv_id, _ = build_env(case, retriever)
    backend = RulesBackend()
    orch = Orchestrator(session, backend, retriever, 1, conv_id)

    understanding = backend.understand(case.message, [])
    result = orch.handle(case.message)
    session.close()

    executed = [
        {"name": step.detail, "arguments": step.payload.get("args", {})}
        for step in result.trace
        if step.stage in {"tool", "action"} and step.payload.get("ok")
    ]
    return {
        "understand": understanding.model_dump(),
        "act": {
            "tool_calls": executed,
            "proposed_resolution": result.action_taken,
        },
        "respond": {
            "customer_message": result.message,
            "action_taken": result.action_taken,
            "reason_code": result.reason_code,
        },
        "trace": [s.model_dump() for s in result.trace],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--variants", type=int, default=4)
    parser.add_argument("--seed", type=int, default=11)
    args = parser.parse_args()

    rng = random.Random(args.seed)
    retriever = Retriever.from_directory()
    cases = generate()

    OUT.mkdir(parents=True, exist_ok=True)
    splits = {"train": [], "dev": []}
    families: dict[str, int] = {}
    seen: set[str] = set()
    dropped = 0
    excluded = 0
    for case in cases:
        if case.family in EXCLUDED_FAMILIES:
            excluded += 1
            continue
        gold = gold_turns(case, retriever)
        split = "dev" if case.family in DEV_FAMILIES else "train"
        families[case.family] = families.get(case.family, 0) + 1

        for i in range(args.variants):
            msg = variant_message(case.message, i, rng)
            base_meta = {
                "case_id": case.id,
                "family": case.family,
                "variant": i,
                "order_id": case.order_id,
                "sku": case.sku,
            }
            for row in [
                {
                    "task": "understand",
                    "messages": [
                        {"role": "system", "content": SYSTEM},
                        {
                            "role": "user",
                            "content": "Classify this support message. Return JSON with intent, "
                            f"entities, needs_clarification, clarification_question, confidence.\n\n{msg}",
                        },
                    ],
                    "response": json.dumps(gold["understand"], ensure_ascii=False),
                    "meta": base_meta,
                },
                {
                    "task": "act",
                    "messages": [
                        {"role": "system", "content": SYSTEM},
                        {
                            "role": "user",
                            "content": "Choose the next tool calls. Return JSON with tool_calls and "
                            f"proposed_resolution.\n\nMessage: {msg}\n"
                            f"Understanding: {json.dumps(gold['understand'])}",
                        },
                    ],
                    "response": json.dumps(gold["act"], ensure_ascii=False),
                    "meta": base_meta,
                },
                {
                    "task": "respond",
                    "messages": [
                        {"role": "system", "content": SYSTEM},
                        {
                            "role": "user",
                            "content": "Write the customer reply using only verified facts. Return "
                            "JSON with customer_message, cites, escalate, escalate_reason.\n\n"
                            f"Message: {msg}\nActions: {json.dumps(gold['respond'])}",
                        },
                    ],
                    "response": json.dumps(
                        {
                            "customer_message": gold["respond"]["customer_message"],
                            "cites": [],
                            "escalate": bool(result_escalates(gold)),
                            "escalate_reason": None,
                        },
                        ensure_ascii=False,
                    ),
                    "meta": base_meta,
                },
            ]:
                digest = json.dumps(row["messages"], sort_keys=True)
                if digest in seen:
                    dropped += 1
                    continue
                seen.add(digest)
                splits[split].append(row)

    for split, rows in splits.items():
        path = OUT / f"{split}.jsonl"
        with path.open("w", encoding="utf-8") as fh:
            for row in rows:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        print(f"{split}: {len(rows)} examples -> {path}")

    manifest = {
        "generated_at": datetime.utcnow().isoformat(),
        "generator": "data_gen/generate.py",
        "teacher": "rules-baseline + policy engine (no external LLM)",
        "seed": args.seed,
        "variants_per_case": args.variants,
        "cases": len(cases),
        "cases_used": len(cases) - excluded,
        "excluded_cases": excluded,
        "examples": {k: len(v) for k, v in splits.items()},
        "families": families,
        "dev_families_held_out": sorted(DEV_FAMILIES),
        "adversarial_families_excluded": sorted(EXCLUDED_FAMILIES),
        "note": "Variants are surface rephrasings only; they are not independent scenarios.",
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps(manifest["examples"]))


def result_escalates(gold: dict) -> bool:
    return gold["respond"]["action_taken"] == "escalate_to_human"


if __name__ == "__main__":
    main()
