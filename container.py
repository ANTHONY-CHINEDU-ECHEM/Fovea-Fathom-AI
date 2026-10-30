"""Service wiring: builds the index, router, pipeline, cache and audit log once per process."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from fovea.audit import AuditLog
from fovea.cache import AnswerCache, build_cache
from fovea.config import Settings, get_settings
from fovea.generation.pipeline import AnswerPipeline
from fovea.llm.router import LLMRouter
from fovea.observability import metrics
from fovea.retrieval.index import KnowledgeIndex

log = logging.getLogger(__name__)


@dataclass
class Container:
    settings: Settings
    index: KnowledgeIndex
    router: LLMRouter
    pipeline: AnswerPipeline
    cache: AnswerCache
    audit: AuditLog

    @property
    def index_version(self) -> str:
        return str(self.index.manifest.get("built_at", "unbuilt"))


def load_or_build_index(settings: Settings) -> KnowledgeIndex:
    directory = Path(settings.index_dir)
    if KnowledgeIndex.exists(directory):
        return KnowledgeIndex.load(directory, settings)
    log.warning("no index at %s; building from the verified seed snapshot", directory)
    from ingestion.pipeline import build_index, load_seed

    index, _ = build_index(settings, load_seed(), directory)
    return index


def build_container(settings: Settings | None = None) -> Container:
    settings = settings or get_settings()
    index = load_or_build_index(settings)
    metrics.INDEX_CHUNKS.set(len(index))
    router = LLMRouter(settings)
    return Container(
        settings=settings,
        index=index,
        router=router,
        pipeline=AnswerPipeline(index, router, settings),
        cache=build_cache(settings.cache_backend, settings.redis_url),
        audit=AuditLog(settings.audit_path, settings.feedback_path, settings.audit_salt),
    )


@lru_cache(maxsize=1)
def get_container() -> Container:
    return build_container()
