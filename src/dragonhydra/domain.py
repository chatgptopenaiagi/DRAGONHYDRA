"""Shared pure domain identity and clock, independent of application composition."""
from datetime import datetime, timezone
import hashlib
import json

API = '/dragon/api/v1'


def now():
    return datetime.now(timezone.utc).isoformat(timespec='microseconds').replace('+00:00', 'Z')


def identity(*parts):
    return hashlib.sha256(json.dumps(['v1', *parts], ensure_ascii=False).encode()).hexdigest()
