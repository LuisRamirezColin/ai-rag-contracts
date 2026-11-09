from pathlib import Path

import check_forbidden_identifiers as scanner

# Sample values are assembled at runtime so this file never matches the scan.
SAMPLE_EMAIL = "jane.doe" + "@" + "corp-mail.io"
SAMPLE_NAME = "Acme" + "corp"


def test_generic_patterns_detect_email_with_file_and_line(tmp_path):
    patterns = scanner.load_generic_patterns(scanner.PATTERNS_FILE)
    (tmp_path / "notes.md").write_text(f"intro\ncontact {SAMPLE_EMAIL}\n")

    findings = scanner.scan_files(tmp_path, [Path("notes.md")], patterns)

    assert [(f.path, f.line_number) for f in findings] == [(Path("notes.md"), 2)]


def test_example_domains_are_allowed():
    patterns = scanner.load_generic_patterns(scanner.PATTERNS_FILE)
    findings = scanner.scan_text(Path("a.md"), "user" + "@example.com", patterns)
    assert findings == []


def test_allow_marker_skips_the_line():
    patterns = scanner.load_generic_patterns(scanner.PATTERNS_FILE)
    line = f"{SAMPLE_EMAIL}  # {scanner.ALLOW_MARKER}"
    assert scanner.scan_text(Path("a.md"), line, patterns) == []


def test_sensitive_names_match_whole_words_case_insensitively():
    patterns = scanner.names_to_patterns([SAMPLE_NAME])
    text = f"Signed with {SAMPLE_NAME.upper()}.\n{SAMPLE_NAME}ish is fine"
    findings = scanner.scan_text(Path("a.md"), text, patterns)
    assert [f.line_number for f in findings] == [1]


def test_names_come_from_file_before_environment(tmp_path):
    names_file = tmp_path / ".forbidden-names"
    names_file.write_text("# comment\nfirst\n\nsecond\n")
    names = scanner.load_sensitive_names(names_file, {"FORBIDDEN_NAMES": "other"})
    assert names == ["first", "second"]


def test_names_fall_back_to_environment(tmp_path):
    names = scanner.load_sensitive_names(
        tmp_path / "missing", {"FORBIDDEN_NAMES": "one, two\nthree"}
    )
    assert names == ["one", "two", "three"]


def test_missing_name_source_warns_without_failing(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(scanner, "NAMES_FILE", tmp_path / "missing")
    monkeypatch.delenv("FORBIDDEN_NAMES", raising=False)
    monkeypatch.setattr(scanner, "tracked_files", lambda _root: [])

    assert scanner.main() == 0
    assert "warning" in capsys.readouterr().err


def test_binary_files_are_skipped(tmp_path):
    (tmp_path / "blob.bin").write_bytes(b"\xff\xfe\x00" + SAMPLE_EMAIL.encode())
    patterns = scanner.load_generic_patterns(scanner.PATTERNS_FILE)
    assert scanner.scan_files(tmp_path, [Path("blob.bin")], patterns) == []
