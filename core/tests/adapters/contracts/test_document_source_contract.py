from dataclasses import dataclass
from pathlib import Path

import pytest

from contract_intel.adapters.outbound.cuad import cuad_document_source as cuad
from contract_intel.adapters.outbound.cuad.cuad_document_source import (
    CuadDirectoryMissingError,
    CuadDocumentSource,
    DuplicateDocumentIdError,
)
from contract_intel.adapters.outbound.in_memory.document_source import (
    InMemoryDocumentSource,
)
from contract_intel.application.ports.outbound.document_source import DocumentSource
from contract_intel.domain.document import Document, DocumentType
from contract_intel.domain.errors import UnknownDocumentError
from contract_intel.domain.ids import ContractId, DocumentId

from .conftest import build_pdf

SAMPLES = {
    "Part_I/Distributor/Alpha Corp_EX-10.1_Distributor Agreement.pdf": "Alpha",
    "Part_II/License/BETA-LICENSE.PDF": "Beta",
}


@dataclass(frozen=True)
class SourceCase:
    source: DocumentSource
    expected_contents: frozenset[bytes]


def _cuad_case(root: Path) -> SourceCase:
    contents = set()
    for relative, text in SAMPLES.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        content = build_pdf(text)
        path.write_bytes(content)
        contents.add(content)
    (root / "Part_I" / "README.txt").write_text("not a contract")
    return SourceCase(CuadDocumentSource(root), frozenset(contents))


def _in_memory_case() -> SourceCase:
    documents = {}
    for name, text in SAMPLES.items():
        document_id = DocumentId(text.lower())
        document = Document(document_id, ContractId(text), name, DocumentType.OTHER)
        documents[document_id] = (document, build_pdf(text))
    contents = frozenset(content for _, content in documents.values())
    return SourceCase(InMemoryDocumentSource(documents), contents)


@pytest.fixture(params=["in_memory", "cuad"])
def case(request: pytest.FixtureRequest, tmp_path: Path) -> SourceCase:
    if request.param == "cuad":
        return _cuad_case(tmp_path)
    return _in_memory_case()


async def test_lists_every_document_once(case):
    documents = await case.source.list_documents()

    assert len(documents) == len(SAMPLES)
    assert len({d.id for d in documents}) == len(SAMPLES)


async def test_fetches_the_content_of_listed_documents(case):
    documents = await case.source.list_documents()

    contents = {await case.source.fetch_content(d.id) for d in documents}

    assert contents == case.expected_contents


async def test_unknown_document_raises(case):
    with pytest.raises(UnknownDocumentError):
        await case.source.fetch_content(DocumentId("missing"))


class TestCuadSpecifics:
    async def test_ids_are_readable_stable_slugs(self, tmp_path):
        _cuad_case(tmp_path)
        first = await CuadDocumentSource(tmp_path).list_documents()
        again = await CuadDocumentSource(tmp_path).list_documents()

        assert [d.id for d in first] == [d.id for d in again]
        assert first[0].id.startswith("alpha-corp-ex-10-1-distributor-agreement-")

    async def test_one_contract_per_document(self, tmp_path):
        _cuad_case(tmp_path)
        documents = await CuadDocumentSource(tmp_path).list_documents()

        assert all(str(d.contract_id) == str(d.id) for d in documents)
        assert documents[1].title == "BETA-LICENSE"

    def test_long_names_are_truncated_but_unique(self):
        long_a = Path("a" * 200 + "-one.pdf")
        long_b = Path("a" * 200 + "-two.pdf")

        id_a, id_b = cuad.document_id_for(long_a), cuad.document_id_for(long_b)

        assert id_a != id_b
        assert len(id_a) <= cuad.SLUG_MAX_LENGTH + 1 + cuad.PATH_HASH_LENGTH

    async def test_duplicate_ids_fail(self, tmp_path, monkeypatch):
        _cuad_case(tmp_path)
        monkeypatch.setattr(cuad, "document_id_for", lambda _: DocumentId("same"))

        with pytest.raises(DuplicateDocumentIdError):
            await CuadDocumentSource(tmp_path).list_documents()

    async def test_missing_directory_explains_how_to_download(self, tmp_path):
        with pytest.raises(CuadDirectoryMissingError, match="download_cuad"):
            await CuadDocumentSource(tmp_path / "absent").list_documents()
