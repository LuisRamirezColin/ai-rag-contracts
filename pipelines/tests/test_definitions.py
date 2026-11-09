from contract_intel_pipelines.definitions import CONTAINER_RESOURCE_KEY, defs


def test_definitions_expose_the_writer_container():
    assert defs.resources is not None
    container = defs.resources[CONTAINER_RESOURCE_KEY]
    assert "vector_index_writer" in container.providers
