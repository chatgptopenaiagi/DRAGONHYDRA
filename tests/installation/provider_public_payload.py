"""Real public-data journey and restart against an existing frozen server payload.

This test owns only its fresh work directory and Popen children. No Windows
services, existing databases, source server or product binaries are modified.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import time
import traceback
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
import zipfile


ROOT = Path(__file__).resolve().parents[2]
EXPECTED_SOURCE = '826b80effc453d9906b9870f83e196e86ce93a4a35f94f28a4481c88e9a0413e'
EXPECTED_BINARY = '5ab672b44e2ee50c7eb6c3786dd82d3e34ae370d2cf46165dce35b10984cd033'
PROVIDERS = ('football-data-couk', 'statsbomb', 'nflverse')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--payload-work', type=Path, default=ROOT/'build/connections/payload-20261031-a1')
    parser.add_argument('--work', type=Path, required=True)
    args = parser.parse_args()
    work, payload_work = args.work.resolve(), args.payload_work.resolve()
    if not work.is_relative_to(ROOT/'build/connections') or work == ROOT/'build/connections':
        raise SystemExit('Use a fresh owned child of build/connections.')
    if work.exists():
        raise SystemExit('Existing verification evidence is preserved; select a fresh work directory.')
    if sys.flags.optimize:
        raise SystemExit('Assertions must be enabled for this verification.')
    work.mkdir(parents=True)
    state = work/'state'
    payload = payload_work/'dist/DRAGONHYDRA-Server-x64'
    binary = payload/'DRAGONHYDRA-Server.exe'
    record = {'schema_version': 1, 'started_at': datetime.now(timezone.utc).isoformat(),
              'passed': False, 'checks': [], 'commands': [], 'lifecycle': [],
              'scope': 'Frozen private-runtime server, three real public providers, same-match API/XLSX and owned restart; no native UI, installer or clean-machine claim.'}
    server = log = None
    origin = token = None
    report_path = work/'verification.json'

    def save():
        report_path.write_text(json.dumps(record, indent=2, ensure_ascii=False)+'\n', encoding='utf-8')

    def passed(description, **details):
        record['checks'].append({'description': description, **details})
        print('PASS:', description, json.dumps(details, ensure_ascii=False), flush=True)
        save()

    server_env = os.environ.copy()
    for name in tuple(server_env):
        if name in ('PYTHONPATH', 'PYTHONHOME', 'VIRTUAL_ENV', 'CONDA_PREFIX') or name.startswith('DRAGONHYDRA_'):
            server_env.pop(name, None)
    windows = server_env.get('SystemRoot', r'C:\Windows')
    server_env['PATH'] = windows+r'\System32'+os.pathsep+windows

    def request(method, path, body=None, raw=False):
        data = None if body is None else json.dumps(body).encode('utf-8')
        req = Request(origin+'/dragon/api/v1'+path, data=data, method=method,
                      headers={'Authorization': 'Bearer '+token, 'Content-Type': 'application/json'})
        with urlopen(req, timeout=30) as response:
            content = response.read()
            return response.status, content if raw else json.loads(content)

    def start(label):
        nonlocal server, log, origin, token
        argv = [str(binary), '--port', '0', '--state', str(state)]
        log = (work/(label+'.log')).open('w', encoding='utf-8')
        server = subprocess.Popen(argv, cwd=work, env=server_env, stdout=log,
                                  stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW)
        entry = {'operation': 'start', 'label': label, 'argv': argv, 'pid': server.pid,
                 'started_at': datetime.now(timezone.utc).isoformat()}
        record['lifecycle'].append(entry)
        deadline = time.monotonic()+30
        while time.monotonic()<deadline:
            if server.poll() is not None:
                raise RuntimeError('Owned frozen server exited before readiness; inspect '+label+'.log')
            try:
                endpoint = json.loads((state/'endpoint.json').read_text())
                # An old endpoint after restart cannot become readiness proof.
                if endpoint['pid'] != server.pid:
                    time.sleep(.1)
                    continue
                origin = endpoint['url']
                token = json.loads((state/'local-session.json').read_text())['token']
                if request('GET', '/health/ready')[0] == 200:
                    entry.update(url=origin, ready=True)
                    save()
                    return
            except (OSError, ValueError, URLError):
                pass
            time.sleep(.1)
        raise TimeoutError('Owned frozen server readiness exceeded 30 seconds')

    def stop(label):
        nonlocal server, log
        if server is None:
            return
        entry = {'operation': 'stop', 'label': label, 'pid': server.pid}
        if server.poll() is None:
            entry['http_status'] = request('POST', '/system/shutdown', {})[0]
            assert entry['http_status'] == 200
            server.wait(timeout=20)
        entry['exit_code'] = server.returncode
        assert server.returncode == 0, 'Owned server did not exit cleanly'
        record['lifecycle'].append(entry)
        log.close()
        log = None
        server = None
        save()

    def wait_job(created, timeout=60):
        deadline = time.monotonic()+timeout
        while time.monotonic()<deadline:
            code, job = request('GET', '/jobs/'+created['id'])
            assert code == 200
            if job['status'] in ('succeeded', 'failed', 'cancelled', 'interrupted'):
                if job['status'] != 'succeeded':
                    raise AssertionError('Owned job failed: '+json.dumps(job.get('error')))
                return job
            time.sleep(.15)
        raise TimeoutError('Owned job exceeded bounded deadline')

    try:
        build = json.loads((payload_work/'BUILD-REPORT.json').read_text())
        inventory = json.loads((payload_work/'PAYLOAD-MANIFEST.json').read_text())['files']
        assert build['status'] == 'verified_current_host'
        assert build['source_content_sha256'] == EXPECTED_SOURCE
        assert sha(binary) == EXPECTED_BINARY == build['binary_sha256']
        expected_paths = set()
        for item in inventory:
            candidate = (payload/item['path']).resolve()
            assert candidate.is_relative_to(payload.resolve())
            assert candidate.is_file() and candidate.stat().st_size == item['bytes']
            assert sha(candidate) == item['sha256'], item['path']
            expected_paths.add(item['path'])
        actual_paths = {p.relative_to(payload).as_posix() for p in payload.rglob('*') if p.is_file()}
        assert actual_paths == expected_paths
        metadata = json.loads(subprocess.check_output([str(binary), '--build-info'], cwd=work, env=server_env, text=True))
        assert metadata['source_content_sha256'] == EXPECTED_SOURCE and metadata['source_sha'] is None
        record['build_info'] = metadata
        record['binary_sha256'] = sha(binary)
        passed('Every frozen payload file independently matches its manifest', files=len(inventory), source_content_sha256=EXPECTED_SOURCE, binary_sha256=EXPECTED_BINARY)

        start('server-initial')
        code, health = request('GET', '/health/ready')
        assert code == 200 and health['status'] == 'ready'
        passed('Private server starts with developer runtime paths removed', http_status=code, health=health, origin=origin)

        argv = [sys.executable, '-B', str(ROOT/'scripts/verify_connections.py'), '--state', str(state),
                '--url', origin, '--output', str(work/'imports'), '--sources', *PROVIDERS]
        began = time.monotonic()
        with (work/'sync-command.log').open('w', encoding='utf-8') as output:
            result = subprocess.run(argv, cwd=ROOT, stdout=output, stderr=subprocess.STDOUT, timeout=540)
        record['commands'].append({'argv': argv, 'exit_code': result.returncode,
                                   'seconds': round(time.monotonic()-began, 3), 'log': 'sync-command.log'})
        assert result.returncode == 0, 'Real public sync failed; inspect sync-command.log'
        imports = json.loads((work/'imports/summary.json').read_text())
        counts = {r['provider']: r['job']['result']['record_count'] for r in imports['results'] if r['job']['status']=='succeeded'}
        assert set(counts)==set(PROVIDERS) and all(v>0 for v in counts.values())
        record['import_counts'] = counts
        passed('Three real public HTTP sources normalize and persist through frozen API jobs', record_counts=counts)

        _, catalog = request('GET', '/connections')
        cards = {item['id']: item for item in catalog['items']}
        for provider, count in counts.items():
            assert cards[provider]['status']=='working' and cards[provider]['record_count']==count
            assert cards[provider]['last_successful_retrieval'] and cards[provider]['last_import']
        passed('Connection statuses expose real stored counts and successful timestamps')

        _, page = request('GET', '/matches?provider=football-data-couk&limit=1')
        match = page['items'][0]
        match_id = match['id']
        assert page['total']==counts['football-data-couk'] and match['source_id']=='football-data-couk'
        _, detail = request('GET', '/matches/'+match_id)
        assert detail['home']==match['home'] and detail['evidence_id']==match['evidence_id']
        _, team = request('GET', '/teams/'+match['home']['id'])
        assert any(item['id']==match_id for item in team['matches']) and team['form']
        _, standings = request('GET', '/competitions/'+match['competition_id']+'/standings')
        assert len(standings['items'])==20 and not standings['official']
        passed('One canonical football event connects match, related team and reconstructed league standings', canonical_match_id=match_id, participants=[match['home']['name'],match['away']['name']], teams_in_table=len(standings['items']))

        _, statistics = request('GET', '/matches/'+match_id+'/statistics')
        _, odds = request('GET', '/matches/'+match_id+'/odds')
        _, history = request('GET', '/matches/'+match_id+'/odds-history')
        assert statistics['items'] and odds['items'] and history['axis']=='archive_phase'
        assert all(item['match_id']==match_id and item['quote_at'] is None for item in odds['items'])
        passed('Source statistics and compatible archival odds belong to the same match', statistics=len(statistics['items']), quotes=len(odds['items']), history_axis=history['axis'], source_quote_times_supplied=False)

        _, evidence = request('GET', '/evidence/'+match['evidence_id'])
        assert evidence['provider']=='football-data-couk'
        assert evidence['source_record_id'] and evidence['adapter_version']=='football-data-couk/1'
        raw_path = state/'raw/connectors'/evidence['raw_reference']
        assert raw_path.is_file() and sha(raw_path)==evidence['raw_sha256']
        with sqlite3.connect(state/'core.sqlite3') as db:
            acquisitions = db.execute('SELECT provider,sha256,raw_reference,bytes FROM connector_acquisitions').fetchall()
            observations_before = db.execute('SELECT COUNT(*) FROM connector_observations').fetchone()[0]
        for provider, digest, reference, size in acquisitions:
            raw = state/'raw/connectors'/reference
            assert raw.stat().st_size==size and sha(raw)==digest
        passed('All acquisition hashes resolve to retained exact bytes and selected evidence is queryable', acquisitions=len(acquisitions), selected_evidence_id=match['evidence_id'], selected_native_id=evidence['source_record_id'], selected_raw_sha256=evidence['raw_sha256'])

        code, created = request('POST', '/matches/'+match_id+'/explanations', {})
        assert code==202
        explanation = wait_job(created)['result']
        assert explanation['kind']=='deterministic' and match['evidence_id'] in explanation['input_manifest']
        code, created = request('POST', '/exports', {'match_id':match_id,'format':'xlsx'})
        assert code==202
        exported = wait_job(created)['result']
        code, data = request('GET', '/exports/'+created['id']+'/download', raw=True)
        workbook = work/'football-match.xlsx'
        workbook.write_bytes(data)
        assert code==200 and sha(workbook)==exported['sha256']
        with zipfile.ZipFile(workbook) as archive:
            assert '[Content_Types].xml' in archive.namelist()
            assert match_id.encode() in archive.read('xl/worksheets/sheet1.xml')
            assert b'name="Odds"' in archive.read('xl/workbook.xml')
        passed('Deterministic cited explanation and actual Excel workbook succeed', explanation_kind=explanation['kind'], workbook_bytes=len(data), workbook_sha256=sha(workbook))

        samples = {}
        for provider in PROVIDERS:
            _, source = request('GET', '/connections/'+provider+'/records?limit=1')
            samples[provider] = {'total':source['total'], 'id':source['items'][0]['id'], 'native_id':source['items'][0]['source_record_id']}
        pairing_hash = sha(state/'local-session.json')
        stop('controlled-restart')
        start('server-restarted')
        for provider in PROVIDERS:
            _, source = request('GET', '/connections/'+provider+'/records?limit=1')
            assert samples[provider]=={'total':source['total'], 'id':source['items'][0]['id'], 'native_id':source['items'][0]['source_record_id']}
        assert sha(state/'local-session.json')==pairing_hash
        with sqlite3.connect(state/'core.sqlite3') as db:
            observations_after = db.execute('SELECT COUNT(*) FROM connector_observations').fetchone()[0]
        assert observations_before==observations_after
        record['persistence'] = {'before_counts':counts,'after_counts':counts,'observations_before':observations_before,
                                 'observations_after':observations_after,'evidence_samples':samples,'pairing_retained':True}
        passed('Restart retains all source counts, selected evidence identities, pairing and observation count', observations_before=observations_before, observations_after=observations_after)
        stop('verification-finished')
        passed('Both test-owned private server processes exited cleanly', exit_codes=[entry['exit_code'] for entry in record['lifecycle'] if entry['operation']=='stop'])
        record['passed']=True
    except Exception as exc:
        record['error']=type(exc).__name__+': '+str(exc)
        record['traceback']=traceback.format_exc()
        raise
    finally:
        if server is not None and server.poll() is None:
            try:
                stop('failure-cleanup')
            except Exception as cleanup:
                record['cleanup_error']=type(cleanup).__name__
                # This Popen handle belongs only to the test; never use a name
                # search, service operation or unrelated process identifier.
                server.terminate()
                try:
                    server.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    server.kill()
                    server.wait(timeout=5)
        if log is not None:
            log.close()
        record['finished_at']=datetime.now(timezone.utc).isoformat()
        record['unique_group_count']=len(record['checks'])
        save()
        print(json.dumps({key:record.get(key) for key in ('passed','import_counts','unique_group_count','error')},indent=2),flush=True)


if __name__=='__main__':
    main()
