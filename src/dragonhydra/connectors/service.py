"""Provider configuration, persisted diagnostics and centrally budgeted sync."""
from contextlib import closing
import json
import sqlite3
import time

from . import adapter, registry
from .core import ConnectorError, Transport, utc_now
from .store import Store
from .vault import Vault


class Connections:
    def __init__(self, product):
        self.product, self.store, self.vault = product, Store(product), Vault(product.state)

    def spec(self, provider):
        specs = registry()
        if provider not in specs:
            raise LookupError('CONNECTION_NOT_FOUND')
        return specs[provider]

    def configure(self, provider, config, interval_seconds, credential=None, remove_credential=False):
        spec, module = self.spec(provider), adapter(provider)
        merged = {**spec.get('defaults', {}), **config}
        if hasattr(module, 'validate_config'):
            merged = module.validate_config(provider, config)
            # Omitted date windows remain rolling at execution time; saving a
            # key or schedule must not freeze an implicit "today" forever.
            for field in ('date_from', 'date_to'):
                if field not in config:
                    merged.pop(field, None)
        elif set(config)-set(spec.get('defaults', {})):
            raise ValueError('UNKNOWN_CONNECTION_SETTING')
        minimum = max(60, spec.get('min_interval_seconds', 3600))
        if interval_seconds and not minimum <= interval_seconds <= 7*86400:
            raise ValueError('SYNC_INTERVAL_OUT_OF_RANGE')
        if credential:
            self.vault.put(provider, credential)
        if remove_credential:
            self.vault.delete(provider)
        with closing(self.product.connect()) as db:
            db.execute('INSERT INTO connector_settings(provider,config,interval_seconds,next_due) VALUES(?,?,?,?) ON CONFLICT(provider) DO UPDATE SET config=excluded.config,interval_seconds=excluded.interval_seconds,next_due=excluded.next_due',
                       (provider, json.dumps(merged), interval_seconds, time.time()+interval_seconds if interval_seconds else 0))
            db.commit()
        return {'provider': provider, 'config': merged, 'interval_seconds': interval_seconds,
                'minimum_interval_seconds': minimum, 'credential_configured': self.vault.configured(provider)}

    def run(self, provider, operation, check=lambda: None, job_id=None):
        spec = self.spec(provider)
        attempt = self.store.start(provider, operation, job_id)
        transport = Transport(self.product.state/'raw'/'connectors',
                              lambda doc: self.store.receipt(provider, doc), check)
        cooldown_until = 0
        try:
            for previous in self.store.attempts(provider, limit=20):
                cooldown_until = max(cooldown_until, (previous.get('error') or {}).get('cooldown_until', 0))
            if cooldown_until > time.time():
                raise ConnectorError('RATE_LIMITED', 'Provider quota cooldown is still active; no new HTTP request was sent.',
                                     retry_after=max(1, int(cooldown_until-time.time())+1))
            settings = self.store.settings(provider)
            secret = self.vault.get(provider)
            records = adapter(provider).fetch(provider, {**spec.get('defaults', {}), **settings['config']}, secret, transport, check)
            check()
            if not records:
                raise ConnectorError('NO_RECORDS', 'The endpoint answered but returned no records for the selected coverage.')
            # Each operation validates exact bytes once per supplied document.
            # Sync's transactional ingestion performs the same common validation
            # and also records quarantine; it must not run a second preflight.
            validation = (self.store.ingest(provider, records, transport.documents) if operation == 'sync'
                          else self.store.validate_batch(provider, records, transport.documents))
            result = {'provider': provider, 'operation': operation, 'status': 'payload_retrieved',
                      'endpoint_reachable': bool(transport.documents), 'authentication': 'accepted' if secret else 'public',
                      'retrieved': True, 'retrieved_rows': len(records), 'normalized_rows': validation['normalized_rows'],
                      'invalid_rows': validation['invalid_rows'], 'normalization_errors': validation['normalization_errors'],
                      'capabilities': spec['capabilities'], 'live': spec.get('live', False),
                      'captured_at': max(d.captured_at for d in transport.documents),
                      'acquisitions': [{'id': d.acquisition_id, 'sha256': d.sha256, 'url': d.url,
                                        'resolved_url': d.resolved_url, 'bytes': len(d.body)} for d in transport.documents],
                      'display_verified': False}
            if operation == 'sync':
                result.update(validation)
                result['status'] = 'imported'
            else:
                result['record_count'] = self.store.count(provider)
            if not validation['normalized_rows']:
                raise ConnectorError('NORMALIZATION_FAILED', 'Retrieved records did not pass the normalized entity contract; inspect retained evidence and quarantine.')
            self.store.finish(attempt, result=result)
            return result
        except Exception as exc:
            if isinstance(exc, ConnectorError):
                error = {'code': exc.code, 'message': exc.message, 'http_status': exc.http_status,
                         'retry_after': exc.retry_after, 'endpoint_reachable': bool(transport.documents)}
                if exc.code == 'RATE_LIMITED':
                    error['cooldown_until'] = cooldown_until if cooldown_until > time.time() else time.time()+(exc.retry_after or 60)
            else:
                error = {'code': 'ADAPTER_FAILED', 'message': type(exc).__name__+' while processing the provider. Cached data remains available.',
                         'endpoint_reachable': bool(transport.documents)}
            self.store.finish(attempt, error=error)
            raise

    def describe(self, provider):
        spec = self.spec(provider)
        count = self.store.count(provider)
        # Latest successful retrieval and latest successful import are separate.
        with closing(self.product.connect()) as db:
            db.row_factory = sqlite3.Row
            rows = db.execute("SELECT * FROM connector_attempts WHERE provider=? AND operation IN ('test','sync') ORDER BY started_at DESC LIMIT 10", (provider,)).fetchall()
            history = [{**dict(row), 'result':json.loads(row['result']) if row['result'] else None,
                        'error':json.loads(row['error']) if row['error'] else None} for row in rows]
            latest = history[0] if history else None
            success = db.execute("SELECT finished_at,result FROM connector_attempts WHERE provider=? AND operation IN ('test','sync') AND status='succeeded' ORDER BY started_at DESC LIMIT 1", (provider,)).fetchone()
            imported = db.execute("SELECT finished_at,result FROM connector_attempts WHERE provider=? AND operation='sync' AND status='succeeded' ORDER BY started_at DESC LIMIT 1", (provider,)).fetchone()
            quarantined = db.execute('SELECT COUNT(*) FROM connector_quarantine WHERE provider=?', (provider,)).fetchone()[0]
            pending = db.execute("SELECT COUNT(*) FROM connector_identity_review WHERE (provider=? OR other_provider=?) AND status='review_required'", (provider, provider)).fetchone()[0]
        requires_key = spec.get('requires_key', provider in ('api-football', 'the-odds-api', 'sportmonks', 'football-data-org'))
        has_key = self.vault.configured(provider)
        if latest and latest['status'] == 'running':
            status, reason = 'checking', 'A diagnostic or synchronization job is running.'
        elif latest and latest['status'] == 'failed':
            error = latest['error'] or {}
            status = 'needs_key' if error.get('code') == 'NEEDS_KEY' else 'failing'
            reason = error.get('message', 'Retrieval failed; cached records remain available.')
        elif success:
            status, reason = 'working', 'Real retrieval and normalization succeeded. '+('Stored records are available.' if count else 'Run Sync now to store this dataset.')
        elif requires_key and not has_key:
            status, reason = 'needs_key', 'Save the provider API key, then test endpoint access and coverage.'
        else:
            status, reason = 'not_tested', 'Adapter implemented; no successful retrieval has been recorded yet.'
        settings = self.store.settings(provider)
        return {'id': provider, 'implemented': True, 'status': status, 'reason': reason,
                'record_count': count, 'last_import': imported[0] if imported else None,
                'last_successful_retrieval': success[0] if success else None,
                'last_retrieval_count': json.loads(success[1])['retrieved_rows'] if success else 0,
                'capabilities': spec['capabilities'], 'live': spec.get('live', False),
                'credential_configured': has_key, 'requires_key': requires_key,
                'config': {**spec.get('defaults', {}), **settings['config']},
                'interval_seconds': settings['interval_seconds'],
                'minimum_interval_seconds': max(60, spec.get('min_interval_seconds', 3600)),
                'last_diagnostic': latest, 'quarantined_count': quarantined, 'identity_review_count': pending,
                'provenance_url': '/dragon/api/v1/connections/'+provider+'/records'}

    def schedule_due(self, jobs):
        tick = time.time()
        with closing(self.product.connect()) as db:
            due = db.execute('SELECT provider,interval_seconds,next_due FROM connector_settings WHERE interval_seconds>0 AND next_due<=?', (tick,)).fetchall()
        for provider, interval, next_due in due:
            if provider not in registry():
                continue
            with closing(self.product.connect()) as db:
                active = db.execute("SELECT 1 FROM product_jobs WHERE kind='connector_sync' AND status IN ('queued','running','interrupted') AND json_extract(payload,'$.provider')=?", (provider,)).fetchone()
            if not active:
                jobs.submit('connector_sync', {'provider': provider}, 'system:scheduler', 'scheduled:'+provider+':'+str(int(next_due)))
            with closing(self.product.connect()) as db:
                db.execute('UPDATE connector_settings SET next_due=? WHERE provider=?', (tick+interval, provider))
                db.commit()
