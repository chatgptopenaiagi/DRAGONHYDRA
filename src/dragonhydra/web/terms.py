import json
from .contracts import PipelineError, public_url, timestamp
from datetime import datetime, timezone, timedelta


def load_sources(root):
    return json.loads((root / 'config/web_sources.json').read_text(encoding='utf-8'))


def allow_source(source, url):
    p = public_url(url)
    if source['terms_status'] != 'ALLOWED_RESEARCH' or source['license_status'] not in ('RESEARCH_ONLY','CC0-1.0'):
        raise PipelineError('TERMS_BLOCKED')
    if source.get('terms_verification') != 'VERIFIED' or source.get('license_verification') != 'VERIFIED':
        raise PipelineError('TERMS_UNVERIFIED')
    if datetime.now(timezone.utc) - timestamp(source['reviewed_at']) > timedelta(days=30):
        raise PipelineError('TERMS_REVIEW_EXPIRED')
    if p.hostname != source['host'] or url not in source['allowed_urls']:
        raise PipelineError('SOURCE_URL_NOT_ALLOWED')
