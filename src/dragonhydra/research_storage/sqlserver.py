"""Explicit, scoped SQL Server SECONDARY archive; no model/source/job authority.

Importing this module neither imports pyodbc nor opens a connection. Only
initialize() may create a database/schema. Uncertain writes are never retried.
"""
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation, localcontext
import hashlib
import importlib
import json
from pathlib import Path
import re
from uuid import UUID, uuid4

from .base import StorageError, canonical, validate_bundle, utc_now


PROVIDER = 'sqlserver'
PRODUCT = 'dragonhydra.research-archive'
MIGRATION = 'research-archive/1'
SCHEMA_VERSION = 1
SCHEMA = Path(__file__).with_name('schema_sqlserver.sql')
MAX_PAYLOAD = 8 * 1024 * 1024
TABLES = frozenset('owner migrations archives models predictions inputs notes note_audit'.split())
TRIGGERS = frozenset('archives_immutable models_immutable predictions_immutable inputs_immutable '
                    'owner_immutable migrations_immutable note_audit_immutable notes_no_delete notes_audit'.split())


def _error(code, exc=None, *, uncertain=False):
    state = None
    if exc is not None and getattr(exc, 'args', ()):
        candidate = exc.args[0]
        if isinstance(candidate, str) and re.fullmatch(r'[A-Z0-9]{5}', candidate):
            state = candidate
    return StorageError(code, sqlstate=state, uncertain_write=uncertain)


def _close(connection, *, rollback=False):
    """Best-effort disposal must never replace a sanitized result with driver text."""
    okay = True
    if rollback:
        try:
            connection.rollback()
        except Exception:
            okay = False
    try:
        connection.close()
    except Exception:
        okay = False
    return okay


def _text(value, maximum, code):
    if (not isinstance(value, str) or not value.strip() or '\x00' in value
            or len(value.encode('utf-16-le')) // 2 > maximum):
        raise _error(code)
    return value


def _hex(value):
    if not isinstance(value, str) or not re.fullmatch(r'[a-f0-9]{64}', value):
        raise _error('SQLSERVER_INVALID_ARCHIVE_ID')
    return value


def _record_id(value):
    if not isinstance(value, str) or not re.fullmatch(r'(?:[a-z_]+:)?[a-f0-9]{64}', value):
        raise _error('SQLSERVER_INVALID_RECORD_ID')
    return _text(value, 160, 'SQLSERVER_INVALID_RECORD_ID')


def _uuid(value):
    try:
        parsed = UUID(value) if isinstance(value, str) else None
    except (ValueError, AttributeError):
        parsed = None
    if parsed is None or str(parsed) != value:
        raise _error('SQLSERVER_INVALID_NOTE_ID')
    return str(parsed)


def _timestamp(value):
    """UTC SQL literal retaining up to seven decimal places without truncation."""
    if not isinstance(value, str):
        raise _error('SQLSERVER_INVALID_TIMESTAMP')
    match = re.fullmatch(r'(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d)(\.\d{1,7})?(Z|\+00:00)', value)
    if not match:
        raise _error('SQLSERVER_INVALID_TIMESTAMP')
    try:
        datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError:
        raise _error('SQLSERVER_INVALID_TIMESTAMP') from None
    return match[1] + (match[2] or '')


def _clock():
    return _timestamp(utc_now())


def _probability(value):
    # Bind a string and use explicit decimal CAST: no float or ODBC scale inference.
    if not isinstance(value, str) or len(value) > 100:
        raise _error('SQLSERVER_INVALID_PROBABILITY')
    try:
        with localcontext() as context:
            context.prec = 100
            result = Decimal(value)
            if not result.is_finite() or not Decimal(0) <= result <= Decimal(1):
                raise _error('SQLSERVER_INVALID_PROBABILITY')
            exact = result.quantize(Decimal('1e-28'))
            if result != exact:
                raise _error('SQLSERVER_PROBABILITY_PRECISION_LOSS')
            return format(exact, 'f')
    except InvalidOperation:
        raise _error('SQLSERVER_INVALID_PROBABILITY') from None


@dataclass(frozen=True, repr=False)
class SQLServerConfig:
    server: str = 'localhost'
    database: str = 'DRAGONHYDRA_CORE_NEXT_SQL_LAB'
    driver: str = 'ODBC Driver 18 for SQL Server'
    connection_timeout_seconds: int = 5
    query_timeout_seconds: int = 10
    encrypt: bool = True
    trust_server_certificate: bool = False
    authentication: str = 'windows_integrated'

    @classmethod
    def from_dict(cls, value):
        if not isinstance(value, dict) or set(value) - set(cls.__dataclass_fields__):
            raise _error('SQLSERVER_CONFIGURATION_INVALID')
        config = cls(**value)
        server = config.server
        # No ODBC property delimiters/braces; explicit lpc shared-memory is supported.
        if (not isinstance(server, str) or len(server) > 255 or not re.fullmatch(
                r'(?:(?:lpc|tcp):)?[A-Za-z0-9_.-]+(?:\\[A-Za-z0-9_-]+)?(?:,\d{1,5})?', server)):
            raise _error('SQLSERVER_CONFIGURATION_INVALID')
        if ',' in server and not 1 <= int(server.rsplit(',', 1)[1]) <= 65535:
            raise _error('SQLSERVER_CONFIGURATION_INVALID')
        if (not isinstance(config.database, str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,127}', config.database)
                or config.database.lower() in {'master', 'model', 'msdb', 'tempdb'}):
            raise _error('SQLSERVER_CONFIGURATION_INVALID')
        if config.driver != 'ODBC Driver 18 for SQL Server' or config.authentication != 'windows_integrated':
            raise _error('SQLSERVER_CONFIGURATION_INVALID')
        if type(config.encrypt) is not bool or not config.encrypt or type(config.trust_server_certificate) is not bool:
            raise _error('SQLSERVER_CONFIGURATION_INVALID')
        for timeout, maximum in ((config.connection_timeout_seconds, 15), (config.query_timeout_seconds, 30)):
            if type(timeout) is not int or not 1 <= timeout <= maximum:
                raise _error('SQLSERVER_CONFIGURATION_INVALID')
        return config

    def __repr__(self):
        return 'SQLServerConfig(authentication=windows_integrated, encrypt=True)'

    def _connection_string(self, database):
        return (f'DRIVER={{{self.driver}}};SERVER={self.server};DATABASE={database};'
                'Trusted_Connection=yes;Encrypt=yes;'
                f'TrustServerCertificate={"yes" if self.trust_server_certificate else "no"};'
                'APP=DRAGONHYDRA secondary research archive;')


class Repo:
    provider = PROVIDER

    def __init__(self, config, scope):
        if isinstance(config, dict):
            config = SQLServerConfig.from_dict(config)
        elif isinstance(config, SQLServerConfig):
            # Direct dataclass construction must not bypass validation.
            config = SQLServerConfig.from_dict({name: getattr(config, name) for name in config.__dataclass_fields__})
        else:
            raise _error('SQLSERVER_CONFIGURATION_INVALID')
        if not isinstance(scope, str) or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,128}', scope):
            raise _error('SQLSERVER_INVALID_SCOPE')
        self.config, self.scope = config, scope
        self.last_success_at = self.last_error = None

    def _connect(self, *, master=False, autocommit=False):
        try:
            driver = importlib.import_module('pyodbc')
        except ImportError:
            raise _error('SQLSERVER_DRIVER_UNAVAILABLE') from None
        connection = None
        try:
            connection = driver.connect(self.config._connection_string('master' if master else self.config.database),
                timeout=self.config.connection_timeout_seconds, autocommit=autocommit)
            connection.timeout = self.config.query_timeout_seconds
            connection.execute('SET XACT_ABORT ON; SET NOCOUNT ON; SET LOCK_TIMEOUT 3000;')
            return connection
        except Exception as exc:
            if connection is not None:
                _close(connection)
            raise _error('SQLSERVER_CONNECTION_FAILED', exc) from None

    @staticmethod
    def _schema_hash():
        return hashlib.sha256(SCHEMA.read_bytes()).digest()

    def _owned(self, connection):
        present = connection.execute("SELECT OBJECT_ID(N'dbo.dh_research_owner', N'U')").fetchone()
        if not present or present[0] is None:
            raise _error('SQLSERVER_DATABASE_NOT_OWNED')
        owner = connection.execute('SELECT product_id,schema_version,migration_sha256 FROM dbo.dh_research_owner WHERE owner_key=1').fetchone()
        if not owner or owner[0] != PRODUCT or owner[1] != SCHEMA_VERSION:
            raise _error('SQLSERVER_DATABASE_NOT_OWNED')
        if bytes(owner[2]) != self._schema_hash():
            raise _error('SQLSERVER_MIGRATION_MISMATCH')
        objects = {(row[0], row[1].strip()) for row in connection.execute(
            "SELECT name,type FROM sys.objects WHERE schema_id=SCHEMA_ID(N'dbo') AND type IN ('U','TR') AND name LIKE N'dh[_]research[_]%' "
            "AND (type='U' OR object_id IN (SELECT object_id FROM sys.triggers WHERE is_disabled=0))")}
        expected = {('dh_research_' + name, 'U') for name in TABLES} | {('dh_research_' + name, 'TR') for name in TRIGGERS}
        if objects != expected:
            raise _error('SQLSERVER_SCHEMA_INCOMPLETE')
        migration = connection.execute('SELECT checksum FROM dbo.dh_research_migrations WHERE migration_name=?', MIGRATION).fetchone()
        if not migration or bytes(migration[0]) != self._schema_hash():
            raise _error('SQLSERVER_MIGRATION_MISMATCH')

    def initialize(self):
        """Explicit setup only. Existing databases need an already-valid owner marker."""
        master = self._connect(master=True, autocommit=True)
        created = False
        try:
            exists = master.execute('SELECT DB_ID(?)', self.config.database).fetchone()[0]
            if exists is None:
                master.execute('CREATE DATABASE [' + self.config.database + ']')
                created = True
        except Exception as exc:
            raise _error('SQLSERVER_INITIALIZATION_FAILED', exc, uncertain=True) from None
        finally:
            _close(master)
        connection = self._connect()
        committing = False
        try:
            if not created:
                self._owned(connection)
                connection.rollback()  # finish read-only setup verification, no schema mutation
            else:
                if connection.execute('SELECT COUNT(*) FROM sys.tables WHERE is_ms_shipped=0').fetchone()[0]:
                    raise _error('SQLSERVER_DATABASE_NOT_EMPTY')
                for batch in re.split(r'(?im)^\s*GO\s*$', SCHEMA.read_text(encoding='utf-8')):
                    if batch.strip():
                        connection.execute(batch)
                at = _clock()
                connection.execute('INSERT INTO dbo.dh_research_owner VALUES(1,?,?,?,CONVERT(datetime2(7),?,126))',
                    PRODUCT, SCHEMA_VERSION, self._schema_hash(), at)
                connection.execute('INSERT INTO dbo.dh_research_migrations VALUES(?,?,CONVERT(datetime2(7),?,126))',
                    MIGRATION, self._schema_hash(), at)
                committing = True
                connection.commit()
            self.last_success_at, self.last_error = utc_now(), None
            return {'provider': PROVIDER, 'initialized': True, 'created_database': created,
                    'schema_version': SCHEMA_VERSION, 'migration_sha256': self._schema_hash().hex()}
        except StorageError:
            try:
                connection.rollback()
            except Exception:
                raise _error('SQLSERVER_WRITE_UNCERTAIN', uncertain=True) from None
            raise
        except Exception as exc:
            uncertain = committing
            try:
                connection.rollback()
            except Exception:
                uncertain = True
            raise _error('SQLSERVER_INITIALIZATION_FAILED', exc, uncertain=uncertain) from None
        finally:
            _close(connection)

    @contextmanager
    def transaction(self):
        """Own one real SQL transaction; intended for adapter/internal acceptance only."""
        connection = self._connect()
        committing = False
        try:
            self._owned(connection)
            yield connection
            committing = True
            connection.commit()
            self.last_success_at, self.last_error = utc_now(), None
        except BaseException as exc:
            uncertain = committing
            try:
                connection.rollback()
            except Exception:
                uncertain = True
            if isinstance(exc, StorageError):
                self.last_error = exc.code
                if uncertain:
                    raise _error('SQLSERVER_WRITE_UNCERTAIN', uncertain=True) from None
                raise
            if not isinstance(exc, Exception):
                raise
            self.last_error = 'SQLSERVER_WRITE_FAILED'
            raise _error('SQLSERVER_WRITE_FAILED', exc, uncertain=uncertain) from None
        finally:
            _close(connection)

    def health(self):
        connection = None
        connected = False
        diagnostics = {'provider': PROVIDER, 'server': self.config.server, 'database': self.config.database,
            'authentication': self.config.authentication, 'encrypt_requested': self.config.encrypt,
            'trust_server_certificate': self.config.trust_server_certificate,
            'encryption_scope': 'Requested ODBC encryption; certificate-chain validation is not inferred', 'read_only': True}
        try:
            connection = self._connect()
            connected = True
            self._owned(connection)
            archives = connection.execute('SELECT COUNT_BIG(*) FROM dbo.dh_research_archives WHERE scope=?', self.scope).fetchone()[0]
            notes = connection.execute('SELECT COUNT_BIG(*) FROM dbo.dh_research_notes WHERE scope=?', self.scope).fetchone()[0]
            row = connection.execute("SELECT SUSER_SNAME(),CURRENT_USER,DB_NAME(),"
                "CONVERT(nvarchar(40),CONNECTIONPROPERTY('net_transport')),"
                "CONVERT(nvarchar(40),CONNECTIONPROPERTY('auth_scheme'))").fetchone()
            if (row is None or len(row) != 5 or any(not isinstance(value, str) or not value.strip()
                    or len(value) > 256 or any(ord(character) < 32 for character in value) for value in row)):
                raise _error('SQLSERVER_CONNECTION_IDENTITY_INVALID')
            connection_identity = dict(zip(('login', 'database_user', 'database', 'net_transport', 'auth_scheme'), row))
            if connection_identity['auth_scheme'].upper() not in {'NTLM', 'KERBEROS'}:
                raise _error('SQLSERVER_WINDOWS_AUTHENTICATION_UNVERIFIED')
            self.last_success_at, self.last_error = utc_now(), None
            return {**diagnostics, 'connected': True, 'ready': True, 'status': 'ready',
                    'schema_version': SCHEMA_VERSION, 'counts': {'archives': int(archives), 'notes': int(notes)},
                    'connection_identity': connection_identity,
                    'last_success_at': self.last_success_at, 'last_error': None}
        except StorageError as exc:
            self.last_error = exc.code
            return {**diagnostics, 'connected': connected, 'ready': False, 'status': 'unavailable',
                    'reason_code': exc.code, 'sqlstate': exc.sqlstate,
                    'last_success_at': self.last_success_at, 'last_error': self.last_error}
        except Exception as exc:
            failure = _error('SQLSERVER_READ_FAILED', exc)
            self.last_error = failure.code
            return {**diagnostics, 'connected': connected, 'ready': False, 'status': 'unavailable',
                    'reason_code': failure.code, 'sqlstate': failure.sqlstate,
                    'last_success_at': self.last_success_at, 'last_error': self.last_error}
        finally:
            if connection is not None:
                _close(connection, rollback=True)

    @staticmethod
    def _projection(bundle):
        bundle = validate_bundle(bundle)
        raw = canonical(bundle)
        if len(raw) > MAX_PAYLOAD:
            raise _error('SQLSERVER_ARCHIVE_TOO_LARGE')
        match = bundle['match']
        names = []
        for side in ('home', 'away'):
            if not isinstance(match.get(side), dict):
                raise _error('SQLSERVER_INVALID_MATCH_TEAM')
            names.append(_text(match[side].get('name'), 512, 'SQLSERVER_INVALID_MATCH_TEAM'))
        event_date = match.get('event_date')
        try:
            if not isinstance(event_date, str) or date.fromisoformat(event_date).isoformat() != event_date:
                raise ValueError()
        except ValueError:
            raise _error('SQLSERVER_INVALID_EVENT_DATE') from None
        models = []
        for model in bundle['models']:
            models.append((_record_id(model['record_id']), _text(model['model_name'], 64, 'SQLSERVER_INVALID_MODEL'),
                _text(model['model_version'], 128, 'SQLSERVER_INVALID_MODEL'), _timestamp(model['data_cutoff']),
                canonical(model).decode('utf-8')))
        predictions = []
        model_ids = {model[0] for model in models}
        for prediction in bundle['predictions']:
            if prediction.get('model_run_id') not in model_ids:
                raise _error('SQLSERVER_MODEL_BINDING_MISMATCH')
            probabilities = [_probability(prediction['probabilities'][key]) for key in ('home', 'draw', 'away')]
            with localcontext() as context:
                context.prec = 100
                if abs(sum(Decimal(p) for p in probabilities) - 1) > Decimal('1e-12'):
                    raise _error('SQLSERVER_INVALID_PROBABILITY')
            predictions.append((_record_id(prediction['record_id']), prediction['model_run_id'], *probabilities,
                _timestamp(prediction['decision_cutoff']), _timestamp(prediction['predicted_at']),
                canonical(prediction).decode('utf-8')))
        inputs = []
        for ordinal, row in enumerate(bundle['input_manifest']):
            if row.get('data_origin') not in ('imported_historical', 'captured_real') or row.get('synthetic') is True:
                raise _error('SQLSERVER_REAL_RETAINED_INPUT_REQUIRED')
            inputs.append((ordinal, _record_id(row['evidence_id']), _text(row['source_id'], 512, 'SQLSERVER_INVALID_INPUT'),
                bytes.fromhex(_hex(row['source_hash'])), _timestamp(row['usable_at']), canonical(row).decode('utf-8')))
        return bundle, raw, names, event_date, models, predictions, inputs

    @staticmethod
    def _receipt(archive_id, payload_hash, persisted_at, duplicate=False):
        return {'provider': PROVIDER, 'archive_id': archive_id, 'payload_sha256': bytes(payload_hash).hex(),
                'persisted_at': persisted_at, 'duplicate': duplicate}

    def save(self, bundle):
        try:
            bundle, raw, names, event_date, models, predictions, inputs = self._projection(bundle)
        except (KeyError, TypeError, UnicodeError):
            raise _error('SQLSERVER_INVALID_PROJECTION') from None
        archive_id = _hex(bundle['archive_id'])
        match_id = _hex(bundle['match_id'])
        run_id = _text(bundle['forecast_run_id'], 128, 'SQLSERVER_INVALID_RUN_ID')
        competition = _text(bundle['match']['competition'], 512, 'SQLSERVER_INVALID_MATCH')
        source_id = _text(bundle['match']['source_id'], 512, 'SQLSERVER_INVALID_MATCH')
        payload_hash = hashlib.sha256(raw).digest()
        receipt = None
        with self.transaction() as connection:
            old = connection.execute('SELECT payload_sha256,CONVERT(varchar(33),persisted_at,126)+\'Z\' FROM dbo.dh_research_archives WITH(UPDLOCK,HOLDLOCK) WHERE scope=? AND archive_id=?',
                self.scope, archive_id).fetchone()
            if old:
                if bytes(old[0]) != payload_hash:
                    raise _error('SQLSERVER_ARCHIVE_IDEMPOTENCY_CONFLICT')
                receipt = self._receipt(archive_id, old[0], old[1], True)
            else:
                at = _clock()
                connection.execute('''INSERT INTO dbo.dh_research_archives
                    (scope,archive_id,match_id,forecast_run_id,home_name,away_name,competition,event_date,source_id,
                     payload,payload_sha256,persisted_at,input_count,synthetic)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,CONVERT(datetime2(7),?,126),?,0)''',
                    self.scope, archive_id, match_id, run_id, names[0], names[1], competition, event_date,
                    source_id, raw.decode('utf-8'), payload_hash, at, len(inputs))
                for model in models:
                    connection.execute('INSERT INTO dbo.dh_research_models VALUES(?,?,?,?,?,CONVERT(datetime2(7),?,126),?)',
                        self.scope, archive_id, *model)
                for prediction in predictions:
                    connection.execute('''INSERT INTO dbo.dh_research_predictions VALUES(?,?,?,?,
                        CAST(? AS decimal(38,28)),CAST(? AS decimal(38,28)),CAST(? AS decimal(38,28)),
                        CONVERT(datetime2(7),?,126),CONVERT(datetime2(7),?,126),?)''', self.scope, archive_id, *prediction)
                for row in inputs:
                    connection.execute('INSERT INTO dbo.dh_research_inputs VALUES(?,?,?,?,?,?,CONVERT(datetime2(7),?,126),?)',
                        self.scope, archive_id, *row)
                actual = {row[0]: tuple(Decimal(str(p)) for p in row[1:]) for row in connection.execute(
                    'SELECT record_id,home_probability,draw_probability,away_probability FROM dbo.dh_research_predictions WHERE scope=? AND archive_id=?', self.scope, archive_id)}
                expected = {row[0]: tuple(Decimal(p) for p in row[2:5]) for row in predictions}
                if actual != expected:
                    raise _error('SQLSERVER_PROBABILITY_ROUNDTRIP_FAILED')
                stamp = connection.execute("SELECT CONVERT(varchar(33),persisted_at,126)+'Z' FROM dbo.dh_research_archives WHERE scope=? AND archive_id=?", self.scope, archive_id).fetchone()[0]
                receipt = self._receipt(archive_id, payload_hash, stamp)
        return receipt

    def _decode_archive(self, row):
        archive_id, payload, payload_hash, persisted_at = row
        raw = payload.encode('utf-8')
        if len(raw) > MAX_PAYLOAD:
            raise _error('SQLSERVER_ARCHIVE_TOO_LARGE')
        try:
            bundle = validate_bundle(json.loads(payload))
        except (ValueError, TypeError, KeyError):
            raise _error('SQLSERVER_ARCHIVE_CORRUPT') from None
        if (canonical(bundle) != raw or hashlib.sha256(raw).digest() != bytes(payload_hash)
                or bundle['archive_id'] != archive_id):
            raise _error('SQLSERVER_ARCHIVE_CORRUPT')
        return {'archive': bundle, 'storage': self._receipt(archive_id, payload_hash, persisted_at)}

    @contextmanager
    def _reading(self):
        connection = self._connect()
        try:
            self._owned(connection)
            yield connection
        except StorageError:
            raise
        except Exception as exc:
            raise _error('SQLSERVER_READ_FAILED', exc) from None
        finally:
            _close(connection, rollback=True)

    def get(self, archive_id):
        archive_id = _hex(archive_id)
        with self._reading() as connection:
            row = connection.execute("SELECT archive_id,payload,payload_sha256,CONVERT(varchar(33),persisted_at,126)+'Z' FROM dbo.dh_research_archives WHERE scope=? AND archive_id=?", self.scope, archive_id).fetchone()
            return None if row is None else self._decode_archive(row)

    def history(self, match_id, limit=100):
        match_id = _hex(match_id)
        if type(limit) is not int or not 1 <= limit <= 100:
            raise _error('SQLSERVER_INVALID_LIMIT')
        with self._reading() as connection:
            rows = connection.execute("SELECT TOP (?) archive_id,payload,payload_sha256,CONVERT(varchar(33),persisted_at,126)+'Z' FROM dbo.dh_research_archives WHERE scope=? AND match_id=? ORDER BY persisted_at DESC,archive_id", limit, self.scope, match_id)
            result, total = [], 0
            for row in rows:
                total += len(row[1].encode('utf-8'))
                if total > 32 * 1024 * 1024:
                    raise _error('SQLSERVER_HISTORY_TOO_LARGE')
                decoded = self._decode_archive(row)
                if decoded['archive']['match_id'] != match_id:
                    raise _error('SQLSERVER_ARCHIVE_CORRUPT')
                result.append(decoded)
            return result

    @staticmethod
    def _note(row):
        return dict(zip(('note_id', 'match_id', 'text', 'revision', 'created_at', 'updated_at'),
                        (str(row[0]).lower(), row[1], row[2], int(row[3]), row[4], row[5])))

    def _get_note(self, connection, note_id, *, locked=False):
        lock = ' WITH(UPDLOCK,HOLDLOCK)' if locked else ''
        row = connection.execute("SELECT note_id,match_id,note_text,revision,CONVERT(varchar(33),created_at,126)+'Z',CONVERT(varchar(33),updated_at,126)+'Z' FROM dbo.dh_research_notes" + lock + " WHERE scope=? AND note_id=?", self.scope, note_id).fetchone()
        return None if row is None else self._note(row)

    def create_note(self, match_id, text, note_id=None):
        match_id, text = _hex(match_id), _text(text, 4000, 'SQLSERVER_INVALID_NOTE_TEXT')
        note_id = str(uuid4()) if note_id is None else _uuid(note_id)
        with self.transaction() as connection:
            old = self._get_note(connection, note_id, locked=True)
            if old:
                if old['match_id'] != match_id or old['text'] != text:
                    raise _error('SQLSERVER_NOTE_IDEMPOTENCY_CONFLICT')
                result = old
            else:
                at = _clock()
                connection.execute('INSERT INTO dbo.dh_research_notes VALUES(?,?,?,?,1,CONVERT(datetime2(7),?,126),CONVERT(datetime2(7),?,126))',
                    self.scope, note_id, match_id, text, at, at)
                result = self._get_note(connection, note_id)
        return result

    def update_note(self, note_id, text, expected_revision):
        note_id, text = _uuid(note_id), _text(text, 4000, 'SQLSERVER_INVALID_NOTE_TEXT')
        if type(expected_revision) is not int or not 1 <= expected_revision < 9223372036854775807:
            raise _error('SQLSERVER_INVALID_REVISION')
        with self.transaction() as connection:
            old = self._get_note(connection, note_id)
            if old is None:
                raise _error('SQLSERVER_NOTE_NOT_FOUND')
            if old['revision'] != expected_revision:
                raise _error('SQLSERVER_NOTE_REVISION_CONFLICT')
            changed = connection.execute('''DECLARE @changed TABLE(revision bigint);
                UPDATE dbo.dh_research_notes SET note_text=?,revision=revision+1,updated_at=CONVERT(datetime2(7),?,126)
                OUTPUT inserted.revision INTO @changed
                WHERE scope=? AND note_id=? AND revision=?;
                SELECT revision FROM @changed;''', text, _clock(), self.scope, note_id, expected_revision).fetchone()
            if changed is None or changed[0] != expected_revision + 1:
                raise _error('SQLSERVER_NOTE_REVISION_CONFLICT')
            result = self._get_note(connection, note_id)
            if result is None or result['revision'] != expected_revision + 1 or result['text'] != text:
                raise _error('SQLSERVER_NOTE_REVISION_CONFLICT')
        return result

    def notes(self, match_id):
        match_id = _hex(match_id)
        with self._reading() as connection:
            return [self._note(row) for row in connection.execute("SELECT TOP (100) note_id,match_id,note_text,revision,CONVERT(varchar(33),created_at,126)+'Z',CONVERT(varchar(33),updated_at,126)+'Z' FROM dbo.dh_research_notes WHERE scope=? AND match_id=? ORDER BY updated_at,note_id", self.scope, match_id)]


# Public adapter name used by the application's provider factory.
SQLServerResearchRepository = Repo
