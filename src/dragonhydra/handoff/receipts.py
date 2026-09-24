from pathlib import Path
from uuid import uuid4
import os,sys
from . import CONSUMER_VERSION
from ..web.contracts import utcnow
from ..web.provenance import exclusive_json,encode


def new_receipt(handoff_id,manifest_hash,checkpoint):
    return {'handoff_id':handoff_id,'attempt_id':uuid4().hex,'manifest_sha256':manifest_hash,'processed_at':utcnow(),
            'python_version':sys.version.split()[0],'consumer_version':CONSUMER_VERSION,'validation_result':'REJECT',
            'sql_server_rows_inserted':{},'mariadb_rows_updated':0,'rejected_records':0,'warnings':[],
            'checkpoint_path':str(checkpoint),'status':'FAILED','provenance':'UNKNOWN','artifact_hashes':[],
            'normalized_payload_hashes':[]}


def write_receipt(root,receipt):
    directory=root/'runtime/handoff/receipts'
    primary=directory/f'{receipt["handoff_id"]}.receipt.json'
    path=primary if not primary.exists() else directory/f'{receipt["handoff_id"]}.{receipt["attempt_id"]}.receipt.json'
    exclusive_json(path,receipt)
    exclusive_json(Path(receipt['checkpoint_path'])/'receipt.json',receipt)
    exclusive_json(root/'runtime/handoff/cli_outbox'/f'{receipt["attempt_id"]}.json',
                   {'handoff_id':receipt['handoff_id'],'status':receipt['status'],'receipt_path':str(path)})
    return path


def atomic_publish(envelope,root):
    from .validator import validate
    raw=encode(envelope);validate(raw,root)
    directory=root/'runtime/handoff/browser_inbox';directory.mkdir(parents=True,exist_ok=True)
    final=directory/f'{envelope["handoff_id"]}.handoff.json'
    temporary=directory/f'{envelope["handoff_id"]}.{uuid4().hex}.tmp'
    with temporary.open('xb') as stream:
        stream.write(raw);stream.flush();os.fsync(stream.fileno())
    # On Windows rename is atomic and refuses an existing destination.
    if final.exists():raise FileExistsError('HANDOFF_ALREADY_PUBLISHED')
    temporary.rename(final)
    return final
