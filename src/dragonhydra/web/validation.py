from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from .contracts import PipelineError, timestamp
from .terms import allow_source
from .odds import validate_temporal


@dataclass(frozen=True)
class Verdict:
    decision: str
    reasons: tuple[str, ...]


def validate_observation(record, source, *, duplicate=False, conflict=False, now=None):
    if source is None:
        return Verdict('REJECT', ('SOURCE_UNKNOWN',))
    try:
        allow_source(source, record['source_url'])
        if record['robots_status'] not in ('ALLOWED', 'ABSENT'):
            raise PipelineError('ROBOTS_BLOCKED')
        if record['content_type'] not in source['content_types']:
            raise PipelineError('CONTENT_TYPE_UNEXPECTED')
        validate_temporal(record['observed_at'], record['available_at'], record['updated_at'], record.get('target_as_of_at'))
        if not record.get('entity_id'):
            return Verdict('QUARANTINE', ('ENTITY_UNRESOLVED',))
        if conflict:
            return Verdict('QUARANTINE', ('CONFLICTING_DATA',))
        if duplicate:
            return Verdict('REJECT', ('DUPLICATE',))
        age = (now or datetime.now(timezone.utc)) - timestamp(record['observed_at'])
        if age > timedelta(seconds=source.get('stale_after_seconds', 86400)):
            return Verdict('ACCEPT_WITH_WARNING', ('STALE_DATA',))
        return Verdict('ACCEPT', ('SOURCE_POLICY_AND_PROVENANCE_VALID',))
    except (PipelineError, KeyError, TypeError, ValueError) as error:
        reason = str(error) if isinstance(error, PipelineError) else 'SCHEMA_CHANGED'
        return Verdict('REJECT', (reason,))
