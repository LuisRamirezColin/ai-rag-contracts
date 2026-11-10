import hashlib
import io
import zipfile
from pathlib import Path

import download_cuad
import pytest

PDF_MEMBER = "CUAD_v1/full_contract_pdf/Part_I/Sample/sample.pdf"


def _archive_bytes() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zip_file:
        zip_file.writestr(PDF_MEMBER, b"%PDF-1.4 fake")
    return buffer.getvalue()


def _serving(content: bytes) -> download_cuad.Fetch:
    def fetch(url: str, destination: Path) -> None:
        destination.write_bytes(content)

    return fetch


def test_valid_archive_is_extracted_into_target(tmp_path):
    content = _archive_bytes()
    target = tmp_path / "data" / "cuad"

    installed = download_cuad.install_dataset(
        target,
        expected_sha256=hashlib.sha256(content).hexdigest(),
        fetch=_serving(content),
    )

    assert installed is True
    assert (target / PDF_MEMBER).read_bytes() == b"%PDF-1.4 fake"


def test_checksum_mismatch_leaves_no_data(tmp_path):
    target = tmp_path / "data" / "cuad"

    with pytest.raises(download_cuad.ChecksumMismatchError):
        download_cuad.install_dataset(
            target, expected_sha256="0" * 64, fetch=_serving(_archive_bytes())
        )

    assert not target.exists()
    assert list(target.parent.iterdir()) == []


def test_existing_target_is_left_untouched(tmp_path):
    target = tmp_path / "cuad"
    target.mkdir()

    def must_not_fetch(url: str, destination: Path) -> None:
        raise AssertionError("fetch must not run")

    assert download_cuad.install_dataset(target, fetch=must_not_fetch) is False


def test_non_https_urls_are_refused(tmp_path):
    with pytest.raises(ValueError, match="non-HTTPS"):
        download_cuad.fetch_over_https("http://example.com/x.zip", tmp_path / "x")
