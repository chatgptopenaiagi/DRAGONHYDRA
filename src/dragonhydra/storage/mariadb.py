"""Bounded MariaDB adapter reusing the proven, SELECT-only Joomla laboratory probe."""

from datetime import datetime
from time import perf_counter

from ..config import Settings, load_settings
from ..integration.mariadb_probe import run_probe
from .contracts import (
    CapabilityReport, ConnectionDiagnostic, DatabaseEngineIdentity,
    DatabaseHealth, ReadOnlyQueryResult,
)


class MariaDBAdapter:
    """Expose one controlled aggregate operation; no generic SQL execution API.

    The existing probe checks SELECT-only grants, executes read-only transactions,
    and expects error 1142 from a guaranteed zero-row UPDATE in a normal
    transaction. It rolls transactions back and never returns secrets or hashes.
    Latency measures the complete capability proof, including its connections.
    """

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or load_settings()

    def capability_report(self) -> CapabilityReport:
        started = perf_counter()
        proof = run_probe(self.settings)
        latency_ms = (perf_counter() - started) * 1000
        if not proof["passed"]:
            raise RuntimeError("MariaDB probe did not establish its SELECT-only safety boundary")
        if proof["account"] != "dragonhydra_probe@localhost":
            raise RuntimeError("MariaDB probe connected with an unexpected database identity")
        return CapabilityReport(
            identity=DatabaseEngineIdentity(
                engine="mariadb", version=proof["server_version"],
                host=self.settings.host, port=self.settings.port,
                database=self.settings.database, driver=proof["driver"],
                driver_version=proof["driver_version"],
            ),
            health=DatabaseHealth(
                status="healthy", connected=True, latency_ms=latency_ms,
                checked_at=datetime.fromisoformat(proof["checked_utc"]),
            ),
            read=True, write=False, transaction=True, write_rejected=True,
            result=ReadOnlyQueryResult(
                operation="controlled_joomla_aggregates",
                counts=tuple(proof["aggregates"].items()),
                source_database=self.settings.database,
            ),
            diagnostic=ConnectionDiagnostic(
                transport="tcp", encrypted=None, certificate_validated=None,
                reason_codes=(
                    "DEDICATED_IDENTITY_VERIFIED", "SELECT_ONLY_GRANTS_VERIFIED",
                    "WRITE_REJECTED_1142", "AGGREGATE_COUNTS_UNCHANGED",
                    "READ_ONLY_TRANSACTION_ROLLED_BACK", "TLS_STATE_NOT_MEASURED",
                ),
            ),
        )
