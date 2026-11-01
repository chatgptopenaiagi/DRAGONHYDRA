"""Exercise the frozen control-center/workflow API in a fresh owned state.

No installed Windows service, Joomla database or provider credential is touched.
Bundled data is imported only by an explicit authenticated retained-import job.
"""
from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import time
from urllib.error import HTTPError
from urllib.request import ProxyHandler, Request, build_opener


API = '/dragon/api/v1'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binary', type=Path, required=True)
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--source-content-sha256', required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    work = args.work.resolve()
    if not work.is_relative_to(root/'build/connections') or work == root/'build/connections' or work.exists():
        raise SystemExit('Select a fresh owned child beneath build/connections; existing evidence is preserved.')
    binary = args.binary.resolve()
    metadata = json.loads((binary.parent/'BUILD-INFO.json').read_text(encoding='utf-8'))
    manifest = json.loads((binary.parent/'SOURCE-MANIFEST.json').read_text(encoding='utf-8'))
    serialized = json.dumps(manifest['files'], sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()
    assert hashlib.sha256(serialized).hexdigest() == args.source_content_sha256
    assert metadata['source_content_sha256'] == manifest['content_sha256'] == args.source_content_sha256
    included = {entry['path'] for entry in manifest['files']}
    assert {'src/dragonhydra/system_workflow.py', 'src/dragonhydra/module_registry.py',
            'src/dragonhydra/api.py', 'src/dragonhydra/jobs.py'} <= included
    work.mkdir(parents=True)
    state = work/'state'
    state.mkdir()
    receipt = {'schema_version': 1, 'created_at': datetime.now(timezone.utc).isoformat(),
        'scope': 'Fresh isolated frozen Windows server, explicit retained data, forecast/pending evaluation and same-state restart; no Joomla/UI or installed-service claim',
        'binary': str(binary), 'binary_sha256': sha(binary), 'source_content_sha256': args.source_content_sha256,
        'checks': [], 'passed': False}
    env = os.environ.copy()
    for key in ('PYTHONPATH', 'PYTHONHOME', 'VIRTUAL_ENV', 'CONDA_PREFIX'):
        env.pop(key, None)
    windows = os.environ.get('SystemRoot', r'C:\Windows')
    env['PATH'] = str(Path(windows)/'System32') + os.pathsep + windows
    opener = build_opener(ProxyHandler({}))
    process = None
    log = None
    base = token = None

    def check(name, **evidence):
        receipt['checks'].append({'id': name, 'status': 'PASS',
            'timestamp': datetime.now(timezone.utc).isoformat(), **evidence})

    def call(method, path, body=None, *, auth=True, key=None):
        headers = {'Content-Type': 'application/json'}
        if auth:
            headers['Authorization'] = 'Bearer ' + token
        if key:
            headers['Idempotency-Key'] = key
        data = None if body is None else json.dumps(body).encode()
        try:
            with opener.open(Request(base+API+path, data=data, headers=headers, method=method), timeout=15) as response:
                return response.status, json.loads(response.read())
        except HTTPError as error:
            return error.code, json.loads(error.read())

    def start(label):
        nonlocal process, log, base, token
        log = (work/(label+'.log')).open('w', encoding='utf-8')
        process = subprocess.Popen([str(binary), '--host', '127.0.0.1', '--port', '0', '--state', str(state)],
            cwd=state, env=env, stdout=log, stderr=subprocess.STDOUT,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        deadline = time.monotonic()+30
        base = token = None
        while time.monotonic() < deadline:
            assert process.poll() is None, 'Owned frozen process exited during startup'
            try:
                endpoint = json.loads((state/'endpoint.json').read_text())
                base = endpoint['url']
                assert endpoint['pid'] == process.pid
                token = json.loads((state/'local-session.json').read_text())['token']
                if call('GET', '/health/ready')[0] == 200:
                    return
            except (OSError, ValueError):
                pass
            time.sleep(.15)
        raise AssertionError('Owned frozen startup deadline exceeded')

    def stop():
        assert call('POST', '/system/shutdown', {})[0] == 200
        process.wait(timeout=15)
        assert process.returncode == 0
        log.close()

    def job(identifier):
        deadline = time.monotonic()+60
        while time.monotonic() < deadline:
            status, result = call('GET', '/jobs/'+identifier)
            assert status == 200
            if result['status'] == 'succeeded':
                return result
            assert result['status'] not in ('failed', 'cancelled'), result.get('error')
            time.sleep(.15)
        raise AssertionError('Owned workflow job deadline exceeded')

    def tables():
        with sqlite3.connect((state/'core.sqlite3').as_uri()+'?mode=ro', uri=True) as db:
            return {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}

    try:
        start('first-start')
        assert call('GET', '/system')[1]['build']['source_content_sha256'] == args.source_content_sha256
        check('fresh-private-frozen-startup', pid=process.pid)
        assert call('GET', '/system/modules', auth=False)[0] == 401
        before = tables()
        status, registry = call('GET', '/system/modules')
        assert status == 200 and registry['registry_version'] == 'module-registry/1'
        assert registry['read_only'] is True and registry['network_probes'] is False
        assert registry['summary']['total_modules'] == len(registry['modules']) == 18
        assert before == tables() and 'cognitive_records' not in before
        check('authenticated-passive-registry-before-memory', modules=len(registry['modules']))
        status, imported = call('POST', '/connections/openfootball/sync', {}, key='control-retained-import')
        assert status == 202
        imported_result = job(imported['id'])
        retained = call('GET', '/matches?limit=1')[1]['total']
        assert retained == imported_result['result']['record_count'] == 760
        check('explicit-retained-import', records=retained, job_id=imported['id'])
        candidates = []
        offset = 0
        while True:
            _, page = call('GET', '/matches?status=scheduled&limit=200&offset='+str(offset))
            candidates.extend(page['items'])
            offset += len(page['items'])
            if offset >= page['total']:
                break
        earliest = str(date.today()+timedelta(days=2))
        target = next(row for row in sorted(candidates, key=lambda row:(row['event_date'], row['id']))
                      if row['event_date'] >= earliest and row['source_id'] == 'openfootball-2026-27-en1.json')
        match_id = target['id']
        path = '/matches/'+match_id
        status, initial_history = call('GET', path+'/cognition-history')
        assert status == 200 and initial_history['counts']['predictions'] == 0
        assert 'cognitive_records' not in tables()
        assert initial_history['present_knowledge_holdout']['reason'] == 'EXPLICIT_DIAGNOSTIC_NOT_REQUESTED'
        check('history-does-not-initialize-or-run-model', match_id=match_id)
        status, submitted = call('POST', path+'/forecasts', {}, key='control-selected-forecast')
        assert status == 202
        forecast = job(submitted['id'])['result']
        assert forecast['run_id'] == submitted['id'] and forecast['status'] == 'persisted'
        assert len(forecast['model_runs']) == len(forecast['predictions']) == 5
        assert all(row['target_evidence_id'] == target['evidence_id'] for row in forecast['predictions'])
        prediction_ids = sorted(row['record_id'] for row in forecast['predictions'])
        _, duplicate = call('POST', path+'/forecasts', {}, key='control-selected-forecast')
        assert duplicate['id'] == submitted['id']
        history = call('GET', path+'/cognition-history')[1]
        assert sorted(row['record_id'] for row in history['records']['predictions']) == prediction_ids
        check('selected-real-fixture-durable-forecast', match_id=match_id,
              source_id=target['source_id'], event_date=target['event_date'], home=target['home']['name'],
              away=target['away']['name'], model_count=5, prediction_count=5,
              training_count=len(forecast['model_runs'][0]['input_evidence_ids']), prediction_record_ids=prediction_ids)
        status, evaluation_job = call('POST', path+'/evaluations', {}, key='control-pending-evaluation')
        assert status == 202
        pending = job(evaluation_job['id'])['result']
        assert pending['status'] == 'pending' and pending['reason'] == 'LATER_RETAINED_OUTCOME_UNAVAILABLE'
        assert not pending['persisted_evaluations']
        assert pending['history']['counts']['outcomes'] == pending['history']['counts']['evaluations'] == 0
        check('no-later-outcome-is-honestly-pending', reason=pending['reason'])
        with sqlite3.connect((state/'core.sqlite3').as_uri()+'?mode=ro', uri=True) as db:
            assert db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        old_token = token
        stop()
        check('first-graceful-shutdown', exit_code=process.returncode)
        start('same-state-restart')
        assert token == old_token
        assert call('GET', '/matches?limit=1')[1]['total'] == retained
        after = call('GET', path+'/cognition-history')[1]
        assert sorted(row['record_id'] for row in after['records']['predictions']) == prediction_ids
        assert after['counts'] == history['counts']
        assert call('GET', '/system/modules')[1]['installation_id'] == registry['installation_id']
        _, again = call('POST', path+'/forecasts', {}, key='control-selected-forecast')
        assert again['id'] == submitted['id']
        check('restart-preserves-pairing-retained-records-memory-and-job-idempotency', records=retained,
              counts=after['counts'], pairing_preserved=True)
        stop()
        check('second-graceful-shutdown', exit_code=process.returncode)
        receipt['passed'] = True
    except Exception as error:
        receipt['error'] = type(error).__name__+': '+str(error)
        raise
    finally:
        if process and process.poll() is None:
            try:
                stop()
            except Exception:
                process.terminate()
                process.wait(timeout=10)
        if log and not log.closed:
            log.close()
        receipt['finished_at'] = datetime.now(timezone.utc).isoformat()
        (work/'system-control-frozen.json').write_text(json.dumps(receipt, indent=2)+'\n', encoding='utf-8')
        print(json.dumps(receipt, indent=2))


if __name__ == '__main__':
    main()
