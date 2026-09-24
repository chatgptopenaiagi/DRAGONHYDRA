"""Fixed, parameterized persistence operations. Runtime never uses bootstrap identities."""
from contextlib import contextmanager
import json
from uuid import uuid4
from ..config import PROJECT_ROOT, load_settings
from ..integration.mariadb_probe import load_driver
from .sqlserver import load_odbc, local_connection_options, odbc_value
from .sqlserver_config import load_sqlserver_settings
from .router import StorageRouter, DataClass
from ..web.provenance import encode, digest
from ..web.contracts import utcnow, PipelineError
from ..web.bridge import bridge_status

TABLES = ('sources', 'source_terms', 'web_observations', 'fixtures', 'entities', 'markets',
          'odds_observations', 'scrape_runs', 'processing_runs', 'conflicts', 'handoff_items')


@contextmanager
def sql_connection(role='ingest'):
    if role not in ('ingest', 'read'):
        raise ValueError('Unsupported runtime role')
    cfg = load_sqlserver_settings()
    secret = json.loads((PROJECT_ROOT / f'runtime/secrets/web-sql-{role}.local.json').read_text())
    if secret['username'] != f'dragonhydra_{role}':
        raise RuntimeError('Runtime identity mismatch')
    driver = load_odbc(cfg)
    connection = None
    try:
        connection = driver.connect(local_connection_options(cfg) +
                                    f'UID={odbc_value(secret["username"])};PWD={odbc_value(secret["password"])};',
                                    timeout=5, autocommit=False)
        connection.timeout = 10
        yield connection
    except driver.Error:
        raise PipelineError('SQL_STORAGE_ERROR') from None
    finally:
        if connection:
            connection.close()


@contextmanager
def maria_connection(role='ops'):
    if role not in ('ops', 'web'):
        raise ValueError('Unsupported runtime role')
    secret = json.loads((PROJECT_ROOT / f'runtime/secrets/web-maria-{role}.local.json').read_text())
    if secret['username'] != f'dragonhydra_{role}':
        raise RuntimeError('Runtime identity mismatch')
    driver = load_driver(load_settings())
    connection = None
    try:
        connection = driver.connect(host='127.0.0.1', port=3306, user=secret['username'], password=secret['password'],
                                    database='dragonhydra_web', charset='utf8mb4', connect_timeout=5,
                                    read_timeout=10, write_timeout=10, autocommit=False)
        yield connection
    except driver.MySQLError:
        raise PipelineError('MARIADB_STORAGE_ERROR') from None
    finally:
        if connection:
            connection.close()


class IntelligenceStore:
    def __init__(self):
        assert StorageRouter().route(DataClass.STRUCTURED_INTELLIGENCE) == 'sqlserver'

    def append(self, connection, table, key, payload, source_id, available_at, *, dedup_key=None):
        if table not in TABLES:
            raise ValueError('Unknown fixed operation')
        body = encode(payload).decode('utf-8')
        fingerprint = dedup_key or digest(encode([key, payload]))
        cur = connection.cursor()
        # Serializable key-range lock prevents concurrent duplicate versions.
        cur.execute(f'SELECT record_id FROM dragonhydra.{table} WITH (UPDLOCK,HOLDLOCK) WHERE dedup_key=?', fingerprint)
        existing = cur.fetchone()
        if existing:
            return existing[0], False
        cur.execute(f'SELECT TOP(1) record_id,version FROM dragonhydra.{table} WITH (UPDLOCK,HOLDLOCK) WHERE natural_key=? ORDER BY version DESC', key)
        prior = cur.fetchone()
        record_id = uuid4().hex
        cur.execute(f'INSERT INTO dragonhydra.{table}(record_id,natural_key,version,supersedes_id,source_id,available_at,created_at,dedup_key,payload) VALUES(?,?,?,?,?,?,?,?,?)',
                    record_id, key, prior[1]+1 if prior else 1, prior[0] if prior else None,
                    source_id, available_at, utcnow(), fingerprint, body)
        return record_id, True

    def previous(self, connection, table, key):
        if table not in TABLES:
            raise ValueError('Unknown fixed operation')
        row = connection.cursor().execute(f'SELECT TOP(1) payload FROM dragonhydra.{table} WHERE natural_key=? ORDER BY version DESC', key).fetchone()
        return json.loads(row[0]) if row else None

    def fixtures_as_of(self, target_as_of_at, limit=100):
        from ..web.contracts import timestamp
        timestamp(target_as_of_at)
        if type(limit) is not int or not 1 <= limit <= 500:
            raise ValueError('Bounded replay required')
        with sql_connection('read') as conn:
            rows = conn.cursor().execute('''WITH revisions AS (
                SELECT payload,ROW_NUMBER() OVER(PARTITION BY natural_key ORDER BY version DESC) AS rn
                FROM dragonhydra.fixtures WHERE available_at<=? AND created_at<=?
                AND TRY_CONVERT(datetimeoffset,JSON_VALUE(payload,'$.updated_at'))<=?)
                SELECT TOP(?) payload FROM revisions WHERE rn=1''',
                target_as_of_at,target_as_of_at,target_as_of_at,limit).fetchall()
            return [dict(json.loads(r[0]),target_as_of_at=target_as_of_at) for r in rows]

    def summary(self):
        with sql_connection('read') as conn:
            cur = conn.cursor()
            counts = {}
            for table in ('sources', 'fixtures', 'odds_observations', 'conflicts'):
                cur.execute(f'SELECT COUNT(DISTINCT natural_key) FROM dragonhydra.{table}')
                counts[table] = cur.fetchone()[0]
            cur.execute('SELECT TOP(10) payload FROM dragonhydra.odds_observations ORDER BY created_at DESC')
            odds = [json.loads(r[0]) for r in cur.fetchall()]
            cur.execute('SELECT TOP(5) payload FROM dragonhydra.fixtures ORDER BY created_at DESC')
            fixtures = [json.loads(r[0]) for r in cur.fetchall()]
            cur.execute('SELECT TOP(1) payload FROM dragonhydra.scrape_runs ORDER BY created_at DESC')
            row = cur.fetchone()
            fetch = json.loads(row[0]) if row else None
            cur.execute('SELECT TOP(1) payload FROM dragonhydra.processing_runs ORDER BY created_at DESC')
            row = cur.fetchone()
            processing = json.loads(row[0]) if row else None
        bridge = bridge_status(PROJECT_ROOT)
        return {'counts': counts, 'odds': odds, 'fixtures': fixtures, 'last_fetch': fetch,
                'processing': processing, 'built_at': utcnow(), 'sqlserver': 'healthy',
                'browser_handoff': bridge['state'], 'bridge':bridge, 'cli_processor': 'Python CLI',
                'attribution': 'OpenFootball football.json (CC0-1.0). Synthetic odds are generated locally, not bookmaker quotes.'}


class PresentationStore:
    def save_job(self, job):
        assert StorageRouter().route(DataClass.OPERATIONAL) == 'mariadb'
        with maria_connection() as conn:
            conn.cursor().execute('INSERT INTO job_state(job_id,status,payload) VALUES(%s,%s,%s) ON DUPLICATE KEY UPDATE status=VALUES(status),payload=VALUES(payload)',
                                  (job['job_id'], job['status'], encode(job).decode()))
            conn.commit()

    def cache(self, summary):
        assert StorageRouter().route(DataClass.CACHE) == 'mariadb'
        with maria_connection() as conn:
            summary = dict(summary, mariadb='healthy')
            conn.cursor().execute('INSERT INTO presentation_cache(cache_key,payload) VALUES(%s,%s) ON DUPLICATE KEY UPDATE payload=VALUES(payload),updated_at=CURRENT_TIMESTAMP',
                                  ('intelligence', encode(summary).decode()))
            conn.commit()
        return summary
