from pathlib import Path

import pytest
from pydantic import ValidationError

from contract_intel.bootstrap.settings import AppSettings


def test_defaults_use_fakes(monkeypatch):
    monkeypatch.delenv("CONTRACT_INTEL_USE_FAKES", raising=False)
    settings = AppSettings(_env_file=None)
    assert settings.use_fakes is True
    assert settings.storage.bucket == "contracts"


def test_loads_nested_sections_from_environment(monkeypatch):
    monkeypatch.setenv("CONTRACT_INTEL_USE_FAKES", "false")
    monkeypatch.setenv("CONTRACT_INTEL_DATABASE__URL", "postgresql+asyncpg://u:p@db/x")
    monkeypatch.setenv("CONTRACT_INTEL_DATABASE__POOL_SIZE", "12")
    monkeypatch.setenv("CONTRACT_INTEL_LLM__API_KEY", "secret-value")

    settings = AppSettings(_env_file=None)

    assert settings.use_fakes is False
    assert settings.database.url == "postgresql+asyncpg://u:p@db/x"
    assert settings.database.pool_size == 12
    assert settings.llm.api_key.get_secret_value() == "secret-value"
    assert "secret-value" not in repr(settings)


def test_ingestion_defaults(monkeypatch):
    monkeypatch.delenv("CONTRACT_INTEL_INGESTION__MAX_DOCUMENTS", raising=False)
    settings = AppSettings(_env_file=None)
    assert settings.ingestion.max_documents == 5
    assert settings.ingestion.cuad_dir.as_posix().endswith("full_contract_pdf")


def test_ingestion_from_environment(monkeypatch):
    monkeypatch.setenv("CONTRACT_INTEL_INGESTION__CUAD_DIR", "/srv/datasets/cuad")
    monkeypatch.setenv("CONTRACT_INTEL_INGESTION__MAX_DOCUMENTS", "510")

    settings = AppSettings(_env_file=None)

    assert settings.ingestion.cuad_dir == Path("/srv/datasets/cuad")
    assert settings.ingestion.max_documents == 510


def test_max_documents_must_be_positive(monkeypatch):
    monkeypatch.setenv("CONTRACT_INTEL_INGESTION__MAX_DOCUMENTS", "0")
    with pytest.raises(ValidationError):
        AppSettings(_env_file=None)


def test_storage_credentials_are_secret(monkeypatch):
    monkeypatch.setenv("CONTRACT_INTEL_STORAGE__SECRET_ACCESS_KEY", "s3-secret")
    settings = AppSettings(_env_file=None)
    assert settings.storage.secret_access_key is not None
    assert "s3-secret" not in repr(settings)


def test_embedding_and_chunking_defaults(monkeypatch):
    for name in ("MODEL", "DIMENSIONS", "API_KEY"):
        monkeypatch.delenv(f"CONTRACT_INTEL_EMBEDDINGS__{name}", raising=False)
    settings = AppSettings(_env_file=None)
    assert settings.embeddings.model == "voyage-law-2"
    assert settings.embeddings.dimensions == 1024
    assert settings.chunking.max_chars == 2000
    assert settings.chunking.overlap_chars == 200


def test_embeddings_from_environment_keep_key_secret(monkeypatch):
    monkeypatch.setenv("CONTRACT_INTEL_EMBEDDINGS__API_KEY", "voyage-secret")
    monkeypatch.setenv("CONTRACT_INTEL_CHUNKING__MAX_CHARS", "1500")

    settings = AppSettings(_env_file=None)

    assert settings.embeddings.api_key.get_secret_value() == "voyage-secret"
    assert "voyage-secret" not in repr(settings)
    assert settings.chunking.max_chars == 1500


def test_overlap_must_be_smaller_than_window(monkeypatch):
    monkeypatch.setenv("CONTRACT_INTEL_CHUNKING__MAX_CHARS", "200")
    monkeypatch.setenv("CONTRACT_INTEL_CHUNKING__OVERLAP_CHARS", "200")
    with pytest.raises(ValidationError):
        AppSettings(_env_file=None)


def test_llm_and_retrieval_defaults(monkeypatch):
    for name in ("CHAT_MODEL", "FALLBACKS", "EFFORT", "API_KEY"):
        monkeypatch.delenv(f"CONTRACT_INTEL_LLM__{name}", raising=False)
    monkeypatch.delenv("CONTRACT_INTEL_RETRIEVAL__TOP_K", raising=False)
    settings = AppSettings(_env_file=None)
    assert settings.llm.chat_model == "claude-sonnet-5-5"
    assert settings.llm.fallbacks is False
    assert settings.llm.effort == "medium"
    assert settings.llm.input_price_per_million == 2.0
    assert settings.llm.output_price_per_million == 10.0
    assert settings.retrieval.top_k == 8


def test_llm_from_environment(monkeypatch):
    monkeypatch.setenv("CONTRACT_INTEL_LLM__CHAT_MODEL", "claude-opus-5-5")
    monkeypatch.setenv("CONTRACT_INTEL_LLM__EFFORT", "high")
    monkeypatch.setenv("CONTRACT_INTEL_LLM__FALLBACKS", "true")
    monkeypatch.setenv("CONTRACT_INTEL_LLM__API_KEY", "sk-test-secret")

    settings = AppSettings(_env_file=None)

    assert settings.llm.chat_model == "claude-opus-5-5"
    assert settings.llm.effort == "high"
    assert settings.llm.fallbacks is True
    assert "sk-test-secret" not in repr(settings)


@pytest.mark.parametrize(
    ("variable", "value"),
    [
        ("CONTRACT_INTEL_LLM__EFFORT", "extreme"),
        ("CONTRACT_INTEL_RETRIEVAL__TOP_K", "0"),
    ],
)
def test_invalid_llm_or_retrieval_values(monkeypatch, variable, value):
    monkeypatch.setenv(variable, value)
    with pytest.raises(ValidationError):
        AppSettings(_env_file=None)


def test_extraction_and_evaluation_defaults(monkeypatch):
    for name in ("MODEL", "WINDOW_CHARS", "EFFORT"):
        monkeypatch.delenv(f"CONTRACT_INTEL_EXTRACTION__{name}", raising=False)
    monkeypatch.delenv("CONTRACT_INTEL_EVALUATION__LABELS_PATH", raising=False)
    settings = AppSettings(_env_file=None)
    assert settings.extraction.model == "claude-sonnet-5-5"
    assert settings.extraction.window_chars == 24000
    assert settings.extraction.input_price_per_million == 2.0
    assert settings.evaluation.labels_path.name == "master_clauses.csv"


def test_extraction_from_environment(monkeypatch):
    monkeypatch.setenv("CONTRACT_INTEL_EXTRACTION__MODEL", "claude-opus-5-5")
    monkeypatch.setenv("CONTRACT_INTEL_EXTRACTION__WINDOW_CHARS", "12000")
    settings = AppSettings(_env_file=None)
    assert settings.extraction.model == "claude-opus-5-5"
    assert settings.extraction.window_chars == 12000


def test_window_chars_must_be_positive(monkeypatch):
    monkeypatch.setenv("CONTRACT_INTEL_EXTRACTION__WINDOW_CHARS", "0")
    with pytest.raises(ValidationError):
        AppSettings(_env_file=None)
