import asyncio
from dataclasses import dataclass
from functools import cached_property

import boto3
from botocore.exceptions import ClientError
from mypy_boto3_s3 import S3Client

from contract_intel.domain.errors import UnknownDocumentError
from contract_intel.domain.ids import DocumentId

RAW_PREFIX = "raw"
PDF_CONTENT_TYPE = "application/pdf"
_MISSING_ERROR_CODES = frozenset({"404", "NoSuchKey", "NotFound"})


@dataclass(frozen=True, slots=True)
class S3Location:
    """Where and how to reach the bucket that holds raw documents."""

    bucket: str
    region: str
    endpoint_url: str | None = None
    access_key_id: str | None = None
    secret_access_key: str | None = None


def object_key(document_id: DocumentId) -> str:
    """Return the object key of a document's original file."""
    return f"{RAW_PREFIX}/{document_id}.pdf"


def _is_missing(error: ClientError) -> bool:
    return error.response.get("Error", {}).get("Code") in _MISSING_ERROR_CODES


class S3DocumentStorage:
    """Raw document files stored as objects in an S3-compatible bucket."""

    def __init__(self, location: S3Location) -> None:
        self._location = location

    @cached_property
    def _client(self) -> S3Client:
        return boto3.client(
            "s3",
            region_name=self._location.region,
            endpoint_url=self._location.endpoint_url,
            aws_access_key_id=self._location.access_key_id,
            aws_secret_access_key=self._location.secret_access_key,
        )

    async def save(self, document_id: DocumentId, content: bytes) -> None:
        """Upload ``content``, replacing any previous object."""
        await asyncio.to_thread(
            self._client.put_object,
            Bucket=self._location.bucket,
            Key=object_key(document_id),
            Body=content,
            ContentType=PDF_CONTENT_TYPE,
        )

    async def load(self, document_id: DocumentId) -> bytes:
        """Download the stored object.

        Raises:
            UnknownDocumentError: If no object exists for ``document_id``.
        """
        return await asyncio.to_thread(self._download, document_id)

    async def exists(self, document_id: DocumentId) -> bool:
        """Tell whether a non-empty object is stored for ``document_id``."""
        return await asyncio.to_thread(self._has_content, document_id)

    def _download(self, document_id: DocumentId) -> bytes:
        try:
            response = self._client.get_object(
                Bucket=self._location.bucket, Key=object_key(document_id)
            )
        except ClientError as error:
            if _is_missing(error):
                raise UnknownDocumentError(document_id) from error
            raise
        return response["Body"].read()

    def _has_content(self, document_id: DocumentId) -> bool:
        try:
            head = self._client.head_object(
                Bucket=self._location.bucket, Key=object_key(document_id)
            )
        except ClientError as error:
            if _is_missing(error):
                return False
            raise
        return head["ContentLength"] > 0
