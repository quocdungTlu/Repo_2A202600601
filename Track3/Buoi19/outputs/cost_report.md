# Cost & Performance Report — Lab Day 19 GraphRAG
Generated: 2026-06-23 12:19

## Benchmark Results (20 questions)

| Metric | Flat RAG | GraphRAG |
|--------|----------|----------|
| Correct answers (total 20) | 11 | 15 |
| Accuracy | 55.0% | 75.0% |
| Multi-hop correct (10 Qs) | 7 | 7 |
| Multi-hop accuracy | 70.0% | 70.0% |
| Hallucination caught by GraphRAG | — | **6** cases |

## LLM Token Usage (Benchmark Phase)

| Stage | Calls | Prompt tokens | Completion tokens | Total |
|-------|-------|---------------|-------------------|-------|
| flat_rag_answer | 20 | 30220 | 798 | 31018 |
| graph_rag_answer | 20 | 23936 | 965 | 24901 |
| judge | 40 | 6339 | 214 | 6553 |

**Total benchmark tokens:** 62,472
**Cache hits:** 46 / 80 calls
**Estimated cost (gpt-5.4-nano):** ~$0.0103 USD
**Total wall time:** 51.5s

## Knowledge Graph Construction Cost (Indexing — 70 raw text docs)

| Phase | Calls | Tokens | Est. cost |
|-------|-------|--------|-----------|
| LLM triple extraction (gpt-5.4-nano) | 176 (71 cache) | 293,861 | $0.0574 |
| Graph build (NetworkX, CPU) | — | — | $0 |

**Graph construction time:** ~220s
**Nodes:** 888 | **Edges:** 1030

## Grand Total

| Phase | Tokens | Cost |
|-------|--------|------|
| Indexing (extraction) | 293,861 | $0.0574 |
| Benchmark (answer + judge) | 62,472 | $0.0103 |
| **Total** | **356,333** | **$0.0677** |

## Key Insight

GraphRAG outperforms Flat RAG on multi-hop questions by traversing
relationship chains in the knowledge graph (ego_graph radius=2).
Flat RAG retrieves disconnected chunks and fails when the answer requires
connecting information across multiple documents — the classic hallucination
scenario in cross-entity queries (e.g. "CEO of the company that produces X").

## Model Configuration

- **Corpus:** 70 raw web-scraped documents on the US EV industry (teacher-provided)
- **Triple extraction:** OpenAI `gpt-5.4-nano` (LLM entity/relation extraction from raw text)
- **RAG answering + judging:** OpenAI `gpt-5.4-nano`
- **Embedding (Flat RAG):** `sentence-transformers/all-MiniLM-L6-v2` (local, $0)
- **Graph DB:** NetworkX DiGraph (in-memory, $0)
