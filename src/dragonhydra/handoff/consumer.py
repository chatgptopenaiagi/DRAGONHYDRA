"""Bounded one-shot claiming, idempotent SQL ingestion, independent cache publication."""
from pathlib import Path
import json,sys,time
from uuid import UUID,uuid4
from .contracts import MAX_MANIFEST_BYTES
from .validator import validate
from .security import SecurityError,scan_secrets,artifact_path
from .receipts import new_receipt,write_receipt
from .store import BridgeStore,cache_summary
from ..config import PROJECT_ROOT
from ..web.provenance import digest,exclusive_json
from ..web.contracts import PipelineError,utcnow
from ..web.bridge import bridge_event

REALM=('browser_inbox','browser_downloads','browser_notes','processing','processed','failed','receipts','cli_outbox','schemas')


def ensure_realm(root):
    for name in REALM:(root/'runtime/handoff'/name).mkdir(parents=True,exist_ok=True)


def stable_bytes(path,interval=0.2):
    if path.is_symlink() or (hasattr(path,'is_junction') and path.is_junction()):raise SecurityError('REPARSE_POINT_REJECTED')
    before=path.stat();time.sleep(interval);after=path.stat()
    if (before.st_size,before.st_mtime_ns)!=(after.st_size,after.st_mtime_ns):raise PipelineError('UNSTABLE_FILE')
    with path.open('rb') as stream:data=stream.read(MAX_MANIFEST_BYTES+1)
    final=path.stat()
    if (after.st_size,after.st_mtime_ns)!=(final.st_size,final.st_mtime_ns):raise PipelineError('UNSTABLE_FILE')
    if len(data)>MAX_MANIFEST_BYTES:raise PipelineError('OVERSIZED_MANIFEST')
    return data


def rejected_count(root):
    ids=set()
    for p in (root/'runtime/handoff/receipts').glob('*.receipt.json'):
        r=json.loads(p.read_text())
        if r['validation_result']=='REJECT':ids.add(r['handoff_id'])
    return len(ids)


def refresh_summary(root,receipt=None):
    summary=BridgeStore().summary()
    if receipt:
        summary.update(consumer_status=receipt['status'],last_attempt_handoff_id=receipt['handoff_id'],
                       last_processing_time=receipt['processed_at'],last_attempt_provenance=receipt['provenance'])
    else:summary['consumer_status']='IDLE'
    summary['rejected_handoffs_count']=rejected_count(root)+(1 if receipt and receipt['validation_result']=='REJECT' and not list((root/'runtime/handoff/receipts').glob(receipt['handoff_id']+'*.receipt.json')) else 0)
    from ..web.bridge import bridge_status
    summary['desktop_handoff_status']=bridge_status(root)['desktop_result']
    summary['bridge_state']=bridge_status(root)['state']
    cache_summary(summary)
    # Preserve the old dashboard DTO and its independently derived bridge status.
    from ..web.pipeline import build_summary
    build_summary(root)
    return summary


def consume_claim(claim,original_name,root=PROJECT_ROOT):
    from ..storage.router import StorageRouter
    assert StorageRouter().handoff_owner('HANDOFF_RAW')=='filesystem'
    cp=root/'runtime/checkpoints'/('desktop-cli-bridge-attempt-'+uuid4().hex);cp.mkdir(parents=True)
    fallback=original_name.removesuffix('.handoff.json')
    try:hid=str(UUID(fallback))
    except ValueError:hid=str(uuid4())
    raw=b'';validated=None;committed=False
    receipt=new_receipt(hid,None,cp)
    try:
        raw=stable_bytes(claim,0)
        receipt['manifest_sha256']=digest(raw)
        scan_secrets(raw)
        if not original_name.endswith('.handoff.json'):raise PipelineError('UNEXPECTED_FILE_TYPE')
        validated=validate(raw,root)
        e=validated.envelope
        if e['handoff_id']!=fallback:raise PipelineError('FILENAME_ID_MISMATCH')
        receipt.update(handoff_id=e['handoff_id'],provenance=validated.provenance,
                       normalized_payload_hashes=list(validated.normalized_hashes),artifact_hashes=[a['sha256'] for a in e['artifacts']])
        with (cp/'handoff.json').open('xb') as stream:stream.write(raw)
        for a,data in zip(e['artifacts'],validated.artifact_bytes):
            archive=cp/'artifacts'/a['sha256'];archive.parent.mkdir(exist_ok=True)
            with archive.open('xb') as stream:stream.write(data)
        origin={'codex-desktop':'DESKTOP_BROWSER','human-browser':'MANUAL','python-fetch':'CLI_FETCH','test-fixture':'SYNTHETIC'}[e['producer']]
        bridge_event(root,'PROCESSING',origin,e['handoff_id'])
        inserted,replay=BridgeStore().ingest(validated);committed=True
        receipt.update(validation_result='ACCEPT',sql_server_rows_inserted=inserted,idempotent_replay=replay,
                       status='BLOCKED' if e['status']=='BLOCKED' else 'DUPLICATE' if replay else 'PROCESSED',
                       processed_at=utcnow(),sql_committed=True)
        if e['status']=='BLOCKED':receipt['warnings'].append('SOURCE_BLOCKED_EVIDENCE_ONLY')
        if e['producer']=='codex-desktop' and e['status']=='SUCCESS':
            bridge_event(root,'DESKTOP_CONFIRMED',origin,e['handoff_id'],desktop_evidence=str(cp/'handoff.json'))
        bridge_event(root,'BLOCKED' if e['status']=='BLOCKED' else 'PROCESSED',origin,e['handoff_id'],receipt_path=str(root/'runtime/handoff/receipts'/f'{hid}.receipt.json'))
        summary=refresh_summary(root,receipt);receipt['mariadb_rows_updated']=2
        exclusive_json(cp/'summary.json',summary)
        receipt['processed_at']=utcnow()
        receipt['sql_server_rows_inserted']['ProcessingReceipt']+=1
        try:BridgeStore().final_receipt(receipt)
        except Exception:
            receipt['sql_server_rows_inserted']['ProcessingReceipt']-=1
            raise
        destination=root/'runtime/handoff/processed'/f'{hid}.{receipt["attempt_id"]}.handoff.json'
        claim.rename(destination)
    except Exception as error:
        reason=str(error) if isinstance(error,PipelineError) else type(error).__name__
        receipt.update(status='FAILED',reason=reason,processed_at=utcnow(),sql_committed=committed)
        if not committed:receipt.update(validation_result='REJECT',rejected_records=len(validated.normalized) if validated else 1)
        else:receipt['warnings'].append('SQL_COMMITTED_REPLAY_SAFE_CACHE_OR_RECEIPT_FAILURE')
        destination=root/'runtime/handoff/failed'/f'{hid}.{receipt["attempt_id"]}.handoff.json'
        if isinstance(error,SecurityError) and reason in ('SECRET_LIKE_CONTENT','FORBIDDEN_FIELD'):
            # Preserve suspected secrets only in the pre-existing protected secret realm.
            quarantine=root/'runtime/secrets/handoff-quarantine'/receipt['attempt_id'];quarantine.mkdir(parents=True)
            claim.rename(quarantine/'manifest.quarantined')
            try:
                parsed=json.loads(raw)
                for a in parsed.get('artifacts',[]):
                    p=artifact_path(root,a['relative_path'])
                    if p.is_file():
                        with p.open('rb') as stream:content=stream.read(5_000_001)
                        try:scan_secrets(content)
                        except SecurityError:p.rename(quarantine/(uuid4().hex+'.quarantined'))
            except (ValueError,KeyError,TypeError,OSError):pass
            exclusive_json(destination,{'handoff_id':hid,'status':'REJECTED','reason':reason,'raw_content':'PROTECTED_QUARANTINE'})
        elif claim.exists():claim.rename(destination)
        bridge_event(root,'FAILED','NONE',hid)
        try:refresh_summary(root,receipt);receipt['mariadb_rows_updated']=2
        except Exception:receipt['warnings'].append('CACHE_REFRESH_FAILED')
    path=write_receipt(root,receipt)
    return dict(receipt,receipt_path=str(path))


def consume_once(root=PROJECT_ROOT,limit=10):
    if sys.version_info[:2]!=(3,14):raise RuntimeError('Python 3.14 required')
    if type(limit) is not int or not 1<=limit<=25:raise ValueError('Bounded batch required')
    ensure_realm(root);lock=root/'runtime/handoff/processing/consumer.lock'
    with lock.open('x') as stream:stream.write(utcnow())
    results=[]
    try:
        candidates=[]
        for p in sorted((root/'runtime/handoff/browser_inbox').iterdir()):
            if not p.is_file() or p.suffix=='.tmp':continue
            if p.suffix=='.json' and not p.name.endswith('.handoff.json'):
                # Recognize the pre-existing v0 manifests; their separate processor owns them.
                try:
                    with p.open('rb') as stream:old=json.loads(stream.read(MAX_MANIFEST_BYTES+1))
                    if isinstance(old,dict) and {'handoff_id','download_path','processing_status','capture_method'}<=set(old):continue
                except (ValueError,OSError):pass
            candidates.append(p)
            if len(candidates)==limit:break
        for path in candidates:
            try:stable_bytes(path)
            except PipelineError as error:
                if str(error)=='UNSTABLE_FILE':
                    results.append({'status':'DEFERRED','reason':'UNSTABLE_FILE'});continue
                # Stable oversized/reparse input still gets a rejection receipt after claim.
            claim=root/'runtime/handoff/processing'/(uuid4().hex+'.handoff.json')
            try:path.rename(claim)
            except FileNotFoundError:continue
            results.append(consume_claim(claim,path.name,root))
        return results
    finally:lock.unlink()


def main(argv=None):
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['consume']);parser.add_argument('--once',action='store_true',required=True)
    parser.add_argument('--limit',type=int,default=10)
    args=parser.parse_args(argv)
    try:
        results=consume_once(limit=args.limit)
        print(json.dumps(results,indent=2))
        return 1 if any(r['status']=='FAILED' for r in results) else 0
    except Exception as error:
        print(json.dumps({'status':'FAILED','reason':str(error) if isinstance(error,PipelineError) else type(error).__name__}))
        return 1


if __name__=='__main__':raise SystemExit(main())
