"""Typed settings read from the environment.

Every setting uses the ``FF_`` prefix so deployments can keep Fovea Fathom AI settings apart
from other services. List settings take comma separated values. Settings are read once per
process through :func:`get_settings` and may be overridden in tests with
:func:`override_settings`.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field, fields, replace
from functools import lru_cache
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGE_ROOT = Path(__file__).resolve().parent
KNOWLEDGE_DIR = PACKAGE_ROOT / "knowledge"


def _seed_dir() -> Path:
    """Seed snapshot location for a source checkout or an installed wheel."""
    candidate = REPO_ROOT / "ingestion" / "data" / "seed"
    if candidate.exists():
        return candidate
    import importlib.util

    spec = importlib.util.find_spec("ingestion")
    if spec and spec.origin:
        return Path(spec.origin).resolve().parent / "data" / "seed"
    return candidate


SEED_DIR = _seed_dir()
DATA_DIR = REPO_ROOT / "data"


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default)


def _list(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    """All runtime configuration. Defaults run fully offline on the seed snapshot."""

    environment: str = "development"
    log_level: str = "INFO"
    log_json: bool = False

    # Language models
    llm_provider: str = "anthropic"
    llm_fallbacks: list[str] = field(default_factory=lambda: ["openai", "extractive"])
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-5-5"
    openai_api_key: str = ""
    openai_model: str = "gpt-4.1"
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.1:8b"
    llm_timeout_seconds: float = 60.0
    llm_max_tokens: int = 1400
    llm_temperature: float = 0.1
    circuit_failure_threshold: int = 3
    circuit_reset_seconds: float = 60.0

    # Retrieval
    embedding_backend: str = "hashing"
    embedding_model: str = "BAAI/bge-base-en-v1.5"
    embedding_dim: int = 512
    reranker_backend: str = "lexical"
    reranker_model: str = "BAAI/bge-reranker-base"
    vector_backend: str = "memory"
    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: str = "fovea_chunks"
    index_dir: str = str(DATA_DIR / "index")
    top_k_dense: int = 40
    top_k_sparse: int = 40
    rerank_depth: int = 30
    top_k_final: int = 8
    max_chunks_per_document: int = 2
    rrf_k: int = 60

    # Clinical priors
    evidence_weight: float = 0.30
    recency_half_life_years: float = 6.0
    uk_bonus: float = 0.15
    condition_bonus: float = 0.40
    drug_bonus: float = 0.20
    superseded_factor: float = 0.5

    # Answerability and validation
    min_evidence_score: float = 0.30
    min_query_coverage: float = 0.40
    min_citation_coverage: float = 0.80
    min_faithfulness: float = 0.50

    # Service
    api_keys: list[str] = field(default_factory=list)
    admin_api_keys: list[str] = field(default_factory=list)
    rate_limit_per_minute: int = 60
    cors_origins: list[str] = field(
        default_factory=lambda: ["http://localhost:5173", "http://localhost:8080"]
    )
    cache_backend: str = "memory"
    redis_url: str = "redis://localhost:6379/0"
    cache_ttl_seconds: int = 3600
    audit_path: str = str(DATA_DIR / "audit" / "audit.jsonl")
    feedback_path: str = str(DATA_DIR / "audit" / "feedback.jsonl")
    audit_salt: str = "local-development-salt-change-me"

    # Ingestion credentials
    ncbi_api_key: str = ""
    ncbi_email: str = ""
    nice_api_key: str = ""

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"

    def provider_chain(self, preferred: str | None = None) -> list[str]:
        """Return the ordered, de duplicated provider chain ending in the extractive generator."""
        chain: list[str] = []
        for name in [preferred or self.llm_provider, *self.llm_fallbacks, "extractive"]:
            if name and name not in chain:
                chain.append(name)
        return chain


_ENV_MAP: dict[str, str] = {f.name: f"FF_{f.name.upper()}" for f in fields(Settings)}
_ENV_MAP.update(
    {
        "anthropic_api_key": "ANTHROPIC_API_KEY",
        "openai_api_key": "OPENAI_API_KEY",
        "ncbi_api_key": "NCBI_API_KEY",
        "ncbi_email": "NCBI_EMAIL",
        "nice_api_key": "NICE_SYNDICATION_API_KEY",
    }
)


def load_settings() -> Settings:
    """Build settings from the environment, converting each value to its declared type."""
    defaults = Settings()
    values: dict[str, Any] = {}
    for f in fields(Settings):
        env_name = _ENV_MAP[f.name]
        if env_name not in os.environ:
            continue
        raw = _env(env_name, "")
        current = getattr(defaults, f.name)
        if isinstance(current, bool):
            values[f.name] = _bool(raw)
        elif isinstance(current, int):
            values[f.name] = int(raw)
        elif isinstance(current, float):
            values[f.name] = float(raw)
        elif isinstance(current, list):
            values[f.name] = _list(raw)
        else:
            values[f.name] = raw
    return replace(defaults, **values)


_OVERRIDE: Settings | None = None


@lru_cache(maxsize=1)
def _cached_settings() -> Settings:
    return load_settings()


def get_settings() -> Settings:
    """Return the active settings: an override when one is set, otherwise the environment."""
    return _OVERRIDE if _OVERRIDE is not None else _cached_settings()


def override_settings(**changes: Any) -> Settings:
    """Replace the active settings, used by tests and the evaluation harness."""
    global _OVERRIDE
    _OVERRIDE = replace(load_settings(), **changes)
    return _OVERRIDE


def reset_settings() -> None:
    """Restore environment driven settings after :func:`override_settings`."""
    global _OVERRIDE
    _OVERRIDE = None
    _cached_settings.cache_clear()
