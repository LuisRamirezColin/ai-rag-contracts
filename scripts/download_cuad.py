"""Download the public CUAD v1 dataset into ``data/cuad/`` (git-ignored).

The archive is verified against a pinned SHA-256 before anything is extracted,
and extraction happens in a temporary sibling directory that is renamed into
place only on success, so a failed run never leaves partial data behind.

Usage: ``uv run python scripts/download_cuad.py``
"""

import hashlib
import shutil
import sys
import tempfile
import urllib.request
import zipfile
from collections.abc import Callable
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
TARGET_DIR = REPO_ROOT / "data" / "cuad"
CUAD_URL = "https://zenodo.org/records/4595826/files/CUAD_v1.zip?download=1"
# SHA-256 of CUAD_v1.zip; its MD5 matches the checksum published by Zenodo.
CUAD_SHA256 = "88b694d99007d39777fa44cd72daf8297773d285dc3eab0091ba32078888d18e"
ARCHIVE_NAME = "CUAD_v1.zip"
HASH_CHUNK_BYTES = 1024 * 1024
DOWNLOAD_TIMEOUT_SECONDS = 300

Fetch = Callable[[str, Path], None]


class ChecksumMismatchError(RuntimeError):
    """Raised when the downloaded archive does not match the pinned SHA-256."""

    def __init__(self, expected: str, actual: str) -> None:
        super().__init__(f"SHA-256 mismatch: expected {expected}, got {actual}")


def fetch_over_https(url: str, destination: Path) -> None:
    """Stream ``url`` into ``destination``."""
    if not url.startswith("https://"):
        raise ValueError(f"Refusing non-HTTPS URL: {url}")
    with (
        urllib.request.urlopen(url, timeout=DOWNLOAD_TIMEOUT_SECONDS) as response,  # noqa: S310 - scheme checked above
        destination.open("wb") as file,
    ):
        shutil.copyfileobj(response, file)


def sha256_of(path: Path) -> str:
    """Return the hex SHA-256 digest of the file at ``path``."""
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(HASH_CHUNK_BYTES), b""):
            digest.update(chunk)
    return digest.hexdigest()


def install_dataset(
    target_dir: Path,
    *,
    url: str = CUAD_URL,
    expected_sha256: str = CUAD_SHA256,
    fetch: Fetch = fetch_over_https,
) -> bool:
    """Download, verify and extract the dataset into ``target_dir``.

    Returns:
        ``True`` when the dataset was installed, ``False`` when it already existed.

    Raises:
        ChecksumMismatchError: If the archive does not match ``expected_sha256``.
    """
    if target_dir.exists():
        return False
    target_dir.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=target_dir.parent, prefix=".cuad-") as staging:
        archive = Path(staging) / ARCHIVE_NAME
        fetch(url, archive)
        actual_sha256 = sha256_of(archive)
        if actual_sha256 != expected_sha256:
            raise ChecksumMismatchError(expected_sha256, actual_sha256)
        extracted = Path(staging) / "extracted"
        with zipfile.ZipFile(archive) as zip_file:
            zip_file.extractall(extracted)
        extracted.rename(target_dir)
    return True


def main() -> int:
    """Install the dataset and report where it lives."""
    if install_dataset(TARGET_DIR):
        print(f"CUAD installed in {TARGET_DIR}")
    else:
        print(f"CUAD already present in {TARGET_DIR}; delete it to download again")
    return 0


if __name__ == "__main__":
    sys.exit(main())
