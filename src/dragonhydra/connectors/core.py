"""Bounded provider HTTP transport. Exact response bytes precede transformation."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from http.client import IncompleteRead
import hashlib
import json
import os
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler
from uuid import uuid4


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec='microseconds').replace('+00:00', 'Z')


class ConnectorError(Exception):
    def __init__(self, code, message, retry_after=None, http_status=None):
        super().__init__(message)
        self.code, self.message = code, message
        self.retry_after, self.http_status = retry_after, http_status


def redact_url(url):
    parsed = urlsplit(url)
    sensitive = {'apikey', 'api_key', 'api-token', 'api_token', 'token', 'key', 'access_token'}
    query = [(k, '[REDACTED]' if k.lower() in sensitive else v) for k, v in parse_qsl(parsed.query, keep_blank_values=True)]
    return urlunsplit((parsed.scheme, parsed.hostname or '', parsed.path, urlencode(query), ''))


@dataclass
class Document:
    url: str
    resolved_url: str
    body: bytes
    captured_at: str
    sha256: str
    content_type: str = ''
    acquisition_id: str = ''
    raw_reference: str = ''
    http_status: int = 200

    def json(self):
        try:
            return json.loads(self.body.decode('utf-8-sig'))
        except (ValueError, UnicodeError):
            raise ConnectorError('INVALID_JSON', 'The provider returned invalid JSON; exact bytes were retained.') from None

    def text(self):
        try:
            return self.body.decode('utf-8-sig')
        except UnicodeError:
            return self.body.decode('cp1252')


ALLOWED_HOSTS = frozenset({'www.football-data.co.uk', 'football-data.co.uk', 'raw.githubusercontent.com',
    'github.com', 'release-assets.githubusercontent.com', 'objects.githubusercontent.com',
    'moneypuck.com', 'www.moneypuck.com', 'cricsheet.org', 'www.cricsheet.org',
    'api.football-data.org', 'v3.football.api-sports.io', 'api.the-odds-api.com', 'api.sportmonks.com'})


def validate_url(url):
    parsed = urlsplit(url)
    if parsed.scheme != 'https' or parsed.hostname not in ALLOWED_HOSTS or parsed.username or parsed.password or parsed.port not in (None, 443):
        raise ConnectorError('ENDPOINT_NOT_ALLOWED', 'Only the registered HTTPS provider endpoints are allowed.')


class SafeRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        validate_url(newurl)
        sensitive = any(k.lower() in ('authorization', 'x-auth-token', 'x-apisports-key') for k in req.headers)
        if (sensitive or any(k.lower() in ('apikey', 'api_token', 'token') for k, _ in parse_qsl(urlsplit(req.full_url).query))) and urlsplit(newurl).hostname != urlsplit(req.full_url).hostname:
            raise ConnectorError('AUTH_REDIRECT_REJECTED', 'The authenticated endpoint redirected to another host.')
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class RejectRedirect(HTTPRedirectHandler):
    """Leave redirects as responses so a bounded operation makes no extra GET."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class Transport:
    def __init__(self, raw_dir: Path, receipt_sink=None, check=lambda: None, *, max_bytes=32*1024*1024, timeout=25,
                 follow_redirects=True):
        self.raw_dir = Path(raw_dir)
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.receipt_sink, self.check = receipt_sink, check
        self.max_bytes, self.timeout = max_bytes, timeout
        self.follow_redirects = follow_redirects
        self.documents = []
        self.opener = build_opener(SafeRedirect() if follow_redirects else RejectRedirect())

    def get(self, url, headers=None):
        self.check()
        validate_url(url)
        request = Request(url, headers={'User-Agent': 'DRAGONHYDRA/0.4 public-dataset-adapter', **(headers or {})})
        try:
            response = self.opener.open(request, timeout=self.timeout)
        except HTTPError as exc:
            response = exc
        except (URLError, TimeoutError, OSError):
            raise ConnectorError('NETWORK_UNAVAILABLE', 'The provider could not be reached. Cached records remain available.', retry_after=60) from None
        with response:
            status = response.getcode()
            content_type = response.headers.get_content_type()
            raw = bytearray()
            while True:
                self.check()
                try:
                    part = response.read(min(256*1024, self.max_bytes+1-len(raw)))
                except (URLError, TimeoutError, OSError, IncompleteRead):
                    raise ConnectorError('NETWORK_UNAVAILABLE', 'The provider transfer was interrupted. No partial dataset was imported; cached records remain available.', retry_after=60) from None
                if not part:
                    break
                raw.extend(part)
                if len(raw) > self.max_bytes:
                    raise ConnectorError('DOWNLOAD_LIMIT', f'The response exceeded the configured {self.max_bytes} byte download limit.')
            # HTTPResponse.read(size) may reach EOF without IncompleteRead when
            # the peer closes early. An apparently valid CSV/JSON prefix must
            # not be published as a complete provider acquisition. Chunked
            # framing takes precedence over a stale Content-Length header.
            expected = response.headers.get('Content-Length', '').strip()
            if not response.headers.get('Transfer-Encoding') and expected.isdigit() and len(raw) != int(expected):
                raise ConnectorError('NETWORK_UNAVAILABLE', 'The provider transfer ended before its declared length. No partial dataset was imported; cached records remain available.', retry_after=60)
            body = bytes(raw)
            digest = hashlib.sha256(body).hexdigest()
            path = self.raw_dir / (digest+'.payload')
            temporary = self.raw_dir / (digest+'.'+uuid4().hex+'.tmp')
            try:
                if not path.exists():
                    with temporary.open('xb') as output:
                        output.write(body)
                        output.flush()
                        os.fsync(output.fileno())
                    try:
                        # Publish a completed sibling without overwriting any
                        # committed content-addressed destination, even on races.
                        os.link(temporary, path)
                    except FileExistsError:
                        pass
                if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
                    raise ConnectorError('RAW_INTEGRITY_FAILURE', 'A retained payload failed its integrity check.')
            except OSError:
                raise ConnectorError('RAW_RETENTION_FAILED', 'The response could not be committed to raw evidence storage. No normalized rows were imported.') from None
            finally:
                temporary.unlink(missing_ok=True)
            doc = Document(redact_url(url), redact_url(response.geturl()), body, utc_now(), digest,
                           content_type, uuid4().hex, path.name, status)
            self.documents.append(doc)
            if self.receipt_sink:
                self.receipt_sink(doc)
            if not self.follow_redirects and 300 <= status < 400:
                raise ConnectorError('REDIRECT_REJECTED', 'This bounded acquisition does not follow HTTP redirects; the received response was retained.', http_status=status)
            if status == 429:
                value = response.headers.get('Retry-After', '60')
                delay = max(1, min(86400, int(value))) if value.isdigit() else 60
                raise ConnectorError('RATE_LIMITED', 'Provider quota exhausted; retry after the reported cooldown.', delay, status)
            if status in (401, 403):
                raise ConnectorError('AUTH_REJECTED', 'The endpoint rejected authentication or account access.', http_status=status)
            if status in (500, 502, 503, 504):
                value = response.headers.get('Retry-After', '60')
                delay = max(1, min(86400, int(value))) if value.isdigit() else 60
                raise ConnectorError('NETWORK_UNAVAILABLE', f'The provider returned temporary HTTP {status}. Cached records remain available.', retry_after=delay, http_status=status)
            if status >= 400:
                raise ConnectorError('HTTP_ERROR', f'The provider returned HTTP {status}. Retained records remain available.', http_status=status)
            if content_type in ('text/html', 'application/xhtml+xml') or body.lstrip().lower().startswith((b'<!doctype html', b'<html')):
                raise ConnectorError('UNEXPECTED_HTML', 'An HTML response is not a sports dataset; response bytes were retained.')
            return doc
