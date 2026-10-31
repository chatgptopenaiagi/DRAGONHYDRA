"""Parse retained public bytes with the actual R7 package, without Internet.

This reuses adapter.fetch, Document, Store validation/ingestion and Product
projections. The only transport implementation returns exact saved acquisitions;
no parser or sports calculation is duplicated. A new private SQLite database is
used. Receipt clocks remain historical; replay/persistence times are separate.
"""
from __future__ import annotations

import argparse
from collections import Counter
from contextlib import ExitStack, closing
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import socket
import sqlite3
import sys
import time
import traceback
from unittest.mock import patch
import urllib.request
from urllib.parse import parse_qsl, urlsplit

ROOT = Path(__file__).resolve().parents[2]
BOUNDARY = ROOT/'build/linux/native-kernel-20261031/provider-replay-7'
PREFIX = ROOT/'build/linux/native-kernel-20261031/acceptance-7/extracted/opt/dragonhydra/api'
RETAINED = ROOT/'runtime/scratch/provenance-retained-20261031-r3'
OLD_PROOF = ROOT/'build/connections/evidence/provenance-retained-20261031-r3/verification.json'
EXPECTED = {'football-data-couk':380,'statsbomb':64,'nflverse':285,'moneypuck':1394,'cricsheet':17}
MODE = 'retained_evidence_not_fresh_http'
EFFECTIVE = '4a2b97baec4fc278bc405a99a1d970f66e030be77b63d5f043f0faf295b39bc0'


def stamp():
    return datetime.now(timezone.utc).isoformat()


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work',type=Path,default=BOUNDARY/'run-r1')
    args = parser.parse_args()
    work=args.work.resolve()
    if (platform.system()!='Linux' or sys.version_info[:2]!=(3,14) or not sys.flags.isolated
            or not sys.flags.no_site or not work.is_relative_to(BOUNDARY) or work==BOUNDARY or work.exists()):
        parser.error('Run Linux CPython3.14 with -I -S -B and a fresh owned replay evidence directory.')
    work.mkdir(parents=True)
    started=time.monotonic()
    report={'schema_version':1,'mode':MODE,'analysis_mode':'reconstructed_historical_research',
            'started_at':stamp(),'passed':False,'fresh_http':False,'fresh_remote_acquisitions_created':False,
            'operational_database_modified':False,'host_unit_modified':False,'network_calls_attempted':0,
            'scope':'Actual R7 packaged adapters parse retained public evidence into fresh private SQLite; no fresh retrieval/live-source/native-service claim.',
            'capture_policy':'Original retained acquisition IDs, UTC capture clocks, URLs and exact payload hashes retained. Replay and persistence acknowledgements are current and separate.',
            'checks':[],'providers':[],'source_inputs':[]}
    report['harness_sha256']=digest(__file__)
    source_hashes={}
    package_hashes={}
    def check(name,**details):
        report['checks'].append({'name':name,'passed':True,**details})
        print(json.dumps({'passed':name,**details}),flush=True)
    def deny_network(*args,**kwargs):
        report['network_calls_attempted']+=1
        raise AssertionError('NETWORK_FORBIDDEN_IN_RETAINED_REPLAY')
    try:
        for key in tuple(os.environ):
            if key.startswith('DRAGONHYDRA_') or key in ('PYTHONPATH','PYTHONHOME','VIRTUAL_ENV','CONDA_PREFIX'):
                os.environ.pop(key,None)
        os.environ['PYTHONTZPATH']=''
        identity=json.loads((PREFIX/'BUILD-IDENTITY.json').read_text())
        assert identity['source_content_sha256']==EFFECTIVE
        payload=json.loads((ROOT/'build/linux/native-kernel-20261031/build-7/PAYLOAD-MANIFEST.json').read_text())['files']
        extracted=PREFIX.parents[2]
        for item in payload:
            path=extracted/item['path']
            assert not path.is_symlink() and path.is_file() and path.stat().st_size==item['bytes'] and digest(path)==item['sha256'],'PACKAGED_INPUT_HASH_MISMATCH'
            package_hashes[path]=item['sha256']
        sys.path.insert(0,str(PREFIX/'site-packages'))
        from dragonhydra.connectors import adapter,registry
        from dragonhydra.connectors.core import Document,redact_url,validate_url
        from dragonhydra.product import Product,identity as entity_id
        from dragonhydra import local_ai,local_ai_service
        from dragonhydra.local_ai_settings import Settings
        site=PREFIX/'site-packages'
        for name,module in tuple(sys.modules.items()):
            if name=='dragonhydra' or name.startswith('dragonhydra.'):
                assert Path(module.__file__).resolve().is_relative_to(site),'CHECKOUT_MODULE_LEAK'
        report['package']={'debian_version':identity['debian_version'],'effective_source_content_sha256':EFFECTIVE,
                           'application_snapshot_sha256':identity['application_snapshot_sha256'],
                           'module_origin':'acceptance-7/extracted/opt/dragonhydra/api/site-packages',
                           'verified_payload_files':len(package_hashes)}
        check('Exact R7 package payload and isolated installed-module binding verified',files=len(package_hashes))
        old=json.loads(OLD_PROOF.read_text())
        assert old['passed'] is True and old['before']['counts']==EXPECTED and old['http_calls_attempted']==0
        receipts_path=RETAINED/'RETAINED-ACQUISITIONS.json'
        receipt_body=receipts_path.read_bytes()
        source_hashes[receipts_path]=hashlib.sha256(receipt_body).hexdigest()
        source_hashes[OLD_PROOF]=digest(OLD_PROOF)
        receipts=json.loads(receipt_body)
        assert len(receipts)==6 and {r['provider'] for r in receipts}==set(EXPECTED)
        bodies={}
        for receipt in receipts:
            assert receipt['adapter_version']==receipt['provider']+'/1' and receipt['http_status']==200
            reference=receipt['raw_reference']
            assert reference==Path(reference).name and reference==receipt['sha256']+'.payload'
            source=RETAINED/'state/raw/connectors'/reference
            assert source.is_file() and not source.is_symlink() and source.resolve().is_relative_to(RETAINED)
            body=source.read_bytes()
            assert len(body)==receipt['bytes'] and hashlib.sha256(body).hexdigest()==receipt['sha256'],'RETAINED_PAYLOAD_HASH_MISMATCH'
            for field in ('original_url','resolved_url'):
                url=receipt[field];validate_url(url);parsed=urlsplit(url)
                assert not parsed.username and not parsed.password and redact_url(url)==url
                assert not {key.lower() for key,_ in parse_qsl(parsed.query)} & {'key','api_key','apikey','api_token','access_token','token'}
            assert not re.search(rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|sk-proj-[A-Za-z0-9_-]{15,}',body)
            source_hashes[source]=receipt['sha256'];bodies[receipt['id']]=body
            report['source_inputs'].append({**receipt,'source_path':source.relative_to(ROOT).as_posix()})
        check('Six retained public payloads/receipts verified before use; URLs and payloads pass targeted secret checks',documents=6,bytes=sum(len(b) for b in bodies.values()))
        state=work/'state'
        state.mkdir()
        raw=state/'raw/connectors';raw.mkdir(parents=True)
        docs={}
        for receipt in receipts:
            body=bodies[receipt['id']]
            target=raw/receipt['raw_reference'];target.write_bytes(body)
            docs[receipt['id']]=Document(receipt['original_url'],receipt['resolved_url'],body,receipt['captured_at'],
                receipt['sha256'],receipt['content_type'],receipt['id'],receipt['raw_reference'],receipt['http_status'])
        with ExitStack() as guards:
            for owner,name in ((urllib.request,'urlopen'),(urllib.request.OpenerDirector,'open'),
                               (socket,'create_connection'),(socket.socket,'connect'),(socket.socket,'connect_ex')):
                guards.enter_context(patch.object(owner,name,deny_network))
            product=Product(state)
            store=product.connector_store
            for receipt in receipts:
                store.receipt(receipt['provider'],docs[receipt['id']])
            all_records={}
            class RetainedTransport:
                def __init__(self,provider):
                    self.provider=provider;self.documents=[];self.calls=[]
                def get(self,url,headers=None):
                    validate_url(url)
                    # Headers here are public content negotiation only. No key
                    # is supplied to these public adapters.
                    assert not any(key.lower() in ('authorization','x-auth-token','x-apisports-key') for key in (headers or {}))
                    choices=[r for r in receipts if r['provider']==self.provider and url in (r['original_url'],r['resolved_url'])]
                    assert len(choices)==1,'RETAINED_ENDPOINT_NOT_AVAILABLE'
                    doc=docs[choices[0]['id']]
                    self.documents.append(doc);self.calls.append({'url':url,'acquisition_id':doc.acquisition_id})
                    return doc
            for provider,count in EXPECTED.items():
                tick=time.monotonic();transport=RetainedTransport(provider)
                records=adapter(provider).fetch(provider,registry()[provider]['defaults'],None,transport,lambda:None)
                all_records[provider]=records
                assert len(records)==count and len({r['source_record_id'] for r in records})==count,'PARSED_COVERAGE_MISMATCH'
                validation=store.validate_batch(provider,records,transport.documents)
                assert validation['invalid_rows']==0 and len(validation['valid_records'])==count
                first=store.ingest(provider,records,transport.documents)
                assert first['inserted']==count and first['unchanged']==0 and first['quarantined']==0 and first['record_count']==count
                repeated=store.ingest(provider,records,transport.documents)
                assert repeated['inserted']==0 and repeated['unchanged']==count and repeated['quarantined']==0 and repeated['record_count']==count
                page=store.page(provider,limit=1); assert page['total']==count
                selected=page['items'][0]; evidence=store.evidence(selected['id'])
                assert evidence['source_documents'] and all(d['status']=='bound' for d in evidence['source_documents'])
                ids=[]
                for doc in transport.documents:
                    metadata=store.acquisition(provider,doc.acquisition_id)
                    assert metadata['captured_at']==doc.captured_at and metadata['sha256']==doc.sha256 and metadata['original_url']==doc.url and metadata['resolved_url']==doc.resolved_url
                    ids.append(doc.acquisition_id)
                entry={'provider':provider,'mode':MODE,'original_verified_count':old['before']['counts'][provider],
                       'parsed_records':len(records),'first_ingestion':first,'repeat_ingestion':repeated,
                       'record_kind_counts':dict(Counter(r['status'] for r in records)),
                       'known_source_record_id':selected['source_record_id'],'observation_evidence_id':selected['id'],
                       'queryable_acquisition_ids':ids,'transport_logical_reads':transport.calls,
                       'elapsed_seconds':round(time.monotonic()-tick,3)}
                if provider=='statsbomb':
                    catalogs={r['attributes']['catalog_sha256'] for r in records}
                    missing=store.validate_batch(provider,records,[d for d in transport.documents if d.sha256 not in catalogs])
                    assert missing['invalid_rows']==count and missing['normalization_errors']=={'MISSING_ACQUISITION':count}
                    entry['missing_catalog_rejected_rows']=count
                report['providers'].append(entry)
                check('Packaged adapter parses/stores retained '+provider+' with provenance and idempotent repeat',provider=provider,parsed=count,inserted=first['inserted'],repeat_inserted=repeated['inserted'])
            match=next(r for r in all_records['football-data-couk'] if r.get('odds'))
            mid=entity_id('fixture','football-data-couk',match['source_record_id'])
            odds=product.odds(mid,history=True)
            primary=next(d for d in docs.values() if d.sha256==match['source_document_sha256'])
            assert odds['items'] and odds['axis']=='archive_phase'
            for quote in odds['items']:
                assert quote['provenance_status']=='bound' and quote['acquisition_id']==primary.acquisition_id and quote['captured_at']==primary.captured_at
                assert quote['source_document_sha256']==primary.sha256 and quote['source_url']==primary.url and quote['quote_at'] is None
            check('Archive quote projection retains bound historical acquisition and untimestamped endpoint semantics',match_id=mid,quotes=len(odds['items']),axis=odds['axis'],captured_at=primary.captured_at)
            settings=Settings(state).public();assert not settings['configured'] and settings['endpoint']=='' and settings['credential_source']=='none'
            package=local_ai.build_package(product,mid);fallback=local_ai_service.explain(product,package)
            assert fallback['kind']=='deterministic' and fallback['local_ai']['code']=='AI_NOT_CONFIGURED' and fallback['local_ai']['accepted'] is False
            report['local_ai_default']={'settings':settings,'kind':fallback['kind'],'code':fallback['local_ai']['code'],'model_executed':False}
            check('New packaged AI configuration gracefully returns explicitly deterministic cited fallback without a model')
            with closing(product.connect()) as db:
                counts=dict(db.execute('SELECT provider,COUNT(DISTINCT source_record_id) FROM connector_observations GROUP BY provider'))
                acquisitions=db.execute('SELECT COUNT(*) FROM connector_acquisitions').fetchone()[0]
                observations=db.execute('SELECT COUNT(*) FROM connector_observations').fetchone()[0]
                quarantine=db.execute('SELECT COUNT(*) FROM connector_quarantine').fetchone()[0]
                attempts=db.execute('SELECT COUNT(*) FROM connector_attempts').fetchone()[0]
            assert counts==EXPECTED and acquisitions==6 and observations==sum(EXPECTED.values()) and quarantine==attempts==0
            report['stored_counts']={'providers':counts,'observations':observations,'copied_historical_receipts':acquisitions,'quarantine':quarantine,'fresh_sync_attempts':attempts}
            check('SQLite exposes2140 new observations and6 original historical receipts with no false fresh sync attempt',observations=observations,acquisitions=acquisitions)
        assert report['network_calls_attempted']==0
        assert all(digest(path)==expected for path,expected in source_hashes.items()),'RETAINED_INPUT_CHANGED'
        assert all(digest(path)==expected for path,expected in package_hashes.items()),'R7_PACKAGE_INPUT_CHANGED'
        check('Network guards saw zero calls; retained source and all packaged bytes remain unchanged')
        report['passed']=True
    except Exception as error:
        report['error']={'type':type(error).__name__,'message':str(error),'line':traceback.extract_tb(error.__traceback__)[-1].lineno}
        (work/'traceback.log').write_text(traceback.format_exc())
    finally:
        report.update(finished_at=stamp(),elapsed_seconds=round(time.monotonic()-started,3))
        (work/'verification.json').write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n')
        print(json.dumps({'passed':report['passed'],'mode':MODE,'network_calls_attempted':report['network_calls_attempted'],
                          'elapsed_seconds':report['elapsed_seconds'],'error':report.get('error'),
                          'evidence':(work/'verification.json').relative_to(ROOT).as_posix()}),flush=True)
    return 0 if report['passed'] else 1


if __name__=='__main__':
    raise SystemExit(main())
