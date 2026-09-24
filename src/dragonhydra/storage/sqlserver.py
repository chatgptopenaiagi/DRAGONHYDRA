"""Fixed SQL Server laboratory operations with no unrestricted SQL interface."""

from datetime import datetime, timezone
import importlib.metadata
from pathlib import Path
import sys
from time import perf_counter

from .contracts import (CapabilityReport, ConnectionDiagnostic, DatabaseEngineIdentity,
                        DatabaseHealth, ReadOnlyQueryResult)
from .sqlserver_config import (SQLServerSettings, load_sqlserver_credential,
                               load_sqlserver_settings)


def load_odbc(settings: SQLServerSettings):
    directory = str(settings.driver_directory)
    if directory not in sys.path:
        sys.path.insert(0, directory)
    import pyodbc
    if not Path(pyodbc.__file__).resolve().is_relative_to(settings.driver_directory.resolve()):
        raise RuntimeError("pyodbc loaded outside its pinned project directory")
    if importlib.metadata.version("pyodbc") != settings.python_driver_version:
        raise RuntimeError("pyodbc version differs from the measured configuration")
    if settings.odbc_driver not in pyodbc.drivers():
        raise RuntimeError("Required Microsoft ODBC Driver 18 is not registered")
    return pyodbc


def odbc_value(value: str) -> str:
    """Quote ODBC values including literal closing braces and semicolons."""
    return "{" + value.replace("}", "}}") + "}"


def local_connection_options(settings: SQLServerSettings) -> str:
    host = f"[{settings.host}]" if ":" in settings.host else settings.host
    return (f"DRIVER={odbc_value(settings.odbc_driver)};SERVER=tcp:{host},{settings.port};"
            f"DATABASE={odbc_value(settings.database)};Encrypt=yes;"
            f"TrustServerCertificate={'yes' if settings.trust_server_certificate else 'no'};")


def lab_grants_are_exact(rows: list[tuple], sample_object_id: int) -> bool:
    """Only database CONNECT and object SELECT, with no delegation or other scope."""
    return set(rows) == {(0, 0, 0, "CONNECT", "GRANT"),
                         (1, sample_object_id, 0, "SELECT", "GRANT")}


class SQLServerAdapter:
    def __init__(self, settings: SQLServerSettings | None = None):
        self.settings = settings or load_sqlserver_settings()
        self.driver = load_odbc(self.settings)

    def _connect(self):
        credential = load_sqlserver_credential(self.settings)
        options = local_connection_options(self.settings)
        options += f"UID={odbc_value(credential.username)};PWD={odbc_value(credential.password)};"
        try:
            connection = self.driver.connect(options, timeout=self.settings.connect_timeout_seconds,
                                             autocommit=False)
            connection.timeout = self.settings.query_timeout_seconds
            return connection
        except self.driver.Error as error:
            state = error.args[0] if error.args else "unknown"
            raise RuntimeError(f"SQL Server connection failed (SQLSTATE {state})") from None

    def _inspect(self, connection) -> dict:
        cursor = connection.cursor()
        cursor.execute("SELECT CAST(SERVERPROPERTY('ProductVersion') AS nvarchar(128)),"
                       "CAST(SERVERPROPERTY('ProductLevel') AS nvarchar(128)),"
                       "CAST(SERVERPROPERTY('Edition') AS nvarchar(128)),"
                       "CAST(SERVERPROPERTY('InstanceName') AS nvarchar(128)),"
                       "CAST(SERVERPROPERTY('EngineEdition') AS int),"
                       "CAST(SERVERPROPERTY('Collation') AS nvarchar(128)),DB_NAME(),ORIGINAL_LOGIN(),@@VERSION")
        row = cursor.fetchone()
        identity = dict(zip(("version", "product_level", "edition", "instance_name", "engine_edition",
                             "collation", "database", "login", "version_banner"), row))
        cursor.execute("SELECT permission_name FROM fn_my_permissions(NULL,'SERVER')")
        server_permissions = sorted(row[0] for row in cursor.fetchall())
        cursor.execute("SELECT permission_name FROM fn_my_permissions(NULL,'DATABASE')")
        database_permissions = sorted(row[0] for row in cursor.fetchall())
        cursor.execute("SELECT permission_name FROM fn_my_permissions('probe.CapabilitySample','OBJECT')")
        # fn_my_permissions returns both object-level and column-level SELECT
        # rows; compare the permission set without mistaking duplicates for writes.
        object_permissions = sorted({row[0] for row in cursor.fetchall()})
        cursor.execute("SELECT r.name FROM sys.server_role_members m JOIN sys.server_principals r ON r.principal_id=m.role_principal_id WHERE m.member_principal_id=SUSER_ID()")
        server_roles = [row[0] for row in cursor.fetchall()]
        cursor.execute("SELECT r.name FROM sys.database_role_members m JOIN sys.database_principals r ON r.principal_id=m.role_principal_id WHERE m.member_principal_id=USER_ID()")
        database_roles = [row[0] for row in cursor.fetchall()]
        cursor.execute("SELECT IS_SRVROLEMEMBER('sysadmin'),IS_SRVROLEMEMBER('serveradmin'),IS_SRVROLEMEMBER('securityadmin'),IS_MEMBER('db_owner')")
        elevated = any(value != 0 for value in cursor.fetchone())
        cursor.execute("SELECT OBJECT_ID(N'probe.CapabilitySample')")
        sample_object_id = int(cursor.fetchone()[0])
        cursor.execute("SELECT class,major_id,minor_id,permission_name,state_desc FROM sys.database_permissions WHERE grantee_principal_id=USER_ID()")
        explicit_grants = [tuple(row) for row in cursor.fetchall()]
        cursor.execute("SELECT s.name,o.name FROM sys.objects o JOIN sys.schemas s ON s.schema_id=o.schema_id WHERE o.is_ms_shipped=0 AND o.type IN ('U','V','P','FN','IF','TF')")
        visible_objects = [tuple(row) for row in cursor.fetchall()]
        cursor.execute("SELECT COUNT(*) FROM sys.schemas WHERE HAS_PERMS_BY_NAME(name,'SCHEMA','ALTER')=1 OR HAS_PERMS_BY_NAME(name,'SCHEMA','CONTROL')=1 OR HAS_PERMS_BY_NAME(name,'SCHEMA','TAKE OWNERSHIP')=1")
        writable_schema_count = int(cursor.fetchone()[0])
        cursor.execute("SELECT COUNT_BIG(*),COALESCE(SUM(CAST(quantity AS bigint)),0) FROM probe.CapabilitySample")
        counts = tuple(int(value) for value in cursor.fetchone())
        allowed_server = {"CONNECT SQL", "VIEW ANY DATABASE", "VIEW ANY COLUMN ENCRYPTION KEY DEFINITION",
                          "VIEW ANY COLUMN MASTER KEY DEFINITION"}
        allowed_database = {"CONNECT", "VIEW ANY COLUMN ENCRYPTION KEY DEFINITION",
                            "VIEW ANY COLUMN MASTER KEY DEFINITION"}
        bounded = (identity["login"] == "dragonhydra_probe_sqlserver"
                   and identity["database"] == self.settings.database
                   and not elevated and not server_roles and not database_roles
                   and set(server_permissions) <= allowed_server
                   and "CONNECT" in database_permissions
                   and set(database_permissions) <= allowed_database and object_permissions == ["SELECT"]
                   and lab_grants_are_exact(explicit_grants, sample_object_id)
                   and visible_objects == [("probe", "CapabilitySample")] and writable_schema_count == 0)
        return {**identity, "server_permissions": server_permissions, "database_permissions": database_permissions,
                "object_permissions": object_permissions, "server_roles": server_roles,
                "database_roles": database_roles, "bounded_identity": bounded, "counts": counts,
                "explicit_database_grants": explicit_grants, "visible_user_objects": visible_objects,
                "writable_schema_count": writable_schema_count,
                "permission_proof_scope": "server privileges and controlled DRAGONHYDRA_LAB; no assertion about future mappings in other databases",
                "odbc_driver_version": connection.getinfo(self.driver.SQL_DRIVER_VER)}

    def _write_rejected(self, connection) -> bool:
        try:
            connection.execute("UPDATE probe.CapabilitySample SET quantity=quantity WHERE 1=0")
        except self.driver.Error as error:
            # Native permission-denied error 229, not a read-only-session error.
            state = str(error.args[0]) if error.args else ""
            detail = str(error.args[1]) if len(error.args) > 1 else ""
            if state == "42000" and "(229)" in detail:
                return True
            raise RuntimeError(f"Unexpected SQL Server denial (SQLSTATE {state})") from None
        finally:
            connection.rollback()
        return False

    def inspect_capabilities(self) -> tuple[CapabilityReport, dict]:
        started = perf_counter()
        connection = self._connect()
        try:
            before = self._inspect(connection)
            connection.rollback()
            denied = self._write_rejected(connection)
            connection.execute("BEGIN TRANSACTION")
            transaction_count = int(connection.execute("SELECT @@TRANCOUNT").fetchone()[0])
            after = self._inspect(connection)
            connection.rollback()
        finally:
            connection.close()
        unchanged = before["counts"] == after["counts"]
        healthy = denied and after["bounded_identity"] and unchanged and transaction_count >= 1
        report = CapabilityReport(
            identity=DatabaseEngineIdentity("sqlserver", after["version"], self.settings.host,
                self.settings.port, self.settings.database, self.settings.odbc_driver + " + pyodbc",
                self.settings.python_driver_version),
            health=DatabaseHealth("healthy" if healthy else "unhealthy", True,
                (perf_counter() - started) * 1000, datetime.now(timezone.utc)),
            read=True, write=not denied, transaction=transaction_count >= 1, write_rejected=denied,
            result=ReadOnlyQueryResult("laboratory_sample_aggregates",
                (("row_count", after["counts"][0]), ("quantity_sum", after["counts"][1])), self.settings.database),
            diagnostic=ConnectionDiagnostic("TCP", True, not self.settings.trust_server_certificate,
                ("ENCRYPTION_REQUIRED", "LOOPBACK_CERTIFICATE_TRUST_EXCEPTION")
                if self.settings.trust_server_certificate else ("ENCRYPTION_REQUIRED",)),
        )
        details = {**after, "counts_unchanged": unchanged, "write_denied_native_error": 229 if denied else None,
                   "transaction_count_before_rollback": transaction_count,
                   "latency_scope": "connection, identity/grants, aggregate queries, denial and rollback"}
        return report, details

    def capability_report(self) -> CapabilityReport:
        return self.inspect_capabilities()[0]
