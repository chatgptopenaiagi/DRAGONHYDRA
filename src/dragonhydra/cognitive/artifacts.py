"""Explicit, immutable cognitive artifacts; no private IPC or executable content.

The store is for an owner-controlled project directory. Link checks fail closed
on pre-existing symlinks/junctions, but do not replace the directory's OS ACLs.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import stat
from uuid import UUID

from . import contracts as c


MAX_ARTIFACT_BYTES = 262_144
MAX_JSON_DEPTH = 24
MAX_JSON_NODES = 20_000
_FORBIDDEN_FIELDS = frozenset({
    "chainofthought", "cot", "internalreasoning", "reasoningtrace", "scratchpad",
})
_KINDS = {
    "snapshots": ("SystemStateSnapshot", "StateDelta"),
    "requests": ("CognitiveRequest", "ResearchNeed", "CalculationRequest", "AcquisitionRequest"),
    "responses": ("CognitiveResponse",),
    "actions": ("ActionProposal", "ActionDecision"),
    "receipts": ("ActionResult", "CognitiveCycleReceipt", "ReconciliationReport", "LearningFeedback"),
}


class ArtifactError(ValueError):
    """Sanitized rejection reason; never include input bytes or secret values."""


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ArtifactError("DUPLICATE_JSON_KEY")
        result[key] = value
    return result


def parse_json(raw: bytes) -> dict:
    """Read bounded data only, rejecting duplicate/non-finite/deep JSON."""
    if not isinstance(raw, bytes) or len(raw) > MAX_ARTIFACT_BYTES:
        raise ArtifactError("ARTIFACT_SIZE_LIMIT")
    try:
        payload = json.loads(
            raw.decode("utf-8"), object_pairs_hook=_pairs,
            parse_constant=lambda _: (_ for _ in ()).throw(ArtifactError("NONFINITE_JSON")),
        )
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ArtifactError("INVALID_JSON") from exc
    pending = [(payload, 0)]
    visited = 0
    while pending:
        value, depth = pending.pop()
        visited += 1
        if depth > MAX_JSON_DEPTH or visited > MAX_JSON_NODES:
            raise ArtifactError("JSON_COMPLEXITY_LIMIT")
        if isinstance(value, dict):
            for key, child in value.items():
                normalized = "".join(ch for ch in key.casefold() if ch.isalnum())
                if normalized in _FORBIDDEN_FIELDS:
                    raise ArtifactError("PRIVATE_REASONING_FIELD")
                pending.append((child, depth + 1))
        elif isinstance(value, list):
            pending.extend((child, depth + 1) for child in value)
    if not isinstance(payload, dict):
        raise ArtifactError("OBJECT_REQUIRED")
    return payload


def _reject_link(path: Path) -> None:
    try:
        info = path.lstat()
    except FileNotFoundError:
        return
    if (stat.S_ISLNK(info.st_mode) or
            getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)):
        raise ArtifactError("LINK_PATH_REJECTED")


def _check_ancestors(path: Path) -> None:
    for part in reversed((path, *path.parents)):
        _reject_link(part)


class ArtifactStore:
    """Only closed contract types in five fixed project-local directories.

    IDs are canonical UUIDs, never caller-provided filenames. Publishing is
    exclusive; an interrupted partial write remains invalid, never overwritten.
    """

    def __init__(self, project_root: Path):
        self.project_root = Path(project_root).absolute()
        _check_ancestors(self.project_root)
        if not self.project_root.is_dir():
            raise ArtifactError("PROJECT_ROOT_MISSING")
        self.root = self.project_root / "runtime" / "cognitive"

    def _path(self, kind: str, artifact_id: str, *, create: bool = False) -> Path:
        if kind not in _KINDS:
            raise ArtifactError("UNSUPPORTED_ARTIFACT_KIND")
        try:
            if str(UUID(artifact_id)) != artifact_id:
                raise ValueError
        except (ValueError, TypeError, AttributeError) as exc:
            raise ArtifactError("INVALID_ARTIFACT_ID") from exc
        _check_ancestors(self.project_root)
        current = self.project_root
        for component in ("runtime", "cognitive", kind):
            current = current / component
            _reject_link(current)
            if create:
                current.mkdir(exist_ok=True)
            if not current.is_dir():
                raise ArtifactError("ARTIFACT_DIRECTORY_MISSING")
            _reject_link(current)
        destination = current / (artifact_id + ".json")
        _reject_link(destination)
        return destination

    @staticmethod
    def _contract_type(kind: str, type_name: str):
        if kind not in _KINDS or type_name not in _KINDS[kind]:
            raise ArtifactError("ARTIFACT_TYPE_MISMATCH")
        return getattr(c, type_name)

    def publish(self, kind: str, artifact_id: str, contract) -> Path:
        contract_type = self._contract_type(kind, type(contract).__name__)
        if type(contract) is not contract_type:
            raise ArtifactError("ARTIFACT_TYPE_MISMATCH")
        # Revalidation blocks mutated nested values and bypassed constructors.
        validated = contract_type.from_dict(parse_json(contract.to_json().encode("utf-8")))
        envelope = {
            "artifact_type": type(validated).__name__,
            "payload": validated.to_dict(),
            "payload_hash": validated.digest(),
        }
        raw = json.dumps(envelope, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
        parse_json(raw)
        destination = self._path(kind, artifact_id, create=True)
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0)
        try:
            descriptor = os.open(destination, flags, 0o600)
        except FileExistsError as exc:
            raise ArtifactError("IMMUTABLE_ARTIFACT_EXISTS") from exc
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        return destination

    def read(self, kind: str, artifact_id: str, contract_type=None):
        destination = self._path(kind, artifact_id)
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
        with os.fdopen(os.open(destination, flags), "rb") as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise ArtifactError("REGULAR_SINGLE_LINK_FILE_REQUIRED")
            if info.st_size > MAX_ARTIFACT_BYTES:
                raise ArtifactError("ARTIFACT_SIZE_LIMIT")
            envelope = parse_json(stream.read(MAX_ARTIFACT_BYTES + 1))
        if set(envelope) != {"artifact_type", "payload", "payload_hash"}:
            raise ArtifactError("UNKNOWN_ENVELOPE_FIELD")
        actual_type = self._contract_type(kind, envelope["artifact_type"])
        if contract_type is not None and actual_type is not contract_type:
            raise ArtifactError("ARTIFACT_TYPE_MISMATCH")
        result = actual_type.from_dict(envelope["payload"])
        if envelope["payload_hash"] != result.digest():
            raise ArtifactError("ARTIFACT_HASH_MISMATCH")
        return result
