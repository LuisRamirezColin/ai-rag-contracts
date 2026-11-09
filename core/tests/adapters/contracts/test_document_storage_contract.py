import os
import uuid
from collections.abc import Iterator

import boto3
import pytest

from contract_intel.adapters.outbound.in_memory.document_storage import (
    InMemoryDocumentStorage,
)
from contract_intel.adapters.outbound.s3.s3_document_storage import (
    S3DocumentStorage,
    S3Location,
)
from contract_intel.application.ports.outbound.document_storage import DocumentStorage
from contract_intel.domain.errors import UnknownDocumentError
from contract_intel.domain.ids import DocumentId

DOC = DocumentId("doc-1")
LOCALSTACK_URL = os.environ.get(
    "CONTRACT_INTEL_STORAGE__ENDPOINT_URL", "http://localhost:4566"
)
LOCALSTACK_CREDENTIAL = "test"


@pytest.fixture
def isolated_bucket() -> Iterator[S3Location]:
    location = S3Location(
        bucket=f"test-{uuid.uuid4().hex}",
        region="us-east-1",
        endpoint_url=LOCALSTACK_URL,
        access_key_id=LOCALSTACK_CREDENTIAL,
        secret_access_key=LOCALSTACK_CREDENTIAL,
    )
    client = boto3.client(
        "s3",
        region_name=location.region,
        endpoint_url=location.endpoint_url,
        aws_access_key_id=location.access_key_id,
        aws_secret_access_key=location.secret_access_key,
    )
    client.create_bucket(Bucket=location.bucket)
    yield location
    for item in client.list_objects_v2(Bucket=location.bucket).get("Contents", []):
        client.delete_object(Bucket=location.bucket, Key=item["Key"])
    client.delete_bucket(Bucket=location.bucket)


@pytest.fixture(params=["in_memory", pytest.param("s3", marks=pytest.mark.integration)])
def storage(request: pytest.FixtureRequest) -> DocumentStorage:
    if request.param == "s3":
        location: S3Location = request.getfixturevalue("isolated_bucket")
        return S3DocumentStorage(location)
    return InMemoryDocumentStorage()


async def test_saved_content_is_loaded_back(storage):
    await storage.save(DOC, b"%PDF original")

    assert await storage.load(DOC) == b"%PDF original"
    assert await storage.exists(DOC)


async def test_save_replaces_previous_content(storage):
    await storage.save(DOC, b"first")
    await storage.save(DOC, b"second")

    assert await storage.load(DOC) == b"second"


async def test_missing_document(storage):
    assert not await storage.exists(DOC)
    with pytest.raises(UnknownDocumentError):
        await storage.load(DOC)


async def test_empty_content_counts_as_missing(storage):
    await storage.save(DOC, b"")

    assert not await storage.exists(DOC)
