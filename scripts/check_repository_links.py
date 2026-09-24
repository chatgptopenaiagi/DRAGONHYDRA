"""Validate Markdown file targets against Git's actual staged blobs, not disk."""

import argparse
import json
import posixpath
from pathlib import Path
import re
import subprocess
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parents[1]


def markdown_targets(text):
    # Keep line offsets while excluding examples that are not rendered links.
    text = re.sub(r"(?ms)^(```|~~~).*?^\1[^\n]*(?:\n|$)",
                  lambda match: "\n" * match.group().count("\n"), text)
    text = re.sub(r"`[^`\n]*`", lambda match: " " * len(match.group()), text)
    definitions = {}
    for match in re.finditer(r"(?m)^\s{0,3}\[([^\]]+)\]:\s*(<[^>]+>|\S+)", text):
        definitions[match[1].casefold()] = match[2].strip("<>")
        yield text.count("\n", 0, match.start()) + 1, match[2].strip("<>")
    for match in re.finditer(r"!?\[[^\]\n]*\]\(\s*(<[^>]+>|[^\s()]+)(?:\s+['\"][^\n]*?['\"])?\s*\)", text):
        yield text.count("\n", 0, match.start()) + 1, match[1].strip("<>")
    for match in re.finditer(r"!?\[([^\]\n]+)\](?:\[([^\]\n]*)\])?", text):
        key = (match[2] or match[1]).casefold()
        if key in definitions and text[match.end():match.end()+1] not in ("(", ":"):
            yield text.count("\n", 0, match.start()) + 1, definitions[key]


def check_links(blobs):
    """blobs maps committed-intent POSIX paths to exact index bytes."""
    paths = set(blobs)
    checked = 0
    issues = []
    for name in sorted(paths):
        if not name.lower().endswith(".md"):
            continue
        text = blobs[name].decode("utf-8-sig")
        for line, raw in markdown_targets(text):
            parts = urlsplit(raw)
            if parts.scheme in ("http", "https", "mailto") or parts.netloc:
                continue
            if parts.scheme:
                issues.append({"file": name, "line": line, "target": raw, "reason": "unsupported_or_local_machine_scheme"})
                continue
            if not parts.path:
                continue
            target = unquote(parts.path).replace("\\", "/")
            target = posixpath.normpath(posixpath.join(posixpath.dirname(name), target))
            checked += 1
            reason = None
            if target.startswith(("/", "../")):
                reason = "outside_repository"
            elif target.startswith("runtime/"):
                reason = "local_forensic_evidence_must_not_be_a_repository_link"
            elif target not in paths and not any(p.startswith(target.rstrip("/") + "/") for p in paths):
                reason = "target_absent_from_staged_files"
            if reason:
                issues.append({"file": name, "line": line, "target": raw, "reason": reason})
    return {"markdown_files": sum(p.lower().endswith(".md") for p in paths),
            "links_checked": checked, "broken_links": issues, "passed": not issues}


def staged_blobs():
    listing = subprocess.check_output(["git", "ls-files", "--stage", "-z"], cwd=ROOT)
    blobs = {}
    for record in listing.split(b"\0"):
        if not record:
            continue
        metadata, raw_name = record.split(b"\t", 1)
        mode, oid, stage = metadata.decode("ascii").split()
        if stage != "0" or mode not in ("100644", "100755"):
            raise ValueError("Unmerged, symlink or submodule content needs explicit review")
        name = raw_name.decode("utf-8")
        # Only Markdown contents are needed; all staged names establish target membership.
        blobs[name] = subprocess.check_output(["git", "cat-file", "blob", oid], cwd=ROOT) if name.lower().endswith(".md") else b""
    if not blobs:
        raise ValueError("No staged files; stage reviewed content before the repository link audit")
    return blobs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="new local JSON evidence under runtime/checkpoints")
    args = parser.parse_args()
    result = check_links(staged_blobs())
    if args.output:
        destination = args.output.resolve()
        if not destination.is_relative_to(ROOT / "runtime/checkpoints"):
            parser.error("Output must stay under runtime/checkpoints")
        with destination.open("x", encoding="utf-8") as stream:
            json.dump(result, stream, indent=2)
            stream.write("\n")
    print(json.dumps(result, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
