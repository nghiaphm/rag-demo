# Phase 1 — Advanced RAG Baseline Evaluation Report

- **Generated At**: `2026-11-15T07:09:09.135181+00:00`
- **Mode**: `offline`
- **Dataset**: `golden_set.json` (9 cases)

## RAGAS Summary

| Metric | Score |
| --- | ---: |
| Context Precision | 1.0000 |
| Context Recall | 0.7778 |
| Faithfulness | 0.7778 |
| Answer Relevancy | 0.7722 |
| **Overall Score** | **0.8319** |

## Latency & Token Usage

- **p50 Latency**: `0.14 ms`
- **p95 Latency**: `0.2 ms`
- **Mean Latency**: `0.15 ms`
- **TTFT p50 / p95**: `0.14 ms` / `0.2 ms`
- **Total Tokens (Prompt / Completion / Total)**: `843` / `431` / `1274`

## Per-Case Breakdown

| ID | Retrieved Sources | Ctx Prec | Ctx Rec | Faithfulness | Relevancy | Overall |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| `vector-backend` | qdrant.md, llm-embedding.md | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| `qdrant-collection` | qdrant.md, chunking.md | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| `active-version-filter` | qdrant.md | 1.00 | 1.00 | 1.00 | 0.95 | 0.99 |
| `chunk-size` | chunking.md, qdrant.md | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| `chunk-overlap` | chunking.md, qdrant.md | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| `embedding-dim` | llm-embedding.md, qdrant.md | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| `embedding-change` | llm-embedding.md, qdrant.md | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| `oob-capital` | (none) | 1.00 | 0.00 | 0.00 | 0.00 | 0.25 |
| `oob-gold` | (none) | 1.00 | 0.00 | 0.00 | 0.00 | 0.25 |
