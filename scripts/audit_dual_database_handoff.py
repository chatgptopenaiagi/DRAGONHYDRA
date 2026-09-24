"""Write a new, secret-free dual-database handoff audit and authored-file manifest."""

from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys
from urllib.parse import unquote
from uuid import uuid4

from dragonhydra.config import PROJECT_ROOT, load_probe_credential, load_settings
from dragonhydra.storage.sqlserver_config import load_sqlserver_credential, load_sqlserver_settings


def read_text(path: Path) -> str:
    data = path.read_bytes()
    return data.decode("utf-16" if data.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8-sig")


def main() -> int:
    root = PROJECT_ROOT
    if sys.version_info[:2] != (3, 14):
        raise SystemExit("The handoff audit requires Python 3.14")
    baseline = root / "runtime/checkpoints/handoff-20260924T160435Z-ecc08e23/files-manifest.json"
    previous = {row["path"]: row["sha256"] for row in json.loads(read_text(baseline))}
    files = [root / name for name in ("AGENTS.md", "README.md", "pyproject.toml", ".gitignore")]
    for folder in ("config", "src", "scripts", "tests", "docs", "research"):
        files.extend(path for path in (root / folder).rglob("*")
                     if path.is_file() and "__pycache__" not in path.parts)
    files = sorted(files)
    # Secrets are used only for exact-match detection; neither values nor context are emitted.
    passwords = (load_probe_credential(load_settings()).password,
                 load_sqlserver_credential(load_sqlserver_settings()).password)
    secret_matches: set[str] = set()
    broken_links = []
    link_count = 0
    manifest = []
    for path in files:
        relative = str(path.relative_to(root))
        content = read_text(path)
        if any(password in content for password in passwords):
            secret_matches.add(relative)
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        change = ("created" if relative not in previous else
                  "unchanged" if previous[relative] == digest else "modified")
        manifest.append({"path": relative, "bytes": path.stat().st_size,
                         "sha256": digest, "change": change})
        if path.suffix != ".md":
            continue
        for raw_link in re.findall(r"\[[^\]]*\]\(([^)]+)\)", content):
            link = unquote(raw_link.strip("<> ").split("#", 1)[0])
            if not link or link.startswith(("https://", "http://", "mailto:")):
                continue
            target = (path.parent / link).resolve()
            link_count += 1
            if not target.is_relative_to(root.parent) or not target.exists():
                broken_links.append({"file": relative, "link": link})
    suffixes = {".json", ".log", ".md", ".toml", ".ps1", ".py", ".reg", ".txt", ".csv"}
    checkpoint_files = sorted(path for path in (root / "runtime/checkpoints").rglob("*")
                              if path.is_file() and path.suffix.lower() in suffixes)
    for path in checkpoint_files:
        if any(password in read_text(path) for password in passwords):
            secret_matches.add(str(path.relative_to(root)))
    required_docs = ("DUAL_DATABASE_ARCHITECTURE.md", "MARIADB_XAMPP_ROLE.md",
                     "SQLSERVER2022_ROLE.md", "DATABASE_PORT_POLICY.md",
                     "PYTHON314_DATABASE_DRIVERS.md", "DATABASE_SECURITY_BOUNDARIES.md",
                     "PROGRESS.md", "DECISIONS.md")
    missing_docs = [name for name in required_docs if not (root / "docs" / name).is_file()]
    removed = sorted(set(previous) - {row["path"] for row in manifest})
    now = datetime.now(timezone.utc)
    destination = root / "runtime/checkpoints" / (now.strftime("dual-handoff-%Y%m%dT%H%M%SZ-") + uuid4().hex[:8])
    audit = {"checked_utc": now.isoformat(), "python_version": sys.version.split()[0],
             "baseline_manifest": str(baseline.relative_to(root)),
             "authored_file_count": len(files), "changes": dict(Counter(row["change"] for row in manifest)),
             "removed_authored_files": removed, "local_links_checked": link_count,
             "broken_links": broken_links, "required_documents_present": len(required_docs) - len(missing_docs),
             "missing_documents": missing_docs, "configuration_parsers_passed": True,
             "checkpoint_text_files_scanned": len(checkpoint_files), "credential_values_checked": len(passwords),
             "plaintext_secret_matches": sorted(secret_matches),
             "passed": not (secret_matches or broken_links or missing_docs or removed)}
    destination.mkdir(exist_ok=False)
    for name, data in (("files-manifest.json", manifest), ("audit.json", audit)):
        with (destination / name).open("x", encoding="utf-8") as stream:
            json.dump(data, stream, indent=2)
            stream.write("\n")
    print(json.dumps({"checkpoint": str(destination), **audit}, indent=2))
    return 0 if audit["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
