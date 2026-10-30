"""Shared fixtures: an offline index built once from the verified seed snapshot."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from fovea.config import Settings, override_settings, reset_settings
from fovea.generation.pipeline import AnswerPipeline
from fovea.llm.router import LLMRouter
from fovea.retrieval.index import KnowledgeIndex


@pytest.fixture(scope="session")
def settings(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Settings]:
    root = tmp_path_factory.mktemp("fovea")
    configured = override_settings(
        llm_provider="extractive",
        llm_fallbacks=[],
        embedding_backend="hashing",
        reranker_backend="lexical",
        vector_backend="memory",
        index_dir=str(root / "index"),
        audit_path=str(root / "audit.jsonl"),
        feedback_path=str(root / "feedback.jsonl"),
        api_keys=[],
        admin_api_keys=[],
        rate_limit_per_minute=10_000,
    )
    yield configured
    reset_settings()


@pytest.fixture(scope="session")
def index(settings: Settings) -> KnowledgeIndex:
    from ingestion.pipeline import build_index, load_seed

    built, _ = build_index(settings, load_seed(), Path(settings.index_dir))
    return built


@pytest.fixture(scope="session")
def pipeline(index: KnowledgeIndex, settings: Settings) -> AnswerPipeline:
    return AnswerPipeline(index, LLMRouter(settings), settings)


@pytest.fixture(scope="session")
def client(index: KnowledgeIndex, settings: Settings):  # type: ignore[no-untyped-def]
    from fastapi.testclient import TestClient

    from fovea import container
    from fovea.main import create_app

    container.get_container.cache_clear()
    return TestClient(create_app())
