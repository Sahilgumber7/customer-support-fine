# External NLU probe — rules baseline

Generated: 2026-10-23T10:48:53+00:00

> **Reference backend only.** This measures the deterministic keyword baseline, not the fine-tuned model (which is NOT RUN). External data is evaluation-only; raw rows are not committed.

## Bitext customer support (mapped intents)

| Metric | Value |
|---|---|
| Rows | 26,872 |
| Mapped rows | 7,986 |
| Unmapped rows | 18,886 |
| Accuracy | 30.98% |
| Macro-F1 | 0.4354 |
| Unmapped rows given an in-scope intent | 926 (4.90%) |

| Intent | Support | Precision | Recall | F1 |
|---|---:|---:|---:|---:|
| cancellation_request | 998 | 1.000 | 0.429 | 0.600 |
| complaint | 1,000 | 1.000 | 0.311 | 0.474 |
| human_handoff | 1,999 | 1.000 | 0.243 | 0.391 |
| order_status | 995 | 0.892 | 0.392 | 0.545 |
| payment_issue | 999 | 0.000 | 0.000 | 0.000 |
| refund_request | 1,995 | 1.000 | 0.431 | 0.603 |

## BANKING77 (out-of-domain rejection)

All 3,080 test queries are out-of-domain for this retailer. Acceptable = `other` or `human_handoff`.

| Metric | Value |
|---|---|
| False accepts | 399 |
| False-accept rate | 12.95% |
| Handoff rate | 0.10% |
| Other rate | 86.95% |

| Predicted in-scope intent | Count |
|---|---:|
| replacement_request | 162 |
| refund_request | 108 |
| order_status | 59 |
| cancellation_request | 42 |
| payment_issue | 11 |
| product_info | 7 |
| return_request | 7 |
| complaint | 3 |

## CLINC150 (out-of-scope recall)

The 1,000 `oos_test` rows should all be refused or handed off.

| Metric | Value |
|---|---|
| OOS recall (acceptable rate) | 96.70% |
| False accepts | 33 |
| False-accept rate | 3.30% |
| Handoff rate | 0.80% |

## Provenance

| Dataset | Source | SHA-256 |
|---|---|---|
| Bitext | https://huggingface.co/datasets/bitext/Bitext-customer-support-llm-chatbot-training-dataset/resolve/main/Bitext_Sample_Customer_Support_Training_Dataset_27K_responses-v11.csv (revision `430d1a89bd93`) | `6f81102b0100b97b…` |
| BANKING77 | https://raw.githubusercontent.com/PolyAI-LDN/task-specific-datasets/master/banking_data/test.csv | `d12d6e3bc4c31039…` |
| CLINC150 | https://raw.githubusercontent.com/clinc/oos-eval/master/data/data_full.json | `36923c3705a59e08…` |

Machine-readable result: `EVALUATION_RESULTS/external-nlu-rules.json`.
