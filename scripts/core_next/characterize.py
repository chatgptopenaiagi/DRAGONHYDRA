"""Offline baseline/candidate API characterization using separately imported source trees.

Run each lane in a fresh subprocess. All runtime/golden artifacts stay in the
explicit lab; the shared snapshot is read only and never contains copied tokens.
"""
from __future__ import annotations
import argparse
from contextlib import ExitStack
import csv
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import random
import shutil
import socket
import sqlite3
import sys
from unittest.mock import patch

FIXED_NOW = '2026-11-01T12:00:00.000000Z'
VOLATILE_JOB_FIELDS = {'created_at','updated_at','heartbeat','lease_until','deadline','next_attempt'}


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def write_new(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False)
        stream.write('\n')


def inside(path, lab):
    path = Path(path).resolve()
    if path == lab or not path.is_relative_to(lab):
        raise ValueError('Characterization artifacts must remain inside the explicit lab')
    return path


def run_lane(args):
    lab = args.lab.resolve()
    source = args.source.resolve()
    expected_source = lab/'baseline-source' if args.lane == 'baseline' else Path(__file__).resolve().parents[2]
    if source != expected_source.resolve() or not (source/'src/dragonhydra/api.py').is_file():
        raise ValueError('Use only the owned baseline export or CORE NEXT clone')
    snapshot = inside(args.snapshot, lab)
    state = inside(args.state, lab)
    output = inside(args.output, lab)
    if state.exists() or output.exists():
        raise ValueError('A fresh state directory and immutable output path are required')
    snapshot_hash = sha(snapshot)
    source_files = {p.relative_to(source).as_posix():sha(p) for p in sorted((source/'src/dragonhydra').rglob('*.py'))}
    state.mkdir(parents=True)
    shutil.copyfile(snapshot, state/'core.sqlite3')
    assert sha(state/'core.sqlite3') == snapshot_hash
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(source/'src'))
    from fastapi.testclient import TestClient
    import dragonhydra.api as api
    import dragonhydra.product as product_module
    import dragonhydra.jobs as jobs_module
    assert Path(api.__file__).resolve().is_relative_to(source)
    random.seed(1729)
    network_attempts = []

    def forbidden(*_args, **_kwargs):
        network_attempts.append('Network attempt rejected by characterization boundary')
        raise RuntimeError('CHARACTERIZATION_NETWORK_FORBIDDEN')

    socket_connect = socket.socket.connect
    def offline_connect(sock, address):
        # Windows asyncio constructs its private wakeup socketpair through a
        # numeric loopback connection. Block external endpoints, not that pipe.
        if isinstance(address, tuple) and address[0] in ('127.0.0.1','::1'):
            return socket_connect(sock,address)
        return forbidden()

    fixture_token = 'core-next-offline-characterization-token-not-a-user-credential'
    kwargs = dict(local_token=fixture_token, bridge_secret='core-next-synthetic-characterization-bridge',
                  start_worker=False, source_root=source)
    if args.lane == 'candidate':
        from dragonhydra.kernel.contracts import KernelConfig
        kwargs['kernel_config'] = KernelConfig(installation_id='core-next-characterization', environment_id='candidate',
            version='0.5.0-dev.1', source_commit=args.source_commit, build_id='core-next-characterization')
    semantic, raw_checks, job_names, artifacts = {}, [], {}, []
    jobs_completed = []

    def normalize(value):
        if isinstance(value, dict):
            return {key: normalize(item) for key,item in value.items()}
        if isinstance(value, list):
            return [normalize(item) for item in value]
        if isinstance(value, str):
            for ident, name in job_names.items():
                value = value.replace(ident, '<job:'+name+'>')
            return value
        return value

    def job_semantic(job):
        value = {key:item for key,item in job.items() if key not in VOLATILE_JOB_FIELDS}
        if value['kind'] == 'export' and isinstance(value.get('result'), dict):
            value['result'] = dict(value['result'])
            # Each actual artifact hash is independently checked, while XLSX ZIP
            # timestamps are not treated as domain behavior.
            value['result'].pop('sha256', None)
            value['result'].pop('bytes', None)
        return normalize(value)

    def get(client, path, name, expected=200):
        response = client.get(api.API+path)
        if response.status_code != expected:
            raise AssertionError(f'{name}: expected HTTP {expected}, got {response.status_code}')
        value = response.json()
        semantic[name] = normalize(value)
        return value

    def post_job(client, app, path, body, name):
        headers = {'Idempotency-Key':'characterize-'+name}
        response = client.post(api.API+path, json=body, headers=headers)
        assert response.status_code == 202, (name, response.status_code)
        queued = response.json()
        job_names[queued['id']] = name
        replay = client.post(api.API+path, json=body, headers=headers)
        assert replay.status_code == 202 and replay.json()['id'] == queued['id']
        assert queued['status'] == 'queued'
        semantic[name+'_queued'] = job_semantic(queued)
        assert app.state.jobs.run_once()
        completed = app.state.jobs.get(queued['id'])
        assert completed['status'] == 'succeeded', (name, completed.get('error'))
        jobs_completed.append(completed)
        semantic[name+'_completed'] = job_semantic(completed)
        return completed

    with ExitStack() as patches:
        for module in (api, product_module, jobs_module):
            patches.enter_context(patch.object(module, 'now', lambda:FIXED_NOW))
        patches.enter_context(patch('socket.create_connection', forbidden))
        patches.enter_context(patch('socket.socket.connect', offline_connect))
        patches.enter_context(patch('urllib.request.urlopen', forbidden))
        patches.enter_context(patch.object(jobs_module, 'urlopen', forbidden))
        patches.enter_context(patch.object(jobs_module, 'fetch_public', forbidden))
        app = api.create_app(state, **kwargs)
        with TestClient(app) as client:
            client.headers['Authorization'] = 'Bearer '+fixture_token
            initial_rows = app.state.product.rows()
            initial_domain_hash = hashlib.sha256(json.dumps(initial_rows,sort_keys=True).encode()).hexdigest()
            with sqlite3.connect(state/'core.sqlite3') as db:
                initial_jobs = db.execute('SELECT COUNT(*) FROM product_jobs').fetchone()[0]
            assert initial_jobs == 0, 'Sanitized snapshot unexpectedly contains operational jobs'
            unauthorized = client.get(api.API+'/matches', headers={'Authorization':''})
            assert unauthorized.status_code == 401
            semantic['unauthorized_matches'] = unauthorized.json()
            get(client, '/matches?limit=0', 'invalid_page', 422)
            health = get(client, '/health/ready', 'health')
            semantic['health'] = {k:v for k,v in health.items() if k not in {'version','source_sha'}}
            all_matches = []
            offset = 0
            while True:
                response = client.get(api.API+f'/matches?limit=200&offset={offset}')
                assert response.status_code == 200
                page = response.json()
                all_matches.extend(page['items'])
                if len(all_matches) >= page['total']:
                    break
                assert page['items'], 'Inconsistent pagination'
                offset += len(page['items'])
            assert len(all_matches) == page['total'] and len({r['id'] for r in all_matches}) == len(all_matches)
            assert all_matches, 'Snapshot must contain real retained records'
            semantic['all_match_ids'] = sorted(r['id'] for r in all_matches)
            semantic['counts'] = {'matches':len(all_matches), 'sources':sorted({r['source_id'] for r in all_matches})}
            get(client, '/matches?limit=5&offset=0', 'first_page')
            get(client, '/matches?limit=5&offset=5', 'second_page')
            teams = get(client, '/teams', 'teams')
            competitions = get(client, '/competitions', 'competitions')
            finished = sorted((r for r in all_matches if r['status']=='finished'),key=lambda r:r['id'])[0]
            semantic['representative_id'] = finished['id']
            get(client, '/matches/'+finished['id'], 'match_detail')
            get(client, '/teams/'+finished['home']['id'], 'team_detail')
            get(client, '/teams/'+finished['home']['id']+'/form', 'team_form')
            get(client, '/competitions/'+finished['competition_id']+'/standings', 'standings')
            get(client, '/matches/'+finished['id']+'/odds', 'odds')
            get(client, '/matches/'+finished['id']+'/odds-history', 'odds_history')
            prediction = get(client, '/matches/'+finished['id']+'/predictions', 'finished_prediction')
            assert prediction['available'] is False, 'Finished real match must abstain'
            for suffix in ('events','lineups','statistics'):
                get(client, '/matches/'+finished['id']+'/'+suffix, suffix)
            with sqlite3.connect(state/'core.sqlite3') as db:
                assert db.execute('SELECT COUNT(*) FROM product_jobs').fetchone()[0] == initial_jobs
            raw_checks.append({'name':'browsing_created_no_jobs','passed':True})
            explanation = post_job(client, app, '/matches/'+finished['id']+'/explanations', {}, 'explanation')
            assert explanation['result']['kind'] == 'deterministic'
            get(client, explanation['result']['evidence'][0]['url'].removeprefix(api.API), 'explanation_evidence')
            for kind in ('json','csv','xlsx'):
                job = post_job(client, app, '/exports', {'match_id':finished['id'],'format':kind}, 'export_'+kind)
                download = client.get(job['result']['download_url'])
                assert download.status_code == 200
                digest = hashlib.sha256(download.content).hexdigest()
                assert digest == job['result']['sha256']
                artifacts.append({'format':kind,'bytes':len(download.content),'sha256':digest,'filename':job['result']['filename']})
                if kind == 'json':
                    semantic['download_json'] = normalize(download.json())
                elif kind == 'csv':
                    semantic['download_csv'] = list(csv.reader(io.StringIO(download.content.decode('utf-8-sig'))))
                else:
                    from openpyxl import load_workbook
                    workbook = load_workbook(io.BytesIO(download.content), data_only=False)
                    semantic['download_xlsx'] = {sheet.title:[list(row) for row in sheet.iter_rows(values_only=True)] for sheet in workbook}
                    workbook.close()
            final_domain_hash = hashlib.sha256(json.dumps(app.state.product.rows(),sort_keys=True).encode()).hexdigest()
            assert final_domain_hash == initial_domain_hash, 'Browsing/jobs changed canonical retained records'
            raw_checks.append({'name':'retained_domain_records_unchanged','passed':True,'sha256':initial_domain_hash})
        # Create a new application over the same private state, without worker startup.
        restarted = api.create_app(state, **kwargs)
        with TestClient(restarted) as client:
            client.headers['Authorization'] = 'Bearer '+fixture_token
            persisted = []
            for job in jobs_completed:
                response = client.get(api.API+'/jobs/'+job['id'])
                assert response.status_code == 200
                actual = job_semantic(response.json())
                assert actual == job_semantic(job), 'Completed job changed after application restart'
                persisted.append(actual)
            semantic['persisted_jobs_after_restart'] = persisted
            assert len(restarted.state.product.rows()) == len(initial_rows)
        raw_checks.append({'name':'completed_jobs_survive_new_application','passed':True,'jobs':len(jobs_completed)})
    assert not network_attempts, 'An offline workflow attempted network acquisition'
    assert sha(snapshot) == snapshot_hash, 'The common snapshot was changed'
    assert source_files == {p.relative_to(source).as_posix():sha(p) for p in sorted((source/'src/dragonhydra').rglob('*.py'))}, 'Source changed during characterization'
    receipt = {'schema_version':1,'lane':args.lane,'passed':True,'source_root':str(source),'source_commit':args.source_commit,
        'api_module':str(Path(api.__file__).resolve()),'interpreter':sys.executable,'snapshot_sha256':snapshot_hash,
        'source_files_sha256':source_files,'harness_sha256':sha(__file__),
        'fixed_clock':FIXED_NOW,'random_seed':1729,'start_worker':False,'network_attempts':network_attempts,
        'state':str(state),'semantic':semantic,'checks':raw_checks,'artifacts':artifacts,
        'normalization':{'job_ids':'Named placeholders; referenced URLs/filenames replaced consistently',
            'job_operational_timestamps':sorted(VOLATILE_JOB_FIELDS), 'health':['version','source_sha'],
            'export_artifacts':'Actual SHA256 checked; compare parsed JSON/CSV and XLSX cell values instead of ZIP timestamps',
            'installation':'Candidate identity and module additions have separate acceptance; existing domain outputs compared'},
        'finished_utc':datetime.now(timezone.utc).isoformat()}
    write_new(output,receipt)
    print(json.dumps({'passed':True,'lane':args.lane,'matches':semantic['counts']['matches'],'output':str(output)}))


def compare(args):
    baseline = json.loads(args.baseline.read_text())
    candidate = json.loads(args.candidate.read_text())
    assert baseline['passed'] and candidate['passed']
    assert baseline['snapshot_sha256'] == candidate['snapshot_sha256']
    def private_state(value, root):
        if isinstance(value,dict):
            return {key:private_state(item,root) for key,item in value.items()}
        if isinstance(value,list):
            return [private_state(item,root) for item in value]
        if isinstance(value,str) and (value == root or value.startswith(root+os.sep)):
            return '<private-lane-state>'+value[len(root):]
        return value
    left = private_state(baseline['semantic'],baseline['state'])
    right = private_state(candidate['semantic'],candidate['state'])
    differences = [key for key in sorted(set(left)|set(right)) if left.get(key) != right.get(key)]
    receipt = {'schema_version':1,'passed':not differences,'baseline_receipt_sha256':sha(args.baseline),
        'candidate_receipt_sha256':sha(args.candidate),'snapshot_sha256':baseline['snapshot_sha256'],
        'compared_groups':len(left),'difference_groups':differences,'counts':left.get('counts'),
        'comparison_normalization':{'private_state_root':'Only an exact value/prefix matching each receipt’s own private state root becomes <private-lane-state>; isolated export locations otherwise retain their relative paths.'},
        'scope':'Fresh-process source API/domain characterization; no installed/native UI, service, provider network, inference or future-result forecast proof'}
    write_new(inside(args.output,args.lab.resolve()),receipt)
    print(json.dumps(receipt,indent=2))
    return 0 if receipt['passed'] else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action',required=True)
    run = sub.add_parser('run')
    run.add_argument('--lane',choices=['baseline','candidate'],required=True)
    for option in ('lab','source','snapshot','state','output'):
        run.add_argument('--'+option,type=Path,required=True)
    run.add_argument('--source-commit',required=True)
    check = sub.add_parser('compare')
    for option in ('lab','baseline','candidate','output'):
        check.add_argument('--'+option,type=Path,required=True)
    args = parser.parse_args()
    if args.action == 'compare':
        return compare(args)
    try:
        run_lane(args)
    except Exception as error:
        if not args.output.exists():
            write_new(inside(args.output,args.lab.resolve()), {'schema_version':1,'lane':args.lane,'passed':False,
                'source_root':str(args.source.resolve()),'state':str(args.state.resolve()),
                'failure_class':type(error).__name__,'failure':str(error),
                'scope':'Failed characterization attempt; inspect harness versus product cause before classifying.'})
        raise
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
