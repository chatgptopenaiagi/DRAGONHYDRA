"""Verify adapters and honest development identity inside the frozen server."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import threading
import time
from urllib.error import HTTPError
from urllib.request import ProxyHandler, Request, build_opener, urlopen
from urllib.parse import urlencode


def seed_synthetic_projection(state):
    """Source-seeded read/projection fixture, never an authenticated feed import."""
    from uuid import uuid4
    import dragonhydra.product as source_product
    from dragonhydra.connectors.core import Document, redact_url
    expected_source = Path(__file__).resolve().parents[2] / 'src'
    assert Path(source_product.__file__).resolve().is_relative_to(expected_source)
    product = source_product.Product(state)
    store = product.connector_store
    provider = 'api-football'
    first, second = '2026-10-31T10:00:00Z', '2026-10-31T10:01:00Z'
    raw_directory = state / 'raw/connectors'
    raw_directory.mkdir(parents=True, exist_ok=True)
    def document(label, clock):
        body = json.dumps({'synthetic': True, 'label': 'SYNTHETIC frozen '+label+' document'}, sort_keys=True).encode()
        sha = hashlib.sha256(body).hexdigest()
        url = 'https://v3.football.api-sports.io/SYNTHETIC/frozen-'+label
        (raw_directory / (sha+'.payload')).write_bytes(body)
        doc = Document(url, url, body, clock, sha, 'application/json', uuid4().hex, sha+'.payload')
        store.receipt(provider, doc)
        return doc
    primary, secondary = document('parent-fixture', first), document('secondary-quote', second)
    fixture = {'source_record_id': 'SYNTHETIC-frozen-projection-42', 'sport': 'football',
        'competition': 'SYNTHETIC frozen projection league', 'season': 'SYNTHETIC',
        'home': 'SYNTHETIC projection home', 'away': 'SYNTHETIC projection away',
        'event_date': '2026-10-31', 'kickoff_utc': None, 'source_local_time': None,
        'status': 'synthetic', 'score_home': None, 'score_away': None,
        'source_document_sha256': primary.sha256, 'statistics': {},
        'attributes': {'data_origin': 'synthetic', 'proof_scope': 'source-seeded fixture projection; not provider HTTP'},
        'original': {'synthetic': True},
        'odds': [{'provider': 'SYNTHETIC fixture bookmaker', 'feed': 'SYNTHETIC fixture quotes',
                  'market': '1x2', 'period': 'regulation', 'selection': 'home',
                  'settlement_rules': 'SYNTHETIC regulation-only fixture', 'decimal_odds': 2.1,
                  'quote_at': None, 'source_document_sha256': secondary.sha256}]}
    result = store.ingest(provider, [fixture], [primary, secondary])
    assert result['inserted'] == 1 and result['quarantined'] == 0
    match = product.matches(provider=provider)['items'][0]
    assert match['status'] == 'synthetic' and match['data_state'] == 'Synthetic demo'
    return {'provider': provider, 'match': match, 'primary': primary, 'secondary': secondary,
            'secondary_url': redact_url(secondary.url)}


def seed_synthetic_context(state):
    """Source-seeded retained fixture; frozen acquisition is NOT exercised."""
    from contextlib import closing
    from uuid import UUID, uuid4
    import dragonhydra.product as source_product
    from dragonhydra import source_context
    from dragonhydra.connectors import research, statsbomb_context as binding
    from dragonhydra.connectors import statsbomb_context_jobs, statsbomb_context_parser as native_parser
    from dragonhydra.connectors.core import Document
    expected_source = Path(__file__).resolve().parents[2] / 'src'
    assert Path(source_product.__file__).resolve().is_relative_to(expected_source)
    assert Path(statsbomb_context_jobs.__file__).resolve().is_relative_to(expected_source)
    product = source_product.Product(state)
    raw_directory = state / 'raw/connectors'
    raw_directory.mkdir(parents=True, exist_ok=True)
    def document(body, url, clock):
        raw = json.dumps(body, ensure_ascii=False, sort_keys=True).encode()
        sha = hashlib.sha256(raw).hexdigest()
        (raw_directory/(sha+'.payload')).write_bytes(raw)
        resolved = url.replace(research.STATSBOMB_BASE, 'https://raw.githubusercontent.com/hudl/open-data/refs/heads/master/data/')
        doc = Document(url, resolved, raw, clock, sha, 'application/json', uuid4().hex, sha+'.payload')
        product.connector_store.receipt('statsbomb', doc)
        return doc
    catalog = document([{'competition_id':43,'season_id':106,'competition_name':'FIFA World Cup',
        'season_name':'2022','synthetic_fixture':True}], research.STATSBOMB_BASE+'competitions.json', '2026-10-31T10:00:00Z')
    native = {'match_id':3869685,'match_date':'2022-12-18','kick_off':'15:00:00.000',
        'competition':{'competition_id':43,'competition_name':'FIFA World Cup'},
        'season':{'season_id':106,'season_name':'2022'},
        'home_team':{'home_team_id':779,'home_team_name':'Argentina'},
        'away_team':{'away_team_id':771,'away_team_name':'France'},
        'home_score':3,'away_score':3,'match_status':'available',
        'stadium':{'name':'SYNTHETIC frozen verification stadium'},
        'metadata':{'data_version':'SYNTHETIC frozen fixture; no live import'}}
    matches = document([native], research.STATSBOMB_BASE+'matches/43/106.json', '2026-10-31T10:01:00Z')
    class RetainedOnly:
        def get(self, url):
            if url == research.STATSBOMB_BASE+'competitions.json': return catalog
            assert url == research.STATSBOMB_BASE+'matches/43/106.json'
            return matches
    fixture = research._statsbomb({'competition_id':43,'season_id':106}, RetainedOnly(), lambda:None)[0]
    assert product.connector_store.ingest('statsbomb', [fixture], [catalog,matches])['inserted'] == 1
    observation = product.connector_store.rows('statsbomb')[0]['id']
    lineups = [ {'team_id':team,'team_name':name,'lineup':[{'player_id':player,'player_name':'SYNTHETIC '+name+' player'}]}
                for team,name,player in ((779,'Argentina',1001),(771,'France',2001))]
    events = [{'id':str(UUID(int=number)),'index':number,'type':{'id':kind,'name':label},
               'team':{'id':team,'name':name},'period':period,'synthetic_fixture':True}
              for number,kind,label,team,name,period in ((1,18,'Half Start',779,'Argentina',1),
                  (2,30,'Pass',779,'Argentina',1),(3,30,'Pass',771,'France',2))]
    docs = {'events':document(events, binding.ROLE_URLS['events'], '2026-10-31T11:00:00Z'),
            'lineups':document(lineups, binding.ROLE_URLS['lineups'], '2026-10-31T11:01:00Z')}
    with closing(product.connect()) as db:
        parent = binding.parent_binding(db, raw_directory, observation)
        documents = {role:binding.document_binding(db, raw_directory, role, doc.acquisition_id) for role,doc in docs.items()}
    projection = native_parser.parse(docs['events'].body, docs['lineups'].body, parent=parent)
    receipt = source_context.append(product.db_path, {'provider':'statsbomb','source_record_id':'3869685',
        'parent':parent,'documents':documents,'parser_version':native_parser.VERSION,'projection':projection},
        validate_dependencies=native_parser.make_validator(raw_directory))
    return {'match_id':product.match_id({'source_id':'statsbomb','fixture_key':'3869685'}),
            'observation_id':observation,'context_id':receipt['record_id'],'documents':documents,
            'events':events,'projection':projection,'context_receipt':receipt}


def retained_context_state(state, *, include_jobs=True):
    """A read-only fingerprint makes accidental GET writes visible."""
    from contextlib import closing
    import sqlite3
    with closing(sqlite3.connect((state/'core.sqlite3').as_uri()+'?mode=ro', uri=True)) as db:
        db.execute('PRAGMA query_only=ON')
        excluded = {'product_sessions','sqlite_sequence'}
        if not include_jobs:
            excluded.update(('product_jobs','product_updates'))
        names = [row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name") if row[0] not in excluded]
        tables = {name:db.execute('SELECT * FROM "'+name.replace('"','""')+'" ORDER BY rowid').fetchall() for name in names}
    files = {path.name:hashlib.sha256(path.read_bytes()).hexdigest() for path in (state/'raw/connectors').glob('*.payload')}
    return hashlib.sha256(json.dumps({'tables':tables,'raw':files},sort_keys=True,allow_nan=False,
        default=lambda value:{'blob_sha256':hashlib.sha256(value).hexdigest(),'bytes':len(value)}).encode()).hexdigest()


@contextmanager
def synthetic_completion_stub(package, key):
    """One bounded loopback HTTP fixture, NOT a model or inference runtime."""
    from http.server import BaseHTTPRequestHandler, HTTPServer
    facts = package['allowed_facts']
    selected = next(fact for fact in facts if fact['evidence_aliases'] == ['E1','C1'])
    observed = {'synthetic':True,'model_inference':False,'requests':[], 'errors':[],
                'selected_fact_id':selected['fact_id'],'owned_thread_stopped':False,'owned_port_released':False}
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass  # Authentication headers and request bodies never enter logs.
        def do_POST(self):
            try:
                assert self.path == '/completion'
                assert self.headers.get('Authorization') == 'Bearer '+key
                length = int(self.headers.get('Content-Length', '0'))
                assert 0 < length <= 64*1024 and len(observed['requests']) == 0
                self.connection.settimeout(3)
                body = self.rfile.read(length)
                assert len(body) == length
                request = json.loads(body)
                schema = request['json_schema']
                assert schema == {'type':'object', 'properties':{'fact_id':{'type':'string',
                    'enum':[fact['fact_id'] for fact in facts]}}, 'required':['fact_id'],'additionalProperties':False}
                assert request['n_predict'] <= 192 and request['temperature'] == 0 and request['stream'] is False
                assert all(fact['observation'] in request['prompt'] for fact in facts)
                observed['requests'].append({'path':self.path,'bytes':len(body),
                    'sha256':hashlib.sha256(body).hexdigest(),'fact_ids':schema['properties']['fact_id']['enum']})
                response = json.dumps({'content':json.dumps({'fact_id':selected['fact_id']})}).encode()
                self.send_response(200)
                self.send_header('Content-Type','application/json')
                self.send_header('Content-Length',str(len(response)))
                self.end_headers()
                self.wfile.write(response)
            except Exception:
                observed['errors'].append('SYNTHETIC_COMPLETION_REQUEST_REJECTED')
                self.send_response(400); self.end_headers()
        def do_GET(self):
            observed['errors'].append('SYNTHETIC_COMPLETION_UNEXPECTED_GET')
            self.send_response(405); self.end_headers()
    server = HTTPServer(('127.0.0.1',0),Handler)
    port = server.server_address[1]
    observed['endpoint'] = 'http://127.0.0.1:'+str(port)
    thread = threading.Thread(target=server.serve_forever, name='synthetic-completion-fixture', daemon=True)
    thread.start()
    try:
        yield observed
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        observed['owned_thread_stopped'] = not thread.is_alive()
        with socket.socket() as probe:
            probe.settimeout(.5)
            observed['owned_port_released'] = probe.connect_ex(('127.0.0.1',port)) != 0


def verify_synthetic_context_package(call, wait_job, state, fixture, record, checks):
    """Exercise frozen HTTP/worker package/3 using SYNTHETIC retained sources.

    The host seeds bytes using the snapshotted source. The tested server must
    independently reconstruct them, and its worker contacts only our explicitly
    configured synthetic completion responder. No Qwen or provider is invoked.
    """
    match = '/matches/'+fixture['match_id']
    context_id = fixture['context_id']
    route = match+'/analysis-package?'+urlencode({'context_record_id':context_id})
    before_reads = retained_context_state(state)
    code, default = call('GET', match+'/analysis-package')
    assert code == 200 and default['schema_version'] == 'sports-evidence-package/2'
    code, package = call('GET', route)
    assert code == 200 and package['schema_version'] == 'sports-evidence-package/3'
    unsigned = {key:value for key,value in package.items() if key != 'package_sha256'}
    canonical = json.dumps(unsigned,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
    assert hashlib.sha256(canonical).hexdigest() == package['package_sha256']
    assert len(json.dumps(package).encode()) <= 16*1024
    assert package['event'] == default['event'] and package['evidence']['E1'] == default['evidence']['E1']
    assert package['event']['score'] == {'home':3,'away':3}
    assert package['context_summary'] == {'event_rows':3,'squad_sizes':[
        {'team_id':779,'team_name':'Argentina','entries':1},{'team_id':771,'team_name':'France','entries':1}]}
    context = package['evidence']['C1']
    assert context['id'] == context_id and context['parent_observation_id'] == fixture['observation_id']
    assert context['record_sha256'] == fixture['context_receipt']['record_content_hash']
    assert context['documents'] == fixture['documents']
    for clock in ('received_at','persisted_at','usable_at'):
        assert context[clock] == fixture['context_receipt'][clock]
    assert context['parser_version'] == 'statsbomb-context/1'
    assert call('GET', match+'/analysis-package')[1] == default
    assert call('GET', route, auth=False)[0] == 401
    assert call('POST', match+'/local-explanations', {'context_record_id':context_id}, auth=False)[0] == 401
    assert call('GET', match+'/analysis-package?context_record_id=latest')[0] == 422
    assert call('POST', match+'/local-explanations', {'context_record_id':context_id,'untrusted':'SYNTHETIC'})[0] == 422
    assert call('POST', match+'/local-explanations', {'context_record_id':True})[0] == 422
    assert call('POST', match+'/local-explanations', {'context_record_id':'source_context:'+'0'*64})[0] == 409
    assert retained_context_state(state) == before_reads
    checks.append('Frozen package/3 reconstructs exact source-seeded SYNTHETIC context/counts/receipts while default package/2 is unchanged; reads and rejected selectors write nothing')
    checks.append('Frozen package/3 selectors enforce authentication and strict explicit immutable IDs without queuing unavailable or injected requests')
    manifest = [fixture['observation_id'],context_id,*(fixture['documents'][role]['id'] for role in ('events','lineups'))]
    sources_before = retained_context_state(state, include_jobs=False)
    def journal():
        from contextlib import closing
        import sqlite3
        with closing(sqlite3.connect((state/'core.sqlite3').as_uri()+'?mode=ro',uri=True)) as db:
            return ({row[0]:row for row in db.execute('SELECT * FROM product_jobs ORDER BY id')},
                    {row[0]:row for row in db.execute('SELECT * FROM product_updates ORDER BY seq')},
                    db.execute('SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name').fetchall(),
                    dict(db.execute('SELECT name,seq FROM sqlite_sequence')))
    jobs_before, updates_before, schema_before, sequences_before = journal()
    code, queued = call('POST', match+'/local-explanations', {'context_record_id':context_id})
    assert code == 202 and queued['kind'] == 'local_explanation'
    fallback = wait_job(queued['id'])
    assert fallback['payload']['package'] == package
    result = fallback['result']
    assert result['kind'] == 'deterministic' and result['local_ai']['code'] == 'AI_NOT_CONFIGURED'
    assert result['input_manifest'] == manifest and result['package_sha256'] == package['package_sha256']
    assert [item['id'] for item in result['evidence']] == [fixture['observation_id']]
    assert result['observations'] == [package['allowed_facts'][0]['observation']]
    checks.append('Frozen queued package/3 fully grounds SYNTHETIC sources before its labelled unconfigured deterministic fallback and retains all four manifest IDs')
    code, prior = call('GET', '/local-model/configuration')
    assert code == 200 and not prior['configured'] and prior['credential_source'] == 'none'
    settings_path = state/'local-ai.json'
    settings_before = settings_path.read_bytes() if settings_path.exists() else None
    key = secrets.token_urlsafe(32)
    restored = False
    proof = {'synthetic':True,'model_inference':False,'real_qwen_used':False,'passed':False,
             'provider_acquisition_jobs_submitted':0,'fixture_key_removed':False,'settings_restored':False}
    record['synthetic_context_package_fixture'] = proof
    with synthetic_completion_stub(package,key) as stub:
        proof['http_stub'] = stub
        try:
            code, configured = call('PUT', '/local-model/configuration', {'endpoint':stub['endpoint'],'credential':key})
            assert code == 200 and configured['configured'] and key not in json.dumps(configured)
            code, queued = call('POST', match+'/local-explanations', {'context_record_id':context_id}, key='SYNTHETIC-package3-stub')
            assert code == 202 and queued['kind'] == 'local_explanation'
            accepted = wait_job(queued['id'])
            assert accepted['payload']['package'] == package
            result = accepted['result']
            proof['stub_job_status'] = accepted['status']
            proof['stub_local_ai_code'] = result.get('local_ai',{}).get('code')
            fact = next(fact for fact in package['allowed_facts'] if fact['fact_id'] == stub['selected_fact_id'])
            assert result['kind'] == 'local_llm' and result['mode'] == 'constrained_source_fact_selection'
            assert result['local_ai']['accepted'] and result['fact_id'] == fact['fact_id']
            assert result['observations'] == [fact['observation']] and result['evidence_aliases'] == ['E1','C1']
            assert result['input_manifest'] == manifest and result['package_sha256'] == package['package_sha256']
            assert len(result['evidence']) == 3 and result['evidence'][0]['id'] == fixture['observation_id']
            for role,citation in zip(('events','lineups'),result['evidence'][1:]):
                assert all(citation[field] == value for field,value in fixture['documents'][role].items())
                assert citation['role'] == role and citation['context_record_id'] == context_id
                assert citation['context_record_sha256'] == context['record_sha256']
                assert citation['parent_observation_id'] == fixture['observation_id']
                assert all(citation[clock] == context[clock] for clock in ('received_at','persisted_at','usable_at'))
                code, metadata = call('GET', citation['url'].removeprefix('/dragon/api/v1'))
                assert code == 200 and all(metadata[field] == value for field,value in fixture['documents'][role].items())
                assert not {'body','raw_reference','raw_path','path'}.intersection(metadata)
            code, replay = call('POST', match+'/local-explanations', {'context_record_id':context_id}, key='SYNTHETIC-package3-stub')
            assert code == 202 and replay['id'] == accepted['id'] and replay['result'] == result
            assert call('POST', match+'/local-explanations', {'context_record_id':'source_context:'+'0'*64}, key='SYNTHETIC-package3-stub')[0] == 409
            assert len(stub['requests']) == 1 and not stub['errors']
        finally:
            try:
                code, removed = call('PUT', '/local-model/configuration', {'endpoint':prior['endpoint'],'remove_credential':True})
                restored = code == 200 and removed == prior
            finally:
                # Failure cleanup belongs solely to this freshly owned state.
                # Preserve failure status while removing an orphan fixture key
                # even if its isolated API disappeared during verification.
                vault = state/'vault/local-ai.dpapi'
                vault.unlink(missing_ok=True)
                if settings_before is None:
                    settings_path.unlink(missing_ok=True)
                elif not settings_path.exists() or settings_path.read_bytes() != settings_before:
                    settings_path.write_bytes(settings_before)
                proof['fixture_key_removed'] = not vault.exists()
                proof['settings_restored'] = (settings_path.read_bytes() if settings_path.exists() else None) == settings_before
    assert restored and not (state/'vault/local-ai.dpapi').exists()
    assert (settings_path.read_bytes() if settings_path.exists() else None) == settings_before
    assert call('GET', '/health/ready')[1]['optional_ai'] == 'not_configured'
    assert stub['owned_thread_stopped'] and stub['owned_port_released']
    assert retained_context_state(state, include_jobs=False) == sources_before
    jobs_after, updates_after, schema_after, sequences_after = journal()
    assert schema_after == schema_before
    assert all(jobs_after.get(ident) == row for ident,row in jobs_before.items())
    assert all(updates_after.get(ident) == row for ident,row in updates_before.items())
    assert set(jobs_after)-set(jobs_before) == {fallback['id'],accepted['id']}
    additions = [row for seq,row in updates_after.items() if seq not in updates_before]
    assert len(additions) == 8
    assert sequences_after == dict(sequences_before, product_updates=sequences_before.get('product_updates',0)+8)
    for identifier in (fallback['id'],accepted['id']):
        job_events = [json.loads(row[2]) for row in additions if row[1] == 'job' and json.loads(row[2]).get('id') == identifier]
        data_events = [json.loads(row[2]) for row in additions if row[1] == 'data' and json.loads(row[2]).get('job_id') == identifier]
        assert [event['status'] for event in job_events] == ['queued','running','succeeded']
        assert data_events == [{'job_id':identifier,'kind':'local_explanation'}]
    proof.update({'passed':True,
             'proof_scope':'Source-seeded synthetic context and one synthetic HTTP completion through the tested server worker; not provider ingestion or model acceptance.',
             'schema_version':package['schema_version'],'package_sha256':package['package_sha256'],
             'context_record_id':context_id,'event_rows':3,'squad_entries':[1,1], 'fallback_job_id':fallback['id'],
             'accepted_stub_job_id':accepted['id'],'selected_fact_id':stub['selected_fact_id'],
             'citations':3,'input_manifest':manifest,'http_stub':stub,'settings_restored':restored,
             'fixture_key_removed':True,'retained_sources_unchanged':True,
             'old_jobs_and_outbox_unchanged':True,'new_jobs':2,'correlated_outbox_additions':8})
    assert key not in json.dumps(proof)
    record['synthetic_context_package_fixture'] = proof
    checks.append('Frozen worker accepts one labelled SYNTHETIC HTTP fact-ID response and resolves three exact source citations/four manifest IDs; idempotent replay makes no second completion request')
    checks.append('SYNTHETIC completion responder thread/port close, isolated fixture settings restore byte-for-byte, its temporary key is removed and retained sources remain unchanged; no Qwen/model/provider acquisition')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binary', type=Path, required=True)
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--source-content-sha256', required=True)
    args = parser.parse_args()
    if sys_optimized():
        raise SystemExit('Run verification with assertions enabled.')
    binary, work = args.binary.resolve(), args.work.resolve()
    if work.exists():
        raise SystemExit('Preserve prior verification evidence and use a fresh work directory.')
    work.mkdir(parents=True)
    env = os.environ.copy()
    for name in tuple(env):
        if name in ('PYTHONPATH', 'PYTHONHOME', 'VIRTUAL_ENV', 'CONDA_PREFIX') or name.startswith('DRAGONHYDRA_'):
            env.pop(name, None)
    windows = env.get('SystemRoot', r'C:\Windows')
    env['PATH'] = windows + r'\System32' + os.pathsep + windows
    checks = []
    record = {'started_at': datetime.now(timezone.utc).isoformat(), 'passed': False, 'checks': checks,
              'scope': 'Frozen adapters/settings, source-seeded SYNTHETIC quote/context projections, retained sports packages and lifecycle; no frozen context acquisition, authenticated provider import or model-inference claim'}
    metadata = json.loads(subprocess.check_output([str(binary), '--build-info'], env=env, cwd=work, text=True, timeout=20))
    assert metadata['source_sha'] is None
    assert metadata['source_content_sha256'] == args.source_content_sha256
    assert metadata['build_kind'] == 'connector-development-snapshot'
    record['build_info'] = metadata
    checks.append('Frozen binary embeds the exact development snapshot identity without claiming a release commit')
    state = work / 'state'
    log = (work / 'server.log').open('w', encoding='utf-8')
    proc = subprocess.Popen([str(binary), '--port', '0', '--state', str(state)], env=env, cwd=work,
                            stdout=log, stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW)
    origin = token = None

    opener = build_opener(ProxyHandler({}))
    def call(method, path, body=None, *, auth=True, key=None):
        data = None if body is None else json.dumps(body).encode()
        headers = {'Content-Type': 'application/json'}
        if auth:
            headers['Authorization'] = 'Bearer ' + token
        if key is not None:
            headers['Idempotency-Key'] = key
        request = Request(origin + '/dragon/api/v1' + path, data=data, method=method,
                          headers=headers)
        try:
            with opener.open(request, timeout=10) as response:
                return response.status, json.loads(response.read())
        except HTTPError as exc:
            try:
                return exc.code, json.loads(exc.read())
            finally:
                exc.close()

    def wait_job(identifier, expected='succeeded'):
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            code, row = call('GET', '/jobs/' + identifier)
            assert code == 200
            if row['status'] in ('failed', 'succeeded', 'cancelled', 'interrupted'):
                assert row['status'] == expected, row.get('error')
                return row
            time.sleep(.15)
        raise AssertionError('Frozen worker did not complete its bounded verification job.')

    try:
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            assert proc.poll() is None, 'Frozen server exited before readiness'
            try:
                origin = json.loads((state / 'endpoint.json').read_text())['url']
                token = json.loads((state / 'local-session.json').read_text())['token']
                if call('GET', '/health/ready')[0] == 200:
                    break
            except (OSError, ValueError):
                pass
            time.sleep(.15)
        assert origin and token and call('GET', '/health/ready')[0] == 200
        code, catalog = call('GET', '/connections')
        assert code == 200
        cards = {item['id']: item for item in catalog['items']}
        expected = {'football-data-couk', 'statsbomb', 'nflverse', 'moneypuck', 'cricsheet',
                    'football-data-org', 'api-football', 'the-odds-api', 'sportmonks'}
        assert all(cards[name]['implemented'] for name in expected)
        assert all(cards[name]['record_count'] == 0 for name in expected)
        checks.append('All nine connector adapters import in the isolated private runtime with empty owned state')
        code, configured = call('PUT', '/connections/nflverse/configuration',
                                {'config': {'seasons': [2025]}, 'interval_seconds': 0})
        assert code == 200 and configured['interval_seconds'] == 0
        assert configured['config']['seasons'] == [2025]
        checks.append('Provider configuration persists through the frozen adapter validation path')
        code, created = call('POST', '/connections/football-data-org/test', {})
        assert code == 202
        deadline = time.monotonic() + 20
        job = None
        while time.monotonic() < deadline:
            code, job = call('GET', '/jobs/' + created['id'])
            assert code == 200
            if job['status'] in ('failed', 'succeeded', 'cancelled', 'interrupted'):
                break
            time.sleep(.15)
        assert job['status'] == 'failed' and job['error']['code'] == 'NEEDS_KEY'
        checks.append('Credential-free frozen job fails gracefully with NEEDS_KEY instead of attempting live authentication')
        code, configuration = call('GET', '/local-model/configuration')
        assert code == 200 and configuration == {'endpoint': '', 'configured': False,
            'endpoint_source': 'none', 'credential_source': 'none'}
        assert call('GET', '/health/ready')[1]['optional_ai'] == 'not_configured'
        fixture_key = 'frozen-settings-fixture-key-20261031'
        code, invalid = call('PUT', '/local-model/configuration',
                             {'endpoint': 'https://example.test/model', 'credential': fixture_key})
        assert code == 409 and invalid['error']['code'] == 'AI_ENDPOINT_INVALID'
        assert not (state / 'local-ai.json').exists() and not (state / 'vault/local-ai.dpapi').exists()
        assert fixture_key not in json.dumps(invalid)
        checks.append('Frozen local-model configuration reads safely and rejects a remote endpoint before writing settings or a key')
        code, saved = call('PUT', '/local-model/configuration',
                           {'endpoint': 'http://127.0.0.1:18746', 'credential': fixture_key})
        assert code == 200 and saved['configured'] and saved['credential_source'] == 'vault'
        code, visible = call('GET', '/local-model/configuration')
        assert code == 200 and set(visible) == {'endpoint', 'configured', 'endpoint_source', 'credential_source'}
        assert visible['endpoint_source'] == 'stored' and visible['credential_source'] == 'vault'
        assert fixture_key not in json.dumps(visible) and fixture_key not in json.dumps(saved)
        assert fixture_key.encode() not in (state / 'vault/local-ai.dpapi').read_bytes()
        assert fixture_key.encode() not in (state / 'local-ai.json').read_bytes()
        assert call('GET', '/health/ready')[1]['optional_ai'] == 'configured_not_tested'
        system = call('GET', '/system')[1]
        assert system['ai'] == 'configured_not_tested' and system['local_ai']['runtime_health'] == 'not_checked'
        assert system['local_ai']['configured'] and system['capabilities']['local_llm']
        checks.append('Frozen server saves its fixture key with current-account DPAPI and exposes only credential-source status')
        # Configuration is passive: never request inference with this dummy key.
        code, removed = call('PUT', '/local-model/configuration',
                             {'endpoint': 'http://127.0.0.1:18746', 'remove_credential': True})
        assert code == 200 and not removed['configured'] and removed['credential_source'] == 'none'
        assert not (state / 'vault/local-ai.dpapi').exists()
        assert call('GET', '/health/ready')[1]['optional_ai'] == 'not_configured'
        assert not call('GET', '/system')[1]['capabilities']['local_llm']
        checks.append('Explicit frozen key removal leaves no stored fixture key before any local-model job is requested')
        code, created = call('POST', '/connections/openfootball/sync', {})
        assert code == 202 and wait_job(created['id'])['result']['record_count'] == 760
        code, matches = call('GET', '/matches?limit=1')
        assert code == 200 and matches['total'] == 760
        selected = matches['items'][0]
        match_path = '/matches/' + selected['id']
        code, package = call('GET', match_path + '/analysis-package')
        assert code == 200 and package['schema_version'] == 'sports-evidence-package/2'
        assert package['event']['id'] == selected['id']
        canonical = json.dumps({key: value for key, value in package.items() if key != 'package_sha256'},
                               ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(',', ':')).encode('utf-8')
        assert hashlib.sha256(canonical).hexdigest() == package['package_sha256']
        evidence = package['evidence']['E1']
        assert evidence['id'] == selected['evidence_id']
        code, retained = call('GET', '/evidence/' + evidence['id'])
        assert code == 200 and retained['source_hash'] == evidence['source_sha256']
        record['sports_package'] = {'match_id': selected['id'], 'sha256': package['package_sha256'],
                                    'evidence_id': evidence['id']}
        checks.append('Frozen sports package exports retained public evidence with an independently reproduced canonical SHA-256')
        code, created = call('POST', match_path + '/local-explanations', {})
        assert code == 202
        local = wait_job(created['id'])['result']
        assert local['kind'] == 'deterministic'
        assert local['local_ai']['requested'] and not local['local_ai']['accepted']
        assert local['local_ai']['code'] == 'AI_NOT_CONFIGURED'
        assert local['package_sha256'] == package['package_sha256']
        assert local['input_manifest'] == [evidence['id']]
        assert local['observations'] == [package['allowed_observations'][0]]
        assert any('deterministic' in item for item in local['unknowns'])
        checks.append('Explicit frozen local-model job completes with a labelled AI_NOT_CONFIGURED deterministic fallback and the original citation')
        code, created = call('POST', match_path + '/explanations', {})
        assert code == 202
        standard = wait_job(created['id'])['result']
        assert standard['kind'] == 'deterministic' and 'local_ai' not in standard
        assert standard['input_manifest'] == [evidence['id']]
        checks.append('Standard explanation remains deterministic after the optional local-model action')
        synthetic = seed_synthetic_projection(state)
        primary, secondary = synthetic['primary'], synthetic['secondary']
        synthetic_id = synthetic['match']['id']
        code, match = call('GET', '/matches/' + synthetic_id)
        assert code == 200 and match['status'] == 'synthetic' and match['data_state'] == 'Synthetic demo'
        code, odds = call('GET', '/matches/' + synthetic_id + '/odds')
        assert code == 200 and len(odds['items']) == 1
        quote = odds['items'][0]
        assert quote['provenance_status'] == 'bound'
        assert quote['acquisition_id'] == secondary.acquisition_id != primary.acquisition_id
        assert quote['captured_at'] == secondary.captured_at != primary.captured_at
        assert quote['source_document_sha256'] == secondary.sha256 != primary.sha256
        assert quote['source_url'] == synthetic['secondary_url'] != primary.url
        assert quote['observation_received_at'] == primary.captured_at
        assert quote['observation_evidence_id'] == synthetic['match']['evidence_id']
        metadata_url = '/connections/' + synthetic['provider'] + '/acquisitions/' + secondary.acquisition_id
        assert quote['acquisition_url'] == '/dragon/api/v1' + metadata_url
        checks.append('Source-seeded SYNTHETIC fixture projects the secondary quote acquisition, clock, hash and URL separately from its parent; no provider HTTP import')
        code, receipt = call('GET', metadata_url)
        assert code == 200 and receipt['provider'] == synthetic['provider']
        assert receipt['id'] == secondary.acquisition_id and receipt['sha256'] == secondary.sha256
        assert receipt['captured_at'] == secondary.captured_at and receipt['original_url'] == synthetic['secondary_url']
        assert not {'body', 'raw_reference', 'raw_path', 'path'}.intersection(receipt)
        assert not {'body', 'raw_reference', 'raw_path', 'path'}.intersection(quote)
        assert secondary.body.decode() not in json.dumps(receipt)
        assert str(raw_directory := state / 'raw/connectors') not in json.dumps(receipt)
        assert call('GET', metadata_url.replace('/api-football/', '/statsbomb/'))[0] == 404
        assert call('GET', metadata_url, auth=False)[0] == 401
        record['synthetic_projection_fixture'] = {'synthetic': True, 'provider': synthetic['provider'],
            'proof_scope': 'Source snapshot Store seeded isolated state; frozen binary served read/projection APIs only.',
            'provider_http_requests': 0, 'authenticated_feed_import': False, 'match_id': synthetic_id,
            'parent_acquisition_id': primary.acquisition_id, 'quote_acquisition_id': secondary.acquisition_id,
            'parent_capture': primary.captured_at, 'quote_capture': secondary.captured_at,
            'parent_sha256': primary.sha256, 'quote_sha256': secondary.sha256,
            'quote_metadata_url': quote['acquisition_url'], 'wrong_provider_status': 404,
            'unauthenticated_status': 401, 'raw_body_or_path_exposed': False}
        checks.append('Frozen secondary acquisition metadata is authenticated and provider-scoped and returns no raw body or filesystem path')
        context_fixture = seed_synthetic_context(state)
        context_path = '/matches/'+context_fixture['match_id']+'/source-context'
        events_path = '/matches/'+context_fixture['match_id']+'/source-events'
        before_reads = retained_context_state(state)
        code, context = call('GET', context_path)
        assert code == 200 and context['availability'] == 'available'
        assert context['context_record_id'] == context_fixture['context_id']
        assert context['parent_observation_id'] == context_fixture['observation_id']
        assert context['projection'] == context_fixture['projection']
        assert context['projection']['event_summary']['row_count'] == 3
        assert len(context['projection']['squads']) == 2
        assert all(player['player_name'].startswith('SYNTHETIC ') for team in context['projection']['squads'] for player in team['lineup'])
        code, page = call('GET', events_path+'?offset=1&limit=1')
        assert code == 200 and page['total'] == 3 and len(page['items']) == 1
        assert page['items'][0]['id'] == context_fixture['events'][1]['id']
        assert 'synthetic_fixture' not in page['items'][0]
        assert call('GET', events_path+'?limit=201')[0] == 422
        assert call('GET', context_path, auth=False)[0] == 401
        assert call('GET', events_path, auth=False)[0] == 401
        assert call('POST', context_path, {}, auth=False)[0] == 401
        # Accepted context jobs can fetch: do not queue one in this smoke.
        assert call('POST', context_path, {'untrusted_url':'https://example.test/'})[0] == 422
        assert call('POST', match_path+'/source-context', {})[0] == 400
        for document in context['documents']:
            code, acquisition = call('GET', document['metadata_url'].removeprefix('/dragon/api/v1'))
            assert code == 200 and acquisition['id'] == document['id'] and acquisition['http_status'] == 200
            assert not {'body','raw_reference','raw_path','path'}.intersection(acquisition)
        assert call('GET', context_path)[1]['context_record_id'] == context_fixture['context_id']
        assert retained_context_state(state) == before_reads
        record['synthetic_context_fixture'] = {'synthetic':True,
            'proof_scope':'Source snapshot seeded receipt-backed synthetic native documents and full-parser context; frozen binary served authenticated reads and rejected invalid writes only.',
            'frozen_acquisition_jobs_executed':0,'provider_http_requests':0,'match_id':context_fixture['match_id'],
            'parent_observation_id':context_fixture['observation_id'],'context_record_id':context_fixture['context_id'],
            'event_rows':3,'squads':2,'page_rows':1,'read_only_state_fingerprint':before_reads,
            'context_payload_version':'source-context/1','parser_version':'statsbomb-context/1'}
        checks.append('Frozen authenticated context/counts/squads/pages reconstruct receipt-backed SYNTHETIC retained data seeded by source snapshot; no frozen acquisition job')
        checks.append('Frozen context routes enforce authentication, page bounds and write validation while repeated retained reads preserve jobs, receipts, observations and raw bytes')
        verify_synthetic_context_package(call, wait_job, state, context_fixture, record, checks)
        with opener.open(origin + '/', timeout=5) as response:
            assert b'DRAGONHYDRA' in response.read()
        with opener.open(origin + '/app.js', timeout=5) as response:
            script = response.read()
            assert all(label in script for label in (b'Use local model', b'Export sports package',
                                                      b'Configure local model', b'Save local model', b'Remove saved model key',
                                                      b'DETERMINISTIC EVIDENCE SUMMARY', b'LOCAL MODEL',
                                                      b'Load events and squads', b'Refresh source context',
                                                      b'Use local model with source counts', b'Export package with source counts'))
        checks.append('Frozen dashboard includes separate local-model and structured-package controls with explicit analysis labels')
        assert (binary.parent / '_internal/tzdata/zoneinfo/America/New_York').is_file()
        checks.append('Bundled dashboard serves and Eastern timezone data is present')
        assert call('POST', '/system/shutdown', {})[0] == 200
        proc.wait(timeout=15)
        assert proc.returncode == 0
        checks.append('Authenticated shutdown exits zero and releases only this verification coordinator')
        record['passed'] = True
    except Exception as exc:
        record['error'] = type(exc).__name__ + ': ' + str(exc)
        raise
    finally:
        if proc.poll() is None:
            if origin and token:
                try:
                    call('POST', '/system/shutdown', {})
                    proc.wait(timeout=10)
                except Exception:
                    proc.terminate()
                    proc.wait(timeout=5)
            else:
                proc.terminate()
                proc.wait(timeout=5)
        log.close()
        record['finished_at'] = datetime.now(timezone.utc).isoformat()
        (work / 'verification.json').write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8')
        print(json.dumps(record, indent=2))


def sys_optimized():
    import sys
    return sys.flags.optimize


if __name__ == '__main__':
    main()
