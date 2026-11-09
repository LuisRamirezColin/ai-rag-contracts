"""Fail when tracked files contain identifiers that must not be published.

Two sources of patterns:

* Generic regexes versioned in ``scripts/forbidden_patterns.txt``.
* Sensitive names (employers, clients) from the git-ignored ``.forbidden-names``
  file or the ``FORBIDDEN_NAMES`` environment variable (CI secret). They are
  never versioned, since listing them would publish them.

Exit code 0 when clean, 1 when any match is found.
"""

import os
import re
import subprocess
import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PATTERNS_FILE = REPO_ROOT / "scripts" / "forbidden_patterns.txt"
NAMES_FILE = REPO_ROOT / ".forbidden-names"
NAMES_ENV_VAR = "FORBIDDEN_NAMES"
ALLOW_MARKER = "forbidden-identifiers: allow"
COMMENT_PREFIX = "#"


@dataclass(frozen=True, slots=True)
class Finding:
    """A forbidden pattern found in a file."""

    path: Path
    line_number: int
    pattern: str

    def __str__(self) -> str:
        return f"{self.path}:{self.line_number}: matches forbidden pattern"


def _meaningful_lines(text: str) -> list[str]:
    stripped = (line.strip() for line in text.splitlines())
    return [line for line in stripped if line and not line.startswith(COMMENT_PREFIX)]


def load_generic_patterns(patterns_file: Path) -> list[re.Pattern[str]]:
    """Compile the versioned generic patterns."""
    return [re.compile(line) for line in _meaningful_lines(patterns_file.read_text())]


def load_sensitive_names(
    names_file: Path, environ: dict[str, str] | os._Environ[str]
) -> list[str] | None:
    """Return sensitive names from the local file or env var; ``None`` if absent."""
    if names_file.is_file():
        return _meaningful_lines(names_file.read_text())
    raw = environ.get(NAMES_ENV_VAR)
    if raw:
        return [name.strip() for name in re.split(r"[,\n]", raw) if name.strip()]
    return None


def names_to_patterns(names: Iterable[str]) -> list[re.Pattern[str]]:
    """Compile names into case-insensitive whole-word patterns."""
    return [
        re.compile(rf"(?<![A-Za-z0-9]){re.escape(name)}(?![A-Za-z0-9])", re.IGNORECASE)
        for name in names
    ]


def tracked_files(repo_root: Path) -> list[Path]:
    """List files tracked or staged in git, relative to ``repo_root``."""
    output = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],  # noqa: S607
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return [Path(line) for line in output.splitlines() if line]


def scan_text(
    path: Path, text: str, patterns: Sequence[re.Pattern[str]]
) -> list[Finding]:
    """Return every line of ``text`` that matches one of ``patterns``."""
    return [
        Finding(path=path, line_number=number, pattern=pattern.pattern)
        for number, line in enumerate(text.splitlines(), start=1)
        if ALLOW_MARKER not in line
        for pattern in patterns
        if pattern.search(line)
    ]


def scan_files(
    repo_root: Path, paths: Iterable[Path], patterns: Sequence[re.Pattern[str]]
) -> list[Finding]:
    """Scan text files under ``repo_root``; binary files are skipped."""
    findings: list[Finding] = []
    for path in paths:
        full_path = repo_root / path
        if full_path.resolve() == PATTERNS_FILE or not full_path.is_file():
            continue
        try:
            text = full_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        findings.extend(scan_text(path, text, patterns))
    return findings


def main() -> int:
    """Run the scan over the repository and report findings."""
    patterns = load_generic_patterns(PATTERNS_FILE)
    names = load_sensitive_names(NAMES_FILE, os.environ)
    if names is None:
        print(
            f"warning: no {NAMES_FILE.name} file or {NAMES_ENV_VAR} variable; "
            "checking generic patterns only",
            file=sys.stderr,
        )
    else:
        patterns.extend(names_to_patterns(names))

    findings = scan_files(REPO_ROOT, tracked_files(REPO_ROOT), patterns)
    for finding in findings:
        print(finding)
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
