"""Explicit, one-time administrative migration. Not imported by runtime."""
import json
import secrets
from dragonhydra.config import PROJECT_ROOT, load_settings
from dragonhydra.storage.sqlserver import load_odbc, local_connection_options
from dragonhydra.storage.sqlserver_config import load_sqlserver_settings
from dragonhydra.integration.mariadb_probe import load_driver
from dragonhydra.storage.intelligence import TABLES
from dragonhydra.web.provenance import exclusive_json, checkpoint


def main():
    cfg = load_sqlserver_settings()
    secret_dir = PROJECT_ROOT / 'runtime/secrets'
    if any((secret_dir / f'{name}.local.json').exists() for name in ('web-sql-ingest','web-sql-read','web-maria-ops','web-maria-web')):
        raise RuntimeError('Provision collision: inspect state; do not reset')
    sql = load_odbc(cfg).connect(local_connection_options(cfg)+'Trusted_Connection=yes;', timeout=5, autocommit=False)
    maria = load_driver(load_settings()).connect(host='127.0.0.1', user='root', password='', port=3306, connect_timeout=5)
    try:
        cur = sql.cursor()
        if cur.execute("SELECT SCHEMA_ID('dragonhydra')").fetchone()[0] is not None:
            raise RuntimeError('Schema already exists')
        m = maria.cursor()
        m.execute("SELECT SCHEMA_NAME FROM information_schema.SCHEMATA WHERE SCHEMA_NAME='dragonhydra_web'")
        if m.fetchone():
            raise RuntimeError('Operational database already exists')
        cur.execute('CREATE SCHEMA dragonhydra AUTHORIZATION dbo')
        for table in TABLES:
            cur.execute(f'''CREATE TABLE dragonhydra.{table}(
                record_id char(32) NOT NULL PRIMARY KEY,
                natural_key nvarchar(240) NOT NULL,
                version int NOT NULL CHECK(version>0),
                supersedes_id char(32) NULL REFERENCES dragonhydra.{table}(record_id),
                source_id nvarchar(80) NOT NULL,
                available_at datetimeoffset NOT NULL,
                created_at datetimeoffset NOT NULL,
                dedup_key char(64) NOT NULL UNIQUE,
                payload nvarchar(max) NOT NULL CHECK(ISJSON(payload)=1),
                CONSTRAINT UQ_{table}_version UNIQUE(natural_key,version))''')
        # Typed relational projections preserve the independently versioned source envelopes.
        cur.execute("ALTER TABLE dragonhydra.fixtures ADD fixture_id AS JSON_VALUE(payload,'$.fixture_id'), home_entity_id AS JSON_VALUE(payload,'$.home_entity_id'), away_entity_id AS JSON_VALUE(payload,'$.away_entity_id')")
        cur.execute("ALTER TABLE dragonhydra.odds_observations ADD fixture_id AS JSON_VALUE(payload,'$.fixture_id'), market_key AS JSON_VALUE(payload,'$.market_key'), selection AS JSON_VALUE(payload,'$.selection'), decimal_odds AS TRY_CONVERT(decimal(18,8),JSON_VALUE(payload,'$.decimal_odds'))")
        cur.execute("ALTER TABLE dragonhydra.odds_observations ADD CONSTRAINT CK_valid_odds CHECK(TRY_CONVERT(decimal(18,8),JSON_VALUE(payload,'$.decimal_odds')) IS NOT NULL AND TRY_CONVERT(decimal(18,8),JSON_VALUE(payload,'$.decimal_odds'))>1)")
        for role in ('ingest', 'read'):
            username = f'dragonhydra_{role}'
            password = 'Aa9!' + secrets.token_urlsafe(36)
            exclusive_json(secret_dir / f'web-sql-{role}.local.json', {'username':username,'password':password})
            cur.execute(f"CREATE LOGIN [{username}] WITH PASSWORD=N'{password}',CHECK_POLICY=ON,CHECK_EXPIRATION=OFF,DEFAULT_DATABASE=[DRAGONHYDRA_LAB]")
            cur.execute(f'CREATE USER [{username}] FOR LOGIN [{username}] WITH DEFAULT_SCHEMA=dragonhydra')
            cur.execute(f'GRANT CONNECT TO [{username}]')
            for table in TABLES:
                cur.execute(f'GRANT SELECT{",INSERT" if role == "ingest" else ""} ON OBJECT::dragonhydra.{table} TO [{username}]')
        sql.commit()
        m.execute('CREATE DATABASE dragonhydra_web CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci')
        m.execute('CREATE TABLE dragonhydra_web.job_state(job_id varchar(80) PRIMARY KEY,status varchar(32) NOT NULL,payload longtext NOT NULL CHECK(JSON_VALID(payload)))')
        m.execute('CREATE TABLE dragonhydra_web.presentation_cache(cache_key varchar(80) PRIMARY KEY,payload longtext NOT NULL CHECK(JSON_VALID(payload)),updated_at timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP)')
        m.execute('CREATE TABLE dragonhydra_web.integration_metadata(metadata_key varchar(80) PRIMARY KEY,payload longtext NOT NULL CHECK(JSON_VALID(payload)))')
        for role in ('ops','web'):
            username = f'dragonhydra_{role}'
            password = 'Aa9!' + secrets.token_urlsafe(36)
            exclusive_json(secret_dir / f'web-maria-{role}.local.json', {'username':username,'password':password})
            m.execute(f"CREATE USER '{username}'@'localhost' IDENTIFIED BY %s", (password,))
            tables = ('job_state','presentation_cache','integration_metadata') if role == 'ops' else ('presentation_cache',)
            for table in tables:
                rights = 'SELECT,INSERT,UPDATE' if role == 'ops' else 'SELECT'
                m.execute(f"GRANT {rights} ON dragonhydra_web.{table} TO '{username}'@'localhost'")
        maria.commit()
        checkpoint(PROJECT_ROOT, 'provision', {'sql_tables':list(TABLES), 'maria_tables':['job_state','presentation_cache','integration_metadata'],
                                              'runtime_admin':False,'schema':'dragonhydra','database':'DRAGONHYDRA_LAB'})
        print('Provisioned append-only SQL identities and bounded MariaDB operational/web identities.')
    finally:
        sql.close()
        maria.close()


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(json.dumps({'status':'FAILED','error_type':type(error).__name__,'action':'Inspect partial state; no automatic reset'}))
        raise SystemExit(1) from None
