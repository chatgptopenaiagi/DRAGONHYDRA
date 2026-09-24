from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
import ipaddress
import math
import re
from urllib.parse import urlsplit


class Failure(StrEnum):
    NETWORK_ERROR = 'NETWORK_ERROR'
    HTTP_ERROR = 'HTTP_ERROR'
    TERMS_BLOCKED = 'TERMS_BLOCKED'
    ROBOTS_BLOCKED = 'ROBOTS_BLOCKED'
    CAPTCHA_PRESENT = 'CAPTCHA_PRESENT'
    AUTH_REQUIRED = 'AUTH_REQUIRED'
    RATE_LIMITED = 'RATE_LIMITED'
    PARSE_FAILED = 'PARSE_FAILED'
    SCHEMA_CHANGED = 'SCHEMA_CHANGED'
    INVALID_ODDS = 'INVALID_ODDS'
    UNKNOWN_MARKET = 'UNKNOWN_MARKET'
    STALE_DATA = 'STALE_DATA'
    CONFLICTING_DATA = 'CONFLICTING_DATA'


class PipelineError(ValueError):
    """Only controlled reason codes, never server bodies or credential context."""


def utcnow():
    return datetime.now(timezone.utc).isoformat()


def timestamp(value):
    result = datetime.fromisoformat(value)
    if result.utcoffset() is None:
        raise PipelineError('TIMESTAMP_TIMEZONE_REQUIRED')
    return result


def public_url(url):
    if not isinstance(url, str) or len(url) > 2048 or any(ord(c) < 33 for c in url):
        raise PipelineError('INVALID_URL')
    try:
        p = urlsplit(url)
        if (p.scheme != 'https' or not p.hostname or p.username or p.password
                or p.port not in (None, 443) or p.fragment or p.query
                or '%' in p.netloc or '\\' in url):
            raise ValueError()
        host = p.hostname.encode('idna').decode('ascii')
        if host == 'localhost' or host.endswith(('.local', '.localhost')):
            raise ValueError()
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            if '.' not in host or not re.fullmatch(r'[a-zA-Z0-9.-]+', host):
                raise ValueError()
        else:
            if not address.is_global:
                raise ValueError()
    except (ValueError, UnicodeError):
        raise PipelineError('INVALID_URL') from None
    return p


@dataclass(frozen=True)
class FetchPolicy:
    source_id: str
    url: str
    purpose: str
    method: str = 'GET'
    user_agent: str = 'DRAGONHYDRA-Research/1.0 (bounded local research)'
    timeout: int = 20
    rate_limit: float = 2.0
    max_bytes: int = 2_000_000
    content_type_allowlist: tuple[str, ...] = ('application/json', 'text/plain')
    retry_count: int = 0

    def __post_init__(self):
        public_url(self.url)
        if not self.source_id or not self.purpose or self.method != 'GET':
            raise PipelineError('INVALID_FETCH_POLICY')
        if (type(self.timeout) is not int or not 1 <= self.timeout <= 30
                or type(self.max_bytes) is not int or not 1 <= self.max_bytes <= 5_000_000
                or type(self.retry_count) is not int or not 0 <= self.retry_count <= 2
                or not math.isfinite(self.rate_limit) or not 1 <= self.rate_limit <= 60
                or not self.content_type_allowlist or not self.user_agent
                or '\r' in self.user_agent or '\n' in self.user_agent):
            raise PipelineError('INVALID_FETCH_POLICY')


@dataclass(frozen=True)
class HandoffManifest:
    handoff_id: str
    created_at: str
    created_by: str
    source_url: str
    source_title: str
    source_type: str
    capture_method: str
    download_path: str
    content_hash: str
    observed_at: str
    event_time_if_known: str | None
    terms_note: str
    robots_note: str
    license_note: str
    confidence: float
    processing_status: str
    source_id: str
    content_type: str

    def __post_init__(self):
        public_url(self.source_url)
        if not re.fullmatch(r'[a-zA-Z0-9_-]{8,80}', self.handoff_id):
            raise PipelineError('INVALID_HANDOFF_ID')
        if not re.fullmatch('[a-f0-9]{64}', self.content_hash):
            raise PipelineError('INVALID_HASH')
        if not math.isfinite(self.confidence) or not 0 <= self.confidence <= 1:
            raise PipelineError('INVALID_CONFIDENCE')
        if timestamp(self.observed_at) > timestamp(self.created_at):
            raise PipelineError('INVALID_TIMESTAMP_ORDER')
        if timestamp(self.created_at) > datetime.now(timezone.utc):
            raise PipelineError('FUTURE_CAPTURE')
        if self.event_time_if_known is not None:
            timestamp(self.event_time_if_known)
        if self.processing_status != 'PENDING':
            raise PipelineError('HANDOFF_NOT_PENDING')
        for key in ('created_by', 'source_title', 'source_type', 'capture_method',
                    'download_path', 'terms_note', 'robots_note', 'license_note', 'source_id', 'content_type'):
            if not isinstance(getattr(self, key), str) or not getattr(self, key).strip():
                raise PipelineError('MISSING_MANIFEST_FIELD')
