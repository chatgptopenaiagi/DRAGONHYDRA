"""One-time admin provisioning; preserves all existing identities and tables."""
import secrets,json
from dragonhydra.config import PROJECT_ROOT
from dragonhydra.storage.sqlserver import load_odbc,local_connection_options
from dragonhydra.storage.sqlserver_config import load_sqlserver_settings
from dragonhydra.handoff.store import TABLES
from dragonhydra.web.provenance import exclusive_json


def main():
    cfg=load_sqlserver_settings();driver=load_odbc(cfg)
    paths=[PROJECT_ROOT/f'runtime/secrets/bridge-sql-{r}.local.json' for r in ('ingest','read')]
    if any(p.exists() for p in paths):raise RuntimeError('COLLISION')
    with driver.connect(local_connection_options(cfg)+'Trusted_Connection=yes;',timeout=5,autocommit=False) as c:
        cur=c.cursor()
        if any(cur.execute('SELECT OBJECT_ID(?)','dragonhydra.'+t).fetchone()[0] for t in TABLES):raise RuntimeError('TABLE_COLLISION')
        cur.execute('''CREATE TABLE dragonhydra.HandoffEnvelope(handoff_id char(36) NOT NULL PRIMARY KEY,manifest_sha256 char(64) NOT NULL,
          producer nvarchar(32) NOT NULL,provenance nvarchar(32) NOT NULL,status nvarchar(32) NOT NULL,created_at datetimeoffset NOT NULL,
          ingested_at datetimeoffset NOT NULL,payload nvarchar(max) NOT NULL CHECK(ISJSON(payload)=1))''')
        cur.execute('''CREATE TABLE dragonhydra.Source(source_id nvarchar(80) NOT NULL,handoff_id char(36) NOT NULL REFERENCES dragonhydra.HandoffEnvelope(handoff_id),
          observed_at datetimeoffset NOT NULL,payload_hash char(64) NOT NULL,payload nvarchar(max) NOT NULL CHECK(ISJSON(payload)=1),PRIMARY KEY(source_id,handoff_id))''')
        cur.execute('''CREATE TABLE dragonhydra.Artifact(artifact_id char(32) NOT NULL PRIMARY KEY,handoff_id char(36) NOT NULL REFERENCES dragonhydra.HandoffEnvelope(handoff_id),
          sha256 char(64) NOT NULL,relative_path nvarchar(300) NOT NULL,size_bytes int NOT NULL CHECK(size_bytes BETWEEN 0 AND 5000000),
          media_type nvarchar(80) NOT NULL,downloaded_at datetimeoffset NOT NULL,UNIQUE(handoff_id,sha256),UNIQUE(handoff_id,relative_path))''')
        cur.execute('''CREATE TABLE dragonhydra.Observation(observation_id char(32) NOT NULL PRIMARY KEY,source_id nvarchar(80) NOT NULL,handoff_id char(36) NOT NULL,
          natural_key char(64) NOT NULL,observed_at datetimeoffset NOT NULL,effective_at datetimeoffset NULL,available_at datetimeoffset NOT NULL,
          ingested_at datetimeoffset NOT NULL,payload_hash char(64) NOT NULL,confidence float NOT NULL CHECK(confidence BETWEEN 0 AND 1),
          supersedes_id char(32) NULL REFERENCES dragonhydra.Observation(observation_id),synthetic bit NOT NULL,
          payload nvarchar(max) NOT NULL CHECK(ISJSON(payload)=1),UNIQUE(handoff_id,payload_hash),
          FOREIGN KEY(source_id,handoff_id) REFERENCES dragonhydra.Source(source_id,handoff_id),CHECK(observed_at<=available_at AND available_at<=ingested_at))''')
        cur.execute('CREATE INDEX IX_BridgeObservationKey ON dragonhydra.Observation(natural_key,observed_at)')
        cur.execute('''CREATE TABLE dragonhydra.ProcessingReceipt(receipt_id char(32) NOT NULL PRIMARY KEY,handoff_id char(36) NOT NULL REFERENCES dragonhydra.HandoffEnvelope(handoff_id),
          phase nvarchar(32) NOT NULL,processed_at datetimeoffset NOT NULL,payload nvarchar(max) NOT NULL CHECK(ISJSON(payload)=1))''')
        for role,path in zip(('ingest','read'),paths):
            username='dragonhydra_ingest_sqlserver' if role=='ingest' else 'dragonhydra_bridge_read_sqlserver'
            password='Aa9!'+secrets.token_urlsafe(36)
            exclusive_json(path,{'username':username,'password':password})
            cur.execute(f"CREATE LOGIN [{username}] WITH PASSWORD=N'{password}',CHECK_POLICY=ON,CHECK_EXPIRATION=OFF,DEFAULT_DATABASE=[DRAGONHYDRA_LAB]")
            cur.execute(f'CREATE USER [{username}] FOR LOGIN [{username}] WITH DEFAULT_SCHEMA=dragonhydra')
            cur.execute(f'GRANT CONNECT TO [{username}]')
            for table in TABLES:cur.execute(f'GRANT SELECT{",INSERT" if role=="ingest" else ""} ON OBJECT::dragonhydra.{table} TO [{username}]')
        c.commit()
    print('Created five bridge tables and two bounded SQL identities; existing grants unchanged.')


if __name__=='__main__':
    try:main()
    except Exception as error:
        print(json.dumps({'status':'FAILED','error_type':type(error).__name__,'action':'Inspect partial state; do not reset or drop objects'}))
        raise SystemExit(1) from None
