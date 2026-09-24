"""Audit authored files/links/secrets and write a new immutable handoff manifest."""

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import unquote
from uuid import uuid4

from dragonhydra.config import PROJECT_ROOT, load_probe_credential, load_settings

root = PROJECT_ROOT
files = [root / name for name in ("AGENTS.md", "README.md", "pyproject.toml", ".gitignore")]
for folder in ("config", "src", "scripts", "tests", "docs", "research"):
    files.extend(path for path in (root / folder).rglob("*") if path.is_file() and "__pycache__" not in path.parts)
files = sorted(files)
secret = load_probe_credential(load_settings())
secret_matches = []
broken_links = []
link_count = 0
for path in files:
    content = path.read_text(encoding="utf-8-sig")
    if secret.password in content:
        secret_matches.append(str(path.relative_to(root)))
    if path.suffix == ".md":
        for raw_link in re.findall(r"\[[^\]]*\]\(([^)]+)\)", content):
            link = unquote(raw_link.strip("<> ").split("#", 1)[0])
            if not link or link.startswith(("https://", "http://", "mailto:")):
                continue
            target = (path.parent / link).resolve()
            link_count += 1
            if not target.is_relative_to(root.parent) or not target.exists():
                broken_links.append({"file": str(path.relative_to(root)), "link": link})
checkpoint_files = list((root / "runtime/checkpoints").rglob("*.json")) + list((root / "runtime/checkpoints").rglob("*.log"))
for path in checkpoint_files:
    if secret.password in path.read_text(encoding="utf-8-sig"):
        secret_matches.append(str(path.relative_to(root)))
required_docs = ["DRAGONHYDRA_GENESIS.md", "PYRAMID_ARCHITECTURE.md", "PYTHON314_POLICY.md",
                 "GPU_COMPUTE_POLICY.md", "MATH_ENGINE_ROOM.md", "DATABASE_ROLES.md", "XAMPP_ROLE.md",
                 "OLD_DRAGON_RECONCILIATION.md", "TECHNOLOGY_COMPATIBILITY_MATRIX.md", "DECISIONS.md", "PROGRESS.md"]
missing_docs = [name for name in required_docs if not (root / "docs" / name).is_file()]
now = datetime.now(timezone.utc)
destination = root / "runtime/checkpoints" / (now.strftime("handoff-%Y%m%dT%H%M%SZ-") + uuid4().hex[:8])
destination.mkdir(exist_ok=False)
manifest = [{"path": str(path.relative_to(root)), "bytes": path.stat().st_size,
             "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "change": "created_during_genesis"} for path in files]
audit = {"checked_utc": now.isoformat(), "authored_file_count": len(files),
         "local_links_checked": link_count, "broken_links": broken_links,
         "required_documents_present": len(required_docs) - len(missing_docs), "missing_documents": missing_docs,
         "checkpoint_files_scanned_for_secret": len(checkpoint_files), "plaintext_secret_matches": secret_matches,
         "passed": not (secret_matches or broken_links or missing_docs)}
for name, data in (("files-manifest.json", manifest), ("audit.json", audit)):
    with (destination / name).open("x", encoding="utf-8") as stream:
        json.dump(data, stream, indent=2)
        stream.write("\n")
print(json.dumps({"checkpoint": str(destination), **audit}, indent=2))
raise SystemExit(0 if audit["passed"] else 1)
