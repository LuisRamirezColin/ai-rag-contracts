import socket

import pytest

from contract_intel.application.ports.outbound.vector_index_writer import (
    VectorIndexWriter,
)
from contract_intel.application.ports.outbound.vector_search import VectorSearch
from contract_intel.bootstrap.containers import (
    ReaderContainer,
    RealAdaptersUnavailableError,
    WriterContainer,
    build_reader_container,
    build_writer_container,
)
from contract_intel.bootstrap.settings import AppSettings


@pytest.fixture
def no_network(monkeypatch):
    def refuse(*_args, **_kwargs):
        raise AssertionError("network access attempted while building containers")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)


@pytest.fixture
def fake_settings():
    return AppSettings(_env_file=None, use_fakes=True)


def _resolve_all(container):
    resolved = []
    for name, provider in container.providers.items():
        if name == "core":
            resolved.extend(_resolve_all(container.core))
        elif name != "settings":
            resolved.append(provider())
    return resolved


def test_writer_container_builds_without_network(no_network, fake_settings):
    container = build_writer_container(fake_settings)
    instances = _resolve_all(container)
    assert any(isinstance(i, VectorIndexWriter) for i in instances)


def test_reader_container_builds_without_network(no_network, fake_settings):
    container = build_reader_container(fake_settings)
    instances = _resolve_all(container)
    assert any(isinstance(i, VectorSearch) for i in instances)


def test_reader_container_resolves_no_index_writer(fake_settings):
    instances = _resolve_all(build_reader_container(fake_settings))
    assert not any(isinstance(i, VectorIndexWriter) for i in instances)


def test_only_the_writer_container_declares_an_index_writer():
    assert "vector_index_writer" in WriterContainer.providers
    assert "vector_index_writer" not in ReaderContainer.providers


def test_real_adapters_are_rejected_until_implemented():
    with pytest.raises(RealAdaptersUnavailableError):
        build_reader_container(AppSettings(_env_file=None, use_fakes=False))
