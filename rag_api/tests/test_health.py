from fastapi.testclient import TestClient

from contract_intel_api.main import create_app


def test_health_returns_ok():
    client = TestClient(create_app())
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_app_is_wired_to_the_reader_container():
    providers = create_app().state.container.providers
    assert "vector_search" in providers
    assert "vector_index_writer" not in providers
