"""Real retained package/3 grounding with SYNTHETIC fact-ID selection only.

No Product construction, database/schema write, provider/API request, worker,
settings access, model runtime or inference is permitted. Existing real retained
documents supply facts; fabricated selection input tests application resolution.
"""
from __future__ import annotations

import argparse
from contextlib import closing, ExitStack
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys
from types import MethodType, SimpleNamespace
import traceback
from unittest.mock import patch
import urllib.request


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from dragonhydra import local_ai, local_ai_context, public_results, source_context
from dragonhydra.cognition import memory
from dragonhydra.connectors.core import Transport
from dragonhydra.connectors.store import Store
from dragonhydra.connectors import statsbomb_context as binding
from dragonhydra.jobs import Jobs
from dragonhydra.local_ai_settings import Settings
from dragonhydra.product import Product, identity


CONTEXT_ID = 'source_context:ee80300baae09fc55c61a5312abdc7553d072bcdd3c2e3dbf4ce13a2bb7466fe'
STATE = ROOT/'runtime/scratch/statsbomb-real-20261031-1'
MARKER = 'REAL-CONTEXT-VERIFICATION.json'


def digest(path):
    with path.open('rb') as incoming:
        return hashlib.file_digest(incoming,'sha256').hexdigest()


def canonical(value):
    return json.dumps(value,ensure_ascii=False,allow_nan=False,sort_keys=True,separators=(',',':')).encode()


def private_directory(path):
    path.mkdir(parents=True)
    if os.name == 'nt':
        user = subprocess.check_output([r'C:\Windows\System32\whoami.exe'],text=True).strip()
        result = subprocess.run([r'C:\Windows\System32\icacls.exe',str(path),'/inheritance:r','/grant:r',
            user+':(OI)(CI)(F)','SYSTEM:(OI)(CI)(F)'],capture_output=True)
        assert result.returncode == 0, 'PRIVATE_EVIDENCE_ACL_FAILED'
    else:
        path.chmod(0o700)


def snapshot(state):
    """All table contents and exact selected database/raw/marker file bytes."""
    database = state/'core.sqlite3'
    physical = {name:{'bytes':(state/name).stat().st_size,'sha256':digest(state/name)}
                for name in ('core.sqlite3','core.sqlite3-wal','core.sqlite3-shm',MARKER) if (state/name).is_file()}
    tables = {}
    with closing(sqlite3.connect(database.as_uri()+'?mode=ro',uri=True,timeout=10)) as db:
        db.execute('PRAGMA query_only=ON'); db.execute('BEGIN')
        schema = db.execute('SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name').fetchall()
        def typed(value):
            if isinstance(value,bytes):
                return ['blob',len(value),hashlib.sha256(value).hexdigest()]
            if isinstance(value,float):
                return ['real',value.hex()]
            return ['null'] if value is None else ['integer' if isinstance(value,int) else 'text',value]
        for (name,) in db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"):
            quoted = '"'+name.replace('"','""')+'"'
            rows = sorted(canonical([typed(value) for value in row]) for row in db.execute('SELECT * FROM '+quoted))
            tables[name] = {'rows':len(rows),'sha256':hashlib.sha256(b'\n'.join(rows)).hexdigest()}
    raw_dir = state/'raw/connectors'
    raws = {}
    for path in sorted(raw_dir.iterdir()):
        assert path.is_file() and not path.is_symlink() and path.resolve().parent == raw_dir.resolve()
        raws[path.name] = {'bytes':path.stat().st_size,'sha256':digest(path)}
    return {'physical_files':physical,'schema_sha256':hashlib.sha256(canonical(schema)).hexdigest(),
            'tables':tables,'raw_files':raws}


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--state',type=Path,required=True)
    cli.add_argument('--output',type=Path,required=True)
    args = cli.parse_args()
    assert not sys.flags.optimize
    state,output = args.state.resolve(),args.output.resolve()
    assert state == STATE.resolve() and output.is_relative_to(ROOT/'build/connections/sports-package-3-20261031')
    assert not output.exists() and not state.is_relative_to(output) and not output.is_relative_to(state)
    marker = json.loads((state/MARKER).read_text(encoding='utf-8'))
    assert marker['mode'] == 'real_statsbomb_context_verification' and marker['completed'] is True
    assert marker['state'] == state.relative_to(ROOT).as_posix() and marker['context_record_id'] == CONTEXT_ID
    assert marker['native_match_id'] == binding.MATCH_ID
    private_directory(output)
    groups,statements = [],[]
    forbidden = {name:0 for name in ('network','process','model','settings','product_constructor','store_constructor',
        'worker','schema','append','recover','latest','product_find','product_rows','product_evidence','whole_chain')}
    report = {'passed':False,'started_at':datetime.now(timezone.utc).isoformat(),
        'mode':'real_retained_grounding_and_synthetic_fact_id_selection',
        'scope':'Real retained SQLite/documents; fabricated fact-ID input only. No Qwen/runtime acceptance.',
        'model_inference':False,'model_runtime_started':False,'provider_requests':False,'worker_executed':False,
        'synthetic_selection':True,'context_record_id':CONTEXT_ID,'state':state.relative_to(ROOT).as_posix(),
        'groups':groups,'forbidden_attempts':forbidden}
    sources = [Path(__file__).resolve(),*(ROOT/name for name in ('src/dragonhydra/local_ai.py',
        'src/dragonhydra/local_ai_context.py','src/dragonhydra/local_ai_service.py','src/dragonhydra/source_context.py',
        'src/dragonhydra/cognition/memory.py','src/dragonhydra/connectors/statsbomb_context.py',
        'src/dragonhydra/connectors/statsbomb_context_parser.py','src/dragonhydra/product.py'))]
    report['source_hashes_before'] = {path.relative_to(ROOT).as_posix():digest(path) for path in sources}
    before = None
    package = body = selection = None
    original_connect = sqlite3.connect
    database_uri = (state/'core.sqlite3').as_uri()+'?mode=ro'

    def refused(name):
        def reject(*_args,**_kwargs):
            forbidden[name] += 1
            raise AssertionError('FORBIDDEN_'+name.upper())
        return reject

    def readonly_connect(*args,**kwargs):
        database = args[0] if args else kwargs.get('database')
        assert database == database_uri and kwargs.get('uri') is True, 'EXACT_READ_ONLY_DATABASE_REQUIRED'
        db = original_connect(*args,**kwargs)
        db.execute('PRAGMA query_only=ON')
        db.set_trace_callback(statements.append)
        def authorize(action,first,second,*_rest):
            allowed = {sqlite3.SQLITE_SELECT,sqlite3.SQLITE_READ,sqlite3.SQLITE_FUNCTION,sqlite3.SQLITE_RECURSIVE}
            if action in allowed or (action == sqlite3.SQLITE_TRANSACTION and first == 'BEGIN'):
                return sqlite3.SQLITE_OK
            if action == sqlite3.SQLITE_PRAGMA and first == 'query_only' and second in (None,'ON','1'):
                return sqlite3.SQLITE_OK
            forbidden['schema'] += 1
            return sqlite3.SQLITE_DENY
        db.set_authorizer(authorize)
        return db

    def passed(name,**details):
        group = {'name':name,'passed':True,**details}
        groups.append(group); print(json.dumps(group),flush=True)

    try:
        with ExitStack() as guards:
            for target,attribute,name in ((Product,'__init__','product_constructor'),(Product,'connect','product_constructor'),
                (Product,'find','product_find'),(Product,'rows','product_rows'),(Product,'evidence','product_evidence'),
                (Store,'__init__','store_constructor'),(Store,'receipt','append'),(Store,'ingest','append'),
                (Jobs,'__init__','worker'),(Jobs,'start','worker'),(Jobs,'run_once','worker'),(Jobs,'execute','worker'),
                (Transport,'get','network'),(local_ai,'infer','model'),(Settings,'__init__','settings'),
                (Settings,'effective','settings'),(source_context,'append','append'),(source_context,'recover','recover'),
                (source_context,'latest','latest'),(memory,'_schema','schema'),(memory,'_revision_chain','whole_chain'),
                (public_results,'_schema','schema'),(socket,'create_connection','network'),(socket.socket,'connect','network'),
                (socket.socket,'connect_ex','network'),(urllib.request,'urlopen','network'),
                (urllib.request,'build_opener','network'),(local_ai,'build_opener','network'),(subprocess,'Popen','process')):
                guards.enter_context(patch.object(target,attribute,refused(name)))
            guards.enter_context(patch.object(sqlite3,'connect',readonly_connect))
            before = snapshot(state)
            report['before'] = before
            # Only these pure formatting/identity methods are available. No
            # Product initializer, finder, evidence service or DB connector.
            product = SimpleNamespace(state=state,db_path=state/'core.sqlite3')
            for name in ('present','match_id','team_id','competition_id'):
                setattr(product,name,MethodType(getattr(Product,name),product))
            match_id = identity('fixture',binding.PROVIDER,binding.MATCH_ID)
            package = local_ai.build_context_package(product,match_id,CONTEXT_ID)
            assert package['schema_version'] == 'sports-evidence-package/3'
            assert len(local_ai.canonical(package)) <= 16*1024
            assert package['event']['score'] == {'home':3,'away':3}
            assert package['context_summary']['event_rows'] == 4407
            assert {team['team_id']:team['entries'] for team in package['context_summary']['squad_sizes']} == {771:24,779:26}
            assert len([fact for fact in package['allowed_facts'] if 'C1' in fact['evidence_aliases']]) == 3
            passed('Real retained package/3 contains 4407 event rows, 24/26 source squad entries and the original 3:3 observation',
                package_bytes=len(local_ai.canonical(package)),package_sha256=package['package_sha256'])

            context = package['evidence']['C1']; parent = package['evidence']['E1']
            with closing(sqlite3.connect(database_uri,uri=True)) as db:
                payload,fingerprint = db.execute('SELECT payload,fingerprint FROM cognitive_records WHERE kind=? AND record_id=?',
                    (source_context.KIND,CONTEXT_ID)).fetchone()
                payload = json.loads(payload)
                clocks = db.execute('SELECT received_at,persisted_at,usable_at FROM cognitive_receipts WHERE record_id=?',(CONTEXT_ID,)).fetchone()
                assert context['record_sha256'] == fingerprint and context['parent_observation_id'] == parent['id']
                assert context['documents'] == payload['documents']
                assert tuple(context[key] for key in ('received_at','persisted_at','usable_at')) == clocks
                assert parent['id'] == payload['parent']['observation_id']
                assert parent['source_sha256'] == payload['parent']['source_document_sha256']
                for role,document in context['documents'].items():
                    receipt = dict(zip(('id','provider','sha256','original_url','resolved_url','captured_at'),db.execute(
                        'SELECT id,provider,sha256,original_url,resolved_url,captured_at FROM connector_acquisitions WHERE id=?',
                        (document['id'],)).fetchone()))
                    assert receipt == document and document['provider'] == binding.PROVIDER
                    assert document['original_url'] == document['resolved_url'] == binding.ROLE_URLS[role]
                    assert document['sha256'] != parent['source_sha256']
                assert context['documents']['events']['captured_at'] != payload['parent']['match_list_acquisition']['captured_at']
            passed('Context ID/hash, parent and both original role receipt IDs/hashes/URLs/clocks are exact; no parent clock substitution')

            # Grounding must use the cited C1/E1, never re-select a current head.
            with patch.object(local_ai_context,'resolve_match',refused('product_find')):
                assert local_ai.validate_grounding(product,package) == package
            body = local_ai.request_body(package)
            fact_ids = [fact['fact_id'] for fact in package['allowed_facts']]
            assert body['json_schema'] == {'type':'object','properties':{'fact_id':{'type':'string','enum':fact_ids}},
                'required':['fact_id'],'additionalProperties':False}
            assert body['n_predict'] <= 192 and body['stream'] is False and body['cache_prompt'] is False
            for opaque in (parent['id'],context['id'],context['record_sha256'],*(d['id'] for d in context['documents'].values())):
                assert opaque not in body['prompt']
            passed('Exact queued grounding and fact-ID-only request construction use real retained evidence without latest lookup or inference',fact_count=len(fact_ids))

            fact = next(fact for fact in package['allowed_facts'] if 'C1' in fact['evidence_aliases'])
            synthetic = json.dumps({'fact_id':fact['fact_id']})
            selection = local_ai.validate_output(package,synthetic)
            assert selection['observation'] == fact['observation'] and selection['evidence_aliases'] == ['E1','C1']
            assert len(selection['evidence']) == 3 and len(selection['input_manifest']) == len(set(selection['input_manifest'])) == 4
            expected_manifest = [parent['id'],context['id'],*(context['documents'][role]['id'] for role in source_context.ROLES)]
            assert selection['input_manifest'] == expected_manifest and selection['evidence'][0]['id'] == parent['id']
            for citation in selection['evidence'][1:]:
                document = context['documents'][citation['role']]
                assert {key:citation[key] for key in document} == document
                assert citation['context_record_id'] == CONTEXT_ID and citation['context_record_sha256'] == context['record_sha256']
                assert citation['parent_observation_id'] == parent['id']
                assert tuple(citation[key] for key in ('received_at','persisted_at','usable_at')) == clocks
            report['synthetic_fact_id'] = fact['fact_id']
            report['synthetic_selection_origin'] = 'Fabricated fact-ID JSON; validate_output contract only. No model generated this selection.'
            passed('SYNTHETIC fact-ID selection resolves three source citations and the four-ID input manifest; NO model/runtime acceptance',
                fact_id=fact['fact_id'],citations=3,input_ids=4)

            changed = deepcopy(package)
            changed['context_summary']['event_rows'] += 1
            changed['allowed_facts'] = local_ai_context._facts(changed['event'],changed['context_summary'])
            changed['package_sha256'] = hashlib.sha256(local_ai.canonical({key:value for key,value in changed.items() if key!='package_sha256'})).hexdigest()
            local_ai.validate_package(changed)  # Structurally coherent forgery.
            try:
                local_ai.validate_grounding(product,changed)
                raise AssertionError('Rehashed fabricated row count was accepted.')
            except local_ai.LocalAIError as error:
                assert error.code == 'AI_EVIDENCE_MISMATCH'
            passed('A coherent rehashed but invented event-row count is rejected against the real retained sources before inference')

            after = snapshot(state)
            report['after'] = after
            assert before == after, 'Retained database bytes/schema/tables/raw/marker changed.'
            assert not any(forbidden.values())
            assert all(sql.lstrip().upper().startswith(('SELECT','BEGIN','PRAGMA QUERY_ONLY')) for sql in statements)
            report.update(database_bytes_unchanged=True,schema_unchanged=True,all_tables_unchanged=True,
                raw_files_unchanged=True,marker_unchanged=True,read_only_connections=True,
                sql_statement_count=len(statements),sql_statements_sha256=hashlib.sha256(canonical(statements)).hexdigest())
            passed('All database/sidecar bytes, schema, every table, raw files and marker are unchanged; all forbidden counters remain zero')
            report['passed'] = True
    except Exception:
        report['error'] = traceback.format_exc()
        print(json.dumps({'passed':False,'error':report['error']}),flush=True)
    finally:
        report['source_hashes_after'] = {path.relative_to(ROOT).as_posix():digest(path) for path in sources}
        report['source_files_unchanged'] = report['source_hashes_before'] == report['source_hashes_after']
        report['passed'] = report['passed'] and report['source_files_unchanged']
        report['completed_at'] = datetime.now(timezone.utc).isoformat()
        for name,value in (('package.json',package),('request-body.json',body),('synthetic-selection.json',
            {'synthetic_selection':True,'model_called':False,'scope':'Fabricated fact-ID selection on real retained package, NOT runtime acceptance.','resolved_contract_output':selection}),
            ('verification.json',report)):
            if value is not None:
                path = output/name
                path.write_text(json.dumps(value,ensure_ascii=False,allow_nan=False,indent=2)+'\n',encoding='utf-8')
                if os.name != 'nt':
                    path.chmod(0o600)
    print(json.dumps({'passed':report['passed'],'groups':len(groups),'model_inference':False,
        'synthetic_selection':True,'evidence':str(output/'verification.json')}),flush=True)
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
