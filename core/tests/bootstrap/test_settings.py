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
