"""Fixed aggregate SELECTs against the controlled Joomla laboratory database."""

from datetime import datetime, timezone
import importlib.metadata
import sys

from ..config import Settings, load_probe_credential, load_settings
from ..storage.contracts import AggregateSnapshot


def load_driver(settings: Settings):
    directory = str(settings.driver_directory)
    if not settings.driver_directory.is_dir():
        raise RuntimeError("Pinned project-local PyMySQL wheel has not been installed")
    if directory not in sys.path:
        sys.path.insert(0, directory)
    import pymysql
    from pathlib import Path
    if not Path(pymysql.__file__).resolve().is_relative_to(settings.driver_directory.resolve()):
        raise RuntimeError("Loaded database driver is outside the pinned project directory")
    if importlib.metadata.version("PyMySQL") != settings.driver_version:
        raise RuntimeError("Database driver version does not match configuration")
    return pymysql


class MariaDBJoomlaProbe:
    """No arbitrary SQL API; application code can only request fixed aggregates."""

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or load_settings()
        self.driver = load_driver(self.settings)

    def _connect(self):
        secret = load_probe_credential(self.settings)
        try:
            return self.driver.connect(
                host=self.settings.host, port=self.settings.port,
                user=secret.username, password=secret.password,
                database=self.settings.database, charset="utf8mb4",
                connect_timeout=self.settings.connect_timeout_seconds,
                read_timeout=10, write_timeout=10, autocommit=False,
            )
        except self.driver.MySQLError as error:
            # Do not expose raw driver context or credentials to logs.
            code = error.args[0] if error.args else "unknown"
            raise RuntimeError(f"Probe database connection failed (code {code})") from None

    def snapshot(self) -> AggregateSnapshot:
        prefix = self.settings.table_prefix  # Identifier validated by Settings invariants.
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("START TRANSACTION READ ONLY")
                cursor.execute("SELECT COUNT(*) FROM information_schema.TABLES WHERE TABLE_SCHEMA=%s", (self.settings.database,))
                counts = [("table_count", int(cursor.fetchone()[0]))]
                for name, sql in (
                    ("published_content_count", f"SELECT COUNT(*) FROM `{prefix}content` WHERE state=1"),
                    ("user_count", f"SELECT COUNT(*) FROM `{prefix}users`"),
                    ("extension_count", f"SELECT COUNT(*) FROM `{prefix}extensions`"),
                ):
                    cursor.execute(sql)
                    counts.append((name, int(cursor.fetchone()[0])))
            connection.rollback()
        return AggregateSnapshot("controlled-joomla-lab", datetime.now(timezone.utc), tuple(counts))

    def verify_write_rejection(self) -> bool:
        # Deliberately use a normal transaction here: READ ONLY transaction mode must
        # not mask a bad account grant. WHERE 1=0 prevents row changes even on failure.
        with self._connect() as connection:
            try:
                with connection.cursor() as cursor:
                    cursor.execute(f"UPDATE `{self.settings.table_prefix}content` SET id=id WHERE 1=0")
            except self.driver.MySQLError as error:
                if error.args and error.args[0] == 1142:
                    return True
                code = error.args[0] if error.args else "unknown"
                raise RuntimeError(f"Unexpected write-denial error (code {code})") from None
            finally:
                connection.rollback()
        return False

    def privilege_summary(self) -> dict:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT PRIVILEGE_TYPE,IS_GRANTABLE FROM information_schema.USER_PRIVILEGES")
                global_permissions = [list(row) for row in cursor.fetchall()]
                cursor.execute("SELECT TABLE_SCHEMA,PRIVILEGE_TYPE,IS_GRANTABLE FROM information_schema.SCHEMA_PRIVILEGES")
                schema_permissions = [list(row) for row in cursor.fetchall()]
                cursor.execute("SELECT VERSION(),CURRENT_USER(),CURRENT_ROLE()")
                version, account, active_role = cursor.fetchone()
                cursor.execute("SELECT PRIVILEGE_TYPE FROM information_schema.TABLE_PRIVILEGES")
                table_permissions = cursor.fetchall()
                cursor.execute("SELECT PRIVILEGE_TYPE FROM information_schema.COLUMN_PRIVILEGES")
                column_permissions = cursor.fetchall()
                cursor.execute("SELECT COUNT(*) FROM information_schema.APPLICABLE_ROLES")
                applicable_role_count = int(cursor.fetchone()[0])
                cursor.execute("SHOW GRANTS")
                # SHOW GRANTS may contain an authentication hash. Keep only scopes,
                # never the identity/authentication suffix in output or evidence.
                grant_scope_headers = [row[0].split(" TO ", 1)[0] for row in cursor.fetchall()]
            connection.rollback()
        expected_schema = self.settings.database.replace("_", "\\_")
        expected_headers = ["GRANT USAGE ON *.*", f"GRANT SELECT ON `{expected_schema}`.*"]
        only_select = (all(row == ["USAGE", "NO"] for row in global_permissions)
                       and schema_permissions == [[expected_schema, "SELECT", "NO"]]
                       and not table_permissions and not column_permissions
                       and applicable_role_count == 0 and active_role in (None, "NONE")
                       and sorted(grant_scope_headers) == sorted(expected_headers))
        return {"server_version": version, "account": account,
                "global_privileges": global_permissions, "schema_privileges": schema_permissions,
                "table_grant_count": len(table_permissions), "column_grant_count": len(column_permissions),
                "applicable_role_count": applicable_role_count, "active_role": active_role,
                "grant_scope_headers": grant_scope_headers,
                "select_only_grants": only_select}


def run_probe(settings: Settings | None = None) -> dict:
    probe = MariaDBJoomlaProbe(settings)
    before = probe.snapshot()
    write_denied = probe.verify_write_rejection()
    after = probe.snapshot()
    privileges = probe.privilege_summary()
    passed = write_denied and before.counts == after.counts and privileges["select_only_grants"]
    return {
        "checked_utc": after.measured_at.isoformat(),
        "scope": "Python 3.14 -> MariaDB -> XAMPP capability proof; Joomla is only a controlled source",
        "database": probe.settings.database, "endpoint": f"{probe.settings.host}:{probe.settings.port}",
        "driver": "PyMySQL", "driver_version": probe.settings.driver_version,
        "aggregates": dict(after.counts), "write_rejected_with_error_1142": write_denied,
        "aggregate_counts_unchanged": before.counts == after.counts,
        **privileges, "passed": passed,
    }
