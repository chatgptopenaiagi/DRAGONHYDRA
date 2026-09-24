from dataclasses import asdict, is_dataclass
import hashlib
import json
from pathlib import Path
from uuid import uuid4
from .contracts import PipelineError, utcnow


def digest(content: bytes):
    return hashlib.sha256(content).hexdigest()


def encode(value):
    return json.dumps(asdict(value) if is_dataclass(value) else value,
                      ensure_ascii=False, sort_keys=True, allow_nan=False, indent=2).encode('utf-8')


def exclusive_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as stream:
        stream.write(encode(value))
    return path


def checkpoint(root, stage, value):
    return exclusive_json(root / 'runtime/checkpoints' / ('web-' + stage + '-' + uuid4().hex + '.json'),
                          {'stage': stage, 'recorded_at': utcnow(), 'evidence': value})


def bounded_file(path, parent, max_bytes=2_000_000):
    resolved = path.resolve()
    if not resolved.is_relative_to(parent.resolve()) or not resolved.is_file():
        raise PipelineError('UNSAFE_HANDOFF_PATH')
    with resolved.open('rb') as stream:
        content = stream.read(max_bytes + 1)
    if len(content) > max_bytes:
        raise PipelineError('MAX_BYTES_EXCEEDED')
    return content
