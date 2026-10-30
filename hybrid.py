"""Hybrid retrieval: dense and BM25 recall, reciprocal rank fusion, reranking and priors."""

from __future__ import annotations

from dataclasses import dataclass, field

from fovea.clinical.understanding import Understanding
from fovea.config import Settings
from fovea.domain import ScoredChunk
from fovea.retrieval import priors
from fovea.retrieval.index import KnowledgeIndex


@dataclass
class RetrievalResult:
    passages: list[ScoredChunk]
    candidates: int
    dense_hits: int
    sparse_hits: int
    debug: dict[str, object] = field(default_factory=dict)

    @property
    def best_score(self) -> float:
        return self.passages[0].score if self.passages else 0.0


class HybridRetriever:
    def __init__(self, index: KnowledgeIndex, settings: Settings) -> None:
        self.index = index
        self.settings = settings

    def retrieve(
        self, u: Understanding, top_k: int | None = None, filters: dict[str, object] | None = None
    ) -> RetrievalResult:
        s = self.settings
        top_k = top_k or s.top_k_final
        dense = self.index.dense_search(u.recall_query, s.top_k_dense, filters)
        sparse = self.index.sparse_search(u.recall_query, s.top_k_sparse)
        if filters:
            sparse = [(cid, sc) for cid, sc in sparse if self.index.matches(cid, filters)]

        fused: dict[str, float] = {}
        dense_rank: dict[str, int] = {}
        sparse_rank: dict[str, int] = {}
        for rank, (cid, _) in enumerate(dense, start=1):
            fused[cid] = fused.get(cid, 0.0) + 1 / (s.rrf_k + rank)
            dense_rank[cid] = rank
        for rank, (cid, _) in enumerate(sparse, start=1):
            fused[cid] = fused.get(cid, 0.0) + 1 / (s.rrf_k + rank)
            sparse_rank[cid] = rank
        # Exact guidance or registry identifiers named in the question always reach reranking.
        for gid in u.guidance_ids:
            for cid in self.index.ids_mentioning(gid):
                fused[cid] = fused.get(cid, 0.0) + 1 / s.rrf_k
        head = sorted(fused, key=lambda c: fused[c], reverse=True)[: s.rerank_depth]
        chunks = [self.index.chunks[c] for c in head]
        texts = [f"{c.title}. {c.section}. {c.text}" for c in chunks]
        rerank = self.index.reranker.score(u.precision_query, u.recall_query, texts)

        scored: list[ScoredChunk] = []
        for chunk, rr in zip(chunks, rerank, strict=True):
            prior = priors.compute(chunk, u.conditions, u.drugs, s)
            named = any(
                g.lower() in (chunk.title + " " + chunk.text + " " + chunk.doc_id).lower()
                for g in u.guidance_ids
            )
            relevance = min(1.0, rr + (0.25 if named else 0.0))
            scored.append(
                ScoredChunk(
                    chunk=chunk,
                    score=relevance * prior.factor,
                    dense_rank=dense_rank.get(chunk.id),
                    sparse_rank=sparse_rank.get(chunk.id),
                    rerank_score=relevance,
                    prior=prior.factor,
                    reasons=prior.reasons + (["named in question"] if named else []),
                )
            )
        scored.sort(key=lambda sc: sc.score, reverse=True)

        selected: list[ScoredChunk] = []
        per_doc: dict[str, int] = {}
        for item in scored:
            doc = item.chunk.doc_id
            if per_doc.get(doc, 0) >= s.max_chunks_per_document:
                continue
            per_doc[doc] = per_doc.get(doc, 0) + 1
            selected.append(item)
            if len(selected) >= top_k:
                break
        return RetrievalResult(selected, len(fused), len(dense), len(sparse))
