"""Read-only, redacted repository secret/generated-file audit (stdlib only).

No matched value or source line is emitted. Local mode compares protected secret
values in memory against every regular file, including checkpoint/binary bytes.
No upload, project-code execution, symlink traversal or file modification occurs.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
import hashlib
import os
from pathlib import Path
import re
import subprocess
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
TEXT_LIMIT = 8 * 1024 * 1024
SENSITIVE_KEY = r"(?:password|passwd|pwd|api[_-]?key|access[_-]?token|refresh[_-]?token|client[_-]?secret|secret|smtppass|authorization|cookie|session[_-]?token)"
ASSIGNMENT = re.compile(rf"(?i)(?<![\w-])(?:[\"']?{SENSITIVE_KEY}[\"']?)\s*[:=]\s*([\"'])([^\r\n]*?)\1")
PHP_ASSIGNMENT = re.compile(rf"(?i)\$(?:{SENSITIVE_KEY})\s*=\s*([\"'])([^\r\n]*?)\1")
PATTERNS = {
    "private_key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |ENCRYPTED )?PRIVATE KEY-----"),
    "github_token": re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{30,})\b"),
    "openai_token": re.compile(r"\bsk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{20,}\b"),
    "aws_access_key": re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
    "jwt": re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"),
    "credential_url": re.compile(r"(?i)\b(?:https?|postgres(?:ql)?|mysql|mssql)://[^\s/@:]+:[^\s/@]+@"),
    "credential_connection_string": re.compile(r"(?i)(?<![\w-])(?:password|pwd)\s*=\s*([A-Za-z0-9_~!@#$%^&*+/-]{8,})(?=[;\"'\s]|$)"),
    "authorization_header": re.compile(r"(?i)\b(?:authorization\s*[:=]\s*[\"']?\s*(?:bearer|basic)\s+)([A-Za-z0-9_+./=-]{12,})"),
    "cookie_header": re.compile(r"(?im)^\s*(?:cookie|set-cookie)\s*:\s*[^\s;=]+=[^\s;]{8,}"),
}
SAFE_LITERALS = {"", "password", "secret", "token", "api_key", "authorization", "cookie", "bearer", "basic", "redacted", "<redacted>", "[redacted]", "changeme", "example", "placeholder", "not-a-secret", "not-a-real-secret", "fake"}
TEXT_SUFFIXES = {".py", ".php", ".ps1", ".json", ".toml", ".ini", ".env", ".log", ".txt", ".md", ".yml", ".yaml", ".xml", ".html", ".csv", ".sql", ".conf", ".cfg", ".reg"}
# Existing negative security tests deliberately contain dummy credential syntax.
# Allow only these exact reviewed source lines, never arbitrary test directories.
# The line digest is of public test code, not of a credential value.
REVIEWED_SYNTHETIC_LINES = {
    ("tests/test_handoff_bridge.py", "credential_url", "150c74489f79da7afa6b26bc5e00879d2541fb39cf3a9e668b317aed4d67bcd5"),
    ("tests/test_handoff_bridge.py", "credential_connection_string", "5232318d7ced23bb7273e8303c21c00eb332b62e790445636ebe913bc1bf6428"),
    ("tests/test_web_pipeline.py", "credential_url", "740cce2ab01af5d8453acfe173566fa3c8d95678e04807ed497d49f2e2cd2ecc"),
}


def safe_placeholder(value: str) -> bool:
    lowered = value.strip().lower()
    return (lowered in SAFE_LITERALS
            or lowered.startswith(("test-", "fake-", "dummy-", "example-", "${", "{", "<", "runtime/", "runtime\\"))
            or lowered.endswith((".local.json", ".local.txt"))
            or "os.environ" in lowered or "getenv(" in lowered)


def scan_text(text: str) -> list[dict]:
    """Return only rule and line, never matched values or source lines."""
    findings: set[tuple[str, int]] = set()
    for rule, pattern in PATTERNS.items():
        for match in pattern.finditer(text):
            if rule == "credential_connection_string" and safe_placeholder(match.group(1)):
                continue
            findings.add((rule, text.count("\n", 0, match.start()) + 1))
    for pattern in (ASSIGNMENT, PHP_ASSIGNMENT):
        for match in pattern.finditer(text):
            rest = text[match.end():].split("\n", 1)[0]
            # A constant prefix joined immediately to fresh cryptographic random
            # bytes is a generator expression, not an embedded credential.
            if re.match(r"\s*\+\s*secrets\.token_urlsafe\(", rest) or re.match(r"\s*\.\s*rtrim\(strtr\(base64_encode\(random_bytes\(", rest):
                continue
            if not safe_placeholder(match.group(2)):
                findings.add(("literal_credential_assignment", text.count("\n", 0, match.start()) + 1))
    return [{"rule": rule, "line": line} for rule, line in sorted(findings)]


def excluded_by_policy(relative: str) -> bool:
    path = Path(relative)
    parts, name = path.parts, path.name.lower()
    return (bool(parts and parts[0] in {"runtime", "data", "models"})
            or relative.replace("\\", "/").startswith("research/browser_research/")
            or (bool(parts and parts[0] == "experiments") and "evidence" in parts)
            or bool(set(parts) & {"__pycache__", ".venv", "venv", ".pytest_cache", ".mypy_cache", ".ruff_cache", "private-config", "downloads", "backups", ".idea", ".vscode"})
            or name.startswith(".env")
            or name.endswith((".local.json", ".local.toml", ".key", ".pem", ".pfx", ".p12", ".log", ".pyc", ".pyo", ".pyd", ".sqlite", ".sqlite3", ".db", ".mdf", ".ndf", ".ldf", ".bak", ".parquet", ".pt", ".pth", ".onnx", ".safetensors"))
            or name == "credentials.local.txt" or ".secret." in name
            or any(part.endswith(".egg-info") for part in parts))


def reviewed_synthetic(relative: str, finding: dict, lines: list[str]) -> bool:
    line = finding.get("line")
    if not line or not 1 <= line <= len(lines):
        return False
    digest = hashlib.sha256(lines[line - 1].encode("utf-8")).hexdigest()
    return (relative, finding["rule"], digest) in REVIEWED_SYNTHETIC_LINES


def git_paths(root: Path, tracked: bool) -> list[Path]:
    args = ["git", "-C", str(root), "ls-files", "-z"]
    if not tracked:
        args.extend(["--cached", "--others", "--exclude-standard"])
    completed = subprocess.run(args, capture_output=True, check=True)
    return sorted({root / os.fsdecode(item) for item in completed.stdout.split(b"\0") if item})


def local_paths(root: Path) -> tuple[list[Path], list[str]]:
    paths, omitted_links = [], []
    for directory, folders, files in os.walk(root, followlinks=False):
        folders[:] = [name for name in folders if name != ".git"]
        for name in list(folders):
            path = Path(directory) / name
            if path.is_symlink() or path.is_junction():
                omitted_links.append(path.relative_to(root).as_posix())
                folders.remove(name)
        for name in files:
            path = Path(directory) / name
            if path.is_symlink():
                omitted_links.append(path.relative_to(root).as_posix())
            else:
                paths.append(path)
    return sorted(paths), sorted(omitted_links)


def protected_values(paths: Iterable[Path], root: Path) -> set[bytes]:
    values: set[bytes] = set()
    def add(value: object) -> None:
        if isinstance(value, str) and len(value) >= 8 and not safe_placeholder(value):
            values.add(value.encode("utf-8"))
    def walk(value: object) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                if re.fullmatch(SENSITIVE_KEY, key, re.IGNORECASE):
                    add(item)
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)
    for path in paths:
        relative = path.relative_to(root).as_posix()
        if not (relative.startswith("runtime/secrets/") or "/private-config/" in relative or path.name == "credentials.local.txt"):
            continue
        if path.stat().st_size > TEXT_LIMIT:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if path.suffix == ".json":
            try:
                walk(json.loads(text))
            except (json.JSONDecodeError, ValueError):
                pass
        for pattern in (ASSIGNMENT, PHP_ASSIGNMENT):
            for match in pattern.finditer(text):
                add(match.group(2))
        if path.name == "credentials.local.txt":
            for line in text.splitlines():
                if "password" in line.lower() or "secret" in line.lower():
                    pair = re.split(r"\s*[:=]\s*", line, maxsplit=1)
                    if len(pair) == 2:
                        add(pair[1].strip().strip("\"'"))
    return values


def contains_known_value(path: Path, values: set[bytes]) -> bool:
    if not values:
        return False
    overlap, tail = max(map(len, values)) - 1, b""
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            data = tail + chunk
            if any(value in data for value in values):
                return True
            tail = data[-overlap:] if overlap else b""
    return False


def decode_text(contents: bytes) -> str | None:
    if contents.startswith((b"\xff\xfe", b"\xfe\xff")):
        return contents.decode("utf-16", errors="replace")
    if b"\0" not in contents[:4096]:
        return contents.decode("utf-8-sig", errors="replace")
    return None


def audit(root: Path, *, tracked: bool = False, all_local: bool = False) -> dict:
    if tracked and all_local:
        raise ValueError("Choose tracked files or all local files")
    paths, omitted_links = local_paths(root) if all_local else (git_paths(root, tracked), [])
    values = protected_values(paths, root) if all_local else set()
    # PowerShell exports may encode a copied credential as UTF-16. Search both
    # byte orders as well as UTF-8 while retaining only the value count in output.
    byte_variants = set(values)
    for value in values:
        for encoding in ("utf-16-le", "utf-16-be"):
            byte_variants.add(value.decode("utf-8").encode(encoding))
    findings, errors, counts = [], [], Counter()
    for path in paths:
        relative = path.relative_to(root).as_posix()
        excluded = excluded_by_policy(relative)
        counts["files"] += 1
        counts["excluded_files" if excluded else "candidate_files"] += 1
        try:
            if path.is_symlink() or path.is_junction():
                raise ValueError("symlink_or_junction")
            size = path.stat().st_size
            counts["bytes"] += size
            file_findings = []
            if excluded and tracked:
                file_findings.append({"rule": "tracked_generated_or_sensitive_path", "line": None})
            if not excluded and size > 10 * 1024 * 1024:
                file_findings.append({"rule": "large_committable_file", "line": None})
            if size <= TEXT_LIMIT and (path.suffix.lower() in TEXT_SUFFIXES or path.name.startswith(".env")):
                contents = path.read_bytes()
                text = decode_text(contents)
                if text is not None:
                    lines = text.splitlines()
                    for finding in scan_text(text):
                        if reviewed_synthetic(relative, finding, lines):
                            counts["reviewed_synthetic_findings"] += 1
                        else:
                            file_findings.append(finding)
                    counts["text_files_scanned"] += 1
                else:
                    counts["binary_files_not_pattern_scanned"] += 1
            else:
                counts["nontext_or_large_files_not_pattern_scanned"] += 1
            if contains_known_value(path, byte_variants):
                file_findings.append({"rule": "known_local_secret_bytes", "line": None})
            if values:
                counts["files_checked_for_known_local_secret_bytes"] += 1
            for finding in file_findings:
                findings.append({"path": relative, **finding, "excluded_by_policy": excluded, "blocking": tracked or not excluded})
        except (OSError, ValueError) as exc:
            errors.append({"path": relative, "error_type": type(exc).__name__, "blocking": tracked or not excluded})
    blocking = [item for item in findings + errors if item["blocking"]]
    return {
        "schema_version": 1, "checked_utc": datetime.now(timezone.utc).isoformat(),
        "mode": "all-local" if all_local else "tracked" if tracked else "candidates",
        "counts": dict(counts), "known_local_secret_value_count": len(values),
        "findings": findings, "read_errors": errors, "omitted_links": omitted_links,
        "blocking_finding_count": len(blocking), "passed": not blocking and not omitted_links,
        "limitations": [
            "Literal/token patterns cannot prove absence of arbitrary encoded or novel secrets.",
            "Pattern scan covers recognized UTF-8 or BOM-marked UTF-16 text up to 8 MiB; local known-secret matching streams UTF-8 and UTF-16 variants across all regular-file bytes.",
            "Local credentials are read only in all-local mode and remain in memory; values and matching lines are never reported.",
            "The .git directory and symlink/junction targets are not read; tracked mode audits working-tree content, not historical commits.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--tracked", action="store_true", help="Scan tracked files; forbidden tracked paths fail")
    mode.add_argument("--all-local", action="store_true", help="Inventory all local files and compare protected secret bytes")
    parser.add_argument("--check", action="store_true", help="Return nonzero on blocking findings or omissions")
    parser.add_argument("--report", type=Path, help="Write new redacted JSON; never overwrite")
    args = parser.parse_args()
    try:
        report = audit(ROOT, tracked=args.tracked, all_local=args.all_local)
    except (OSError, subprocess.CalledProcessError, ValueError) as exc:
        print(json.dumps({"passed": False, "error_type": type(exc).__name__}))
        return 2
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        with args.report.open("x", encoding="utf-8") as stream:
            json.dump(report, stream, indent=2)
            stream.write("\n")
    summary = {key: value for key, value in report.items() if key not in {"findings", "read_errors", "limitations"}}
    summary["findings"] = [item for item in report["findings"] if item["blocking"]]
    summary["read_errors"] = report["read_errors"]
    summary["excluded_finding_count"] = sum(not item["blocking"] for item in report["findings"])
    print(json.dumps(summary, indent=2))
    return 1 if args.check and not report["passed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
