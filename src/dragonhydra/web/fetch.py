"""HTTPS only, pinned public DNS address, no redirects, cookies, proxies or auth."""
from dataclasses import replace
import http.client
import ipaddress
import socket
import ssl
import time
from .contracts import PipelineError, public_url, utcnow
from .provenance import digest
from .rate_limit import LIMITER
from .robots import evaluate_robots
from .terms import allow_source


def _request(policy, allow_404=False):
    p = public_url(policy.url)
    LIMITER.wait(p.hostname, policy.rate_limit)
    conn = None
    try:
        addresses = socket.getaddrinfo(p.hostname, 443, type=socket.SOCK_STREAM)
        if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
            raise PipelineError('NON_PUBLIC_DNS')
        # Connect to the vetted IP while validating TLS against the original hostname.
        conn = http.client.HTTPSConnection(p.hostname, timeout=policy.timeout)
        raw = socket.create_connection((addresses[0][4][0], 443), timeout=policy.timeout)
        conn.sock = ssl.create_default_context().wrap_socket(raw, server_hostname=p.hostname)
        deadline = time.monotonic() + policy.timeout
        conn.request('GET', p.path or '/', headers={'User-Agent': policy.user_agent, 'Accept-Encoding': 'identity'})
        response = conn.getresponse()
        status = response.status
        if status == 404 and allow_404:
            return b'', 'text/plain', status
        if status in (401, 403):
            raise PipelineError('AUTH_REQUIRED')
        if status == 429:
            raise PipelineError('RATE_LIMITED')
        if status != 200:
            raise PipelineError('HTTP_ERROR')
        content_type = response.getheader('Content-Type', '').split(';')[0].strip().lower()
        if content_type not in policy.content_type_allowlist:
            raise PipelineError('CONTENT_TYPE_UNEXPECTED')
        if response.getheader('Content-Encoding', 'identity') != 'identity':
            raise PipelineError('CONTENT_ENCODING_UNSUPPORTED')
        size = response.getheader('Content-Length')
        if size is not None and int(size) > policy.max_bytes:
            raise PipelineError('MAX_BYTES_EXCEEDED')
        parts, length = [], 0
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise PipelineError('NETWORK_ERROR')
            if conn.sock:
                conn.sock.settimeout(remaining)
            block = response.read1(min(65536, policy.max_bytes + 1 - length))
            if not block:
                break
            parts.append(block)
            length += len(block)
            if length > policy.max_bytes:
                raise PipelineError('MAX_BYTES_EXCEEDED')
        body = b''.join(parts)
        if b'captcha' in body.lower() or b'cf-chl-' in body.lower():
            raise PipelineError('CAPTCHA_PRESENT')
        return body, content_type, status
    except PipelineError:
        raise
    except (OSError, http.client.HTTPException, ValueError):
        raise PipelineError('NETWORK_ERROR') from None
    finally:
        if conn:
            conn.close()


def fetch(policy, source):
    allow_source(source, policy.url)
    p = public_url(policy.url)
    robots_policy = replace(policy, url=f'https://{p.netloc}/robots.txt',
                            max_bytes=100_000, content_type_allowlist=('text/plain',), retry_count=0)
    raw, _, status = _request(robots_policy, allow_404=True)
    robots = evaluate_robots(raw.decode('utf-8'), policy.url, policy.user_agent, status)
    robots['content_hash'] = digest(raw)
    if robots['robots_status'] not in ('ALLOWED', 'ABSENT'):
        raise PipelineError('ROBOTS_BLOCKED')
    delay = robots['crawl_delay_if_any'] or policy.rate_limit
    if delay > 60:
        raise PipelineError('ROBOTS_BLOCKED')
    # retry_count is an upper bound; intentionally no automatic retries of failures.
    body, content_type, _ = _request(replace(policy, rate_limit=max(delay, policy.rate_limit)))
    return body, {'retrieved_at': utcnow(), 'content_hash': digest(body), 'robots': robots,
                  'content_type': content_type, 'source_url': policy.url, 'source_id': policy.source_id}
