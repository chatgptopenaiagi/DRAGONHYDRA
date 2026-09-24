"""One-league prospective evidence clock; bounded one-shot CLI, no daemon.

The local ledger owns acquisition receipts, not normalized SQL intelligence.
Actual capture timestamps can never be backfilled by this collector.
"""
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import re
from uuid import uuid4

from ..config import PROJECT_ROOT
from ..web.contracts import FetchPolicy, PipelineError, public_url, timestamp, utcnow
from ..web.fetch import fetch
from ..web.provenance import digest, encode, exclusive_json
from ..web.terms import allow_source, load_sources


class RawEvidenceStore:
    """Content-addressed bytes, verified on reuse; never overwrite an artifact."""

    def __init__(self, directory: Path):
        self.directory = Path(directory)

    def put(self, body: bytes) -> str:
        if not isinstance(body, bytes) or not body or len(body) > 2_000_000:
            raise ValueError('RAW_SIZE_INVALID')
        key = digest(body)
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self.directory / key
        try:
            with path.open('xb') as stream:
                stream.write(body)
        except FileExistsError:
            if self.get(key) != body:
                raise ValueError('RAW_HASH_MISMATCH') from None
        return key

    def get(self, key: str) -> bytes:
        if not re.fullmatch('[a-f0-9]{64}', key):
            raise ValueError('RAW_HASH_INVALID')
        path = self.directory / key
        if path.stat().st_size > 2_000_000:
            raise ValueError('RAW_SIZE_INVALID')
        body = path.read_bytes()
        if digest(body) != key:
            raise ValueError('RAW_HASH_MISMATCH')
        return body


@dataclass(frozen=True)
class ProspectiveSnapshot:
    snapshot_id: str
    source_id: str
    source_url: str
    retrieved_at: str
    observed_at: str
    available_at: str
    content_hash: str
    raw_artifact_hash: str
    byte_count: int
    media_type: str
    parser_version: str
    source_policy_version: str
    source_policy_hash: str
    competition: str
    season: str
    fixture_count: int
    temporal_mode: str = 'STRICT_PIT'

    def __post_init__(self):
        public_url(self.source_url)
        for value in (self.content_hash, self.raw_artifact_hash, self.source_policy_hash):
            if not re.fullmatch('[a-f0-9]{64}', value):
                raise ValueError('SNAPSHOT_HASH_INVALID')
        if self.content_hash != self.raw_artifact_hash:
            raise ValueError('SNAPSHOT_HASH_MISMATCH')
        if not (timestamp(self.observed_at) <= timestamp(self.retrieved_at)
                <= timestamp(self.available_at) <= datetime.now(timezone.utc)):
            raise ValueError('SNAPSHOT_TIME_INVALID')
        if (self.temporal_mode != 'STRICT_PIT' or type(self.fixture_count) is not int
                or not 1 <= self.fixture_count <= 500):
            raise ValueError('SNAPSHOT_CONTRACT_INVALID')
        if type(self.byte_count) is not int or not 1 <= self.byte_count <= 2_000_000:
            raise ValueError('SNAPSHOT_SIZE_INVALID')
        if not re.fullmatch('[a-f0-9]{32}', self.snapshot_id):
            raise ValueError('SNAPSHOT_ID_INVALID')
        if any(not isinstance(value, str) or not value.strip()
               for value in (self.source_id, self.media_type, self.parser_version,
                             self.source_policy_version, self.competition, self.season)):
            raise ValueError('SNAPSHOT_METADATA_REQUIRED')


def validate_fixture_document(body: bytes, competition: str) -> int:
    """Validate acquisition shape only. Do not resolve identity or infer kickoff UTC."""
    try:
        data = json.loads(body)
        matches = data['matches']
        if data['name'] != competition or not isinstance(matches, list) or not 1 <= len(matches) <= 500:
            raise ValueError()
        for row in matches:
            if any(not isinstance(row[key], str) or not row[key].strip()
                   for key in ('round', 'date', 'team1', 'team2')):
                raise ValueError()
            datetime.strptime(row['date'], '%Y-%m-%d')
            if row['team1'] == row['team2']:
                raise ValueError()
    except (ValueError, TypeError, KeyError, UnicodeError):
        raise PipelineError('SCHEMA_CHANGED') from None
    return len(matches)


def collect_once(root: Path = PROJECT_ROOT, *, retry_failed: bool = False) -> dict:
    """One daily attempt, plus at most one explicit failed-attempt recovery.

    Call periodically from an owner-managed scheduler. No credentials or services
    are created. Source policy is rechecked before every acquisition.
    """
    root = Path(root)
    ledger = root / 'runtime/prospective/openfootball-en.1'
    ledger.mkdir(parents=True, exist_ok=True)
    lock = ledger / '.collector.lock'
    try:
        handle = lock.open('x', encoding='utf-8')
    except FileExistsError:
        return {'status': 'COLLECTOR_LOCKED', 'reason': 'inspect unfinished local attempt before removing lock'}
    try:
        with handle:
            handle.write(utcnow())
        now = datetime.now(timezone.utc)
        attempts = [json.loads(p.read_text(encoding='utf-8')) for p in sorted(ledger.glob('*.json'))]
        recent = sorted((a for a in attempts if timestamp(a['attempted_at']) > now - timedelta(days=1)),
                        key=lambda a: a['attempted_at'])
        manual_retry = (retry_failed and len(recent) == 1 and recent[-1]['status'] == 'SOURCE_UNAVAILABLE')
        if recent and not manual_retry:
            return {'status': 'NOT_DUE', 'attempts': len(attempts)}
        entry = {'attempt_id': uuid4().hex, 'attempted_at': now.isoformat(),
                 'source_id': 'openfootball', 'data_class': 'fixture', 'status': 'SOURCE_UNAVAILABLE'}
        try:
            source = load_sources(root)['openfootball']
            current = source.get('prospective')
            if not current:
                raise PipelineError('SOURCE_UNAVAILABLE')
            if current['competition'] != 'Premier League' or current['interval_hours'] != 24:
                raise PipelineError('PROSPECTIVE_SCOPE_INVALID')
            allow_source(source, current['url'])
            policy = FetchPolicy('openfootball', current['url'], 'one-league daily prospective fixture receipt')
            body, evidence = fetch(policy, source)
            if digest(body) != evidence['content_hash']:
                raise PipelineError('CONTENT_HASH_MISMATCH')
            raw_hash = RawEvidenceStore(root / 'runtime/raw').put(body)
            entry['raw_artifact_hash'] = raw_hash
            entry['acquisition'] = evidence
            count = validate_fixture_document(body, current['document_name'])
            snapshot = ProspectiveSnapshot(uuid4().hex, 'openfootball', current['url'],
                evidence['retrieved_at'], evidence['retrieved_at'], utcnow(), raw_hash, raw_hash,
                len(body), evidence['content_type'], 'openfootball-snapshot/1.0',
                source['policy_version'], digest(encode(source)), current['competition'], current['season'], count)
            # Preserve the exact reviewed policy locally so its hash can be replayed.
            policy_path = ledger / 'policies' / (snapshot.source_policy_hash + '.json')
            if not policy_path.exists():
                exclusive_json(policy_path, source)
            if digest(encode(json.loads(policy_path.read_text(encoding='utf-8')))) != snapshot.source_policy_hash:
                raise PipelineError('SOURCE_POLICY_HASH_MISMATCH')
            entry.update(status='CAPTURED', snapshot=asdict(snapshot), robots=evidence['robots'])
        except (PipelineError, KeyError, ValueError, OSError) as error:
            # Controlled code/type only; never persist server response or credentials.
            entry.update(status='SOURCE_UNAVAILABLE', reason=str(error) if isinstance(error, PipelineError)
                         else type(error).__name__)
        exclusive_json(ledger / (entry['attempt_id'] + '.json'), entry)
        return entry
    finally:
        lock.unlink()


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--retry-failed', action='store_true',
                        help='explicit single recovery attempt after one failure; maximum two attempts/day')
    args = parser.parse_args()
    result = collect_once(retry_failed=args.retry_failed)
    print(json.dumps(result, indent=2))
    return 0 if result['status'] in ('CAPTURED', 'NOT_DUE') else 1


if __name__ == '__main__':
    raise SystemExit(main())
