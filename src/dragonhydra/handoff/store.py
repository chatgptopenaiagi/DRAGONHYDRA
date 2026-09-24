from contextlib import contextmanager
import json
from uuid import uuid4
from ..config import PROJECT_ROOT
from ..storage.sqlserver import load_odbc,local_connection_options,odbc_value
from ..storage.sqlserver_config import load_sqlserver_settings
from ..storage.intelligence import maria_connection
from ..storage.router import StorageRouter,DataClass
from ..web.provenance import encode,digest
from ..web.contracts import utcnow,PipelineError

TABLES=('HandoffEnvelope','Source','Artifact','Observation','ProcessingReceipt')


@contextmanager
def connection(read=False):
    role='read' if read else 'ingest'
    cfg=load_sqlserver_settings();driver=load_odbc(cfg)
    secret=json.loads((PROJECT_ROOT/f'runtime/secrets/bridge-sql-{role}.local.json').read_text())
    expected='dragonhydra_bridge_read_sqlserver' if read else 'dragonhydra_ingest_sqlserver'
    if secret['username']!=expected:raise PipelineError('IDENTITY_MISMATCH')
    conn=None
    try:
        conn=driver.connect(local_connection_options(cfg)+f'UID={odbc_value(expected)};PWD={odbc_value(secret["password"])};',timeout=5,autocommit=False)
        conn.timeout=10
        yield conn
    except driver.Error:
        raise PipelineError('BRIDGE_SQL_ERROR') from None
    finally:
        if conn:conn.close()


class BridgeStore:
    def ingest(self,validated):
        assert StorageRouter().route(DataClass.STRUCTURED_INTELLIGENCE)=='sqlserver'
        e=validated.envelope;hid=e['handoff_id'];now=utcnow();counts={t:0 for t in TABLES}
        with connection() as c:
            cur=c.cursor()
            row=cur.execute('SELECT manifest_sha256 FROM dragonhydra.HandoffEnvelope WITH(UPDLOCK,HOLDLOCK) WHERE handoff_id=?',hid).fetchone()
            if row:
                if row[0]!=validated.manifest_sha256:raise PipelineError('HANDOFF_ID_COLLISION')
                c.rollback();return counts,True
            cur.execute('INSERT INTO dragonhydra.HandoffEnvelope(handoff_id,manifest_sha256,producer,provenance,status,created_at,ingested_at,payload) VALUES(?,?,?,?,?,?,?,?)',
                        hid,validated.manifest_sha256,e['producer'],validated.provenance,e['status'],e['created_at'],now,encode(e).decode())
            counts['HandoffEnvelope']=1
            for source in e['sources']:
                cur.execute('INSERT INTO dragonhydra.Source(source_id,handoff_id,observed_at,payload_hash,payload) VALUES(?,?,?,?,?)',
                            source['source_id'],hid,source['observed_at'],digest(encode(source)),encode(source).decode())
                counts['Source']+=1
            for artifact in e['artifacts']:
                cur.execute('INSERT INTO dragonhydra.Artifact(artifact_id,handoff_id,sha256,relative_path,size_bytes,media_type,downloaded_at) VALUES(?,?,?,?,?,?,?)',
                            uuid4().hex,hid,artifact['sha256'],artifact['relative_path'],artifact['size_bytes'],artifact['media_type'],artifact['downloaded_at'])
                counts['Artifact']+=1
            for record,payload_hash in zip(validated.normalized,validated.normalized_hashes):
                key=digest(encode([record[k] for k in ('source_id','observation_type','entity_type','entity_name','unit','synthetic')]))
                prior=cur.execute('SELECT TOP(1) observation_id FROM dragonhydra.Observation WITH(UPDLOCK,HOLDLOCK) WHERE natural_key=? AND observed_at<=? ORDER BY observed_at DESC,ingested_at DESC',key,record['observed_at']).fetchone()
                oid=uuid4().hex
                # Payload hash describes normalization, not the later DB-assigned ingestion metadata.
                cur.execute('INSERT INTO dragonhydra.Observation(observation_id,source_id,handoff_id,natural_key,observed_at,effective_at,available_at,ingested_at,payload_hash,confidence,supersedes_id,synthetic,payload) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',
                            oid,record['source_id'],hid,key,record['observed_at'],record['effective_at'],record['available_at'],now,payload_hash,
                            record['confidence'],prior[0] if prior else None,record['synthetic'],encode(record).decode())
                counts['Observation']+=1
            ingested={'handoff_id':hid,'manifest_sha256':validated.manifest_sha256,'phase':'SQL_COMMITTED',
                      'processed_at':now,'normalized_payload_hashes':validated.normalized_hashes,'sql_rows_inserted':dict(counts)}
            cur.execute('INSERT INTO dragonhydra.ProcessingReceipt(receipt_id,handoff_id,phase,processed_at,payload) VALUES(?,?,?,?,?)',
                        uuid4().hex,hid,'SQL_COMMITTED',now,encode(ingested).decode())
            counts['ProcessingReceipt']=1
            c.commit()
        return counts,False

    def final_receipt(self,receipt):
        with connection() as c:
            c.cursor().execute('INSERT INTO dragonhydra.ProcessingReceipt(receipt_id,handoff_id,phase,processed_at,payload) VALUES(?,?,?,?,?)',
                               receipt['attempt_id'],receipt['handoff_id'],'FINAL',receipt['processed_at'],encode(receipt).decode())
            c.commit()

    def summary(self):
        with connection(read=True) as c:
            cur=c.cursor()
            count=cur.execute('SELECT COUNT(*) FROM dragonhydra.Observation').fetchone()[0]
            source_count=cur.execute('SELECT COUNT(DISTINCT source_id) FROM dragonhydra.Source').fetchone()[0]
            row=cur.execute('SELECT TOP(1) handoff_id,producer,provenance,status,CONVERT(nvarchar(40),ingested_at,127),payload FROM dragonhydra.HandoffEnvelope ORDER BY ingested_at DESC').fetchone()
            last_observation=cur.execute('SELECT CONVERT(nvarchar(40),MAX(observed_at),127) FROM dragonhydra.Observation').fetchone()[0]
        envelope=json.loads(row[5]) if row else {}
        return {'generated_at':utcnow(),'source_count':source_count,'observation_count':count,
                'last_handoff_id':row[0] if row else None,'last_source':envelope.get('sources',[{}])[-1].get('source_id'),
                'last_observation_at':str(last_observation) if last_observation else None,
                'last_processing_time':str(row[4]) if row else None,'provenance':row[2] if row else None,
                'producer':row[1] if row else None,'pipeline_status':row[3] if row else 'NO_HANDOFF',
                'sqlserver_status':'HEALTHY','mariadb_status':'HEALTHY'}

    def as_of(self,target):
        from ..web.contracts import timestamp
        timestamp(target)
        with connection(read=True) as c:
            rows=c.cursor().execute('SELECT TOP(100) payload,CONVERT(nvarchar(40),ingested_at,127) FROM dragonhydra.Observation WHERE available_at<=? AND observed_at<=? AND ingested_at<=? ORDER BY ingested_at',target,target,target).fetchall()
        return [dict(json.loads(r[0]),ingested_at=str(r[1])) for r in rows]


def cache_summary(summary):
    assert StorageRouter().route(DataClass.CACHE)=='mariadb'
    with maria_connection() as c:
        c.cursor().execute('INSERT INTO presentation_cache(cache_key,payload) VALUES(%s,%s) ON DUPLICATE KEY UPDATE payload=VALUES(payload),updated_at=CURRENT_TIMESTAMP',
                           ('desktop_cli_bridge',encode(summary).decode()))
        c.commit()
    return 1
