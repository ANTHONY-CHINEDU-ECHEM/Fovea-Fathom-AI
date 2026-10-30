# 0001. Hybrid retrieval with clinical priors

Status: accepted

## Context

Dense models blur the exact tokens eye care depends on (6/12, R3A, TA824, 400 µm), while BM25 alone misses paraphrase. Pure relevance ranking also lets a vivid case report outrank NICE guidance.

## Decision

Fuse dense and BM25 results with reciprocal rank fusion, rerank against the question, then multiply by priors for evidence grade, recency, UK jurisdiction, condition and medicine match, and currency. Priors multiply rather than add so provenance never rescues an irrelevant passage. At most two chunks per document reach the model.

## Consequences

Ranking is explainable (each source lists its reasons) and tunable through settings. Priors need review when new source types are added.
