"""Narrow read boundary for capability proofs, independent of MariaDB and Joomla."""

from dataclasses import dataclass
from datetime import datetime
import math
from typing import Protocol


@dataclass(frozen=True, slots=True)
class AggregateSnapshot:
    source_id: str
    measured_at: datetime
    counts: tuple[tuple[str, int], ...]


class AggregateReader(Protocol):
    def snapshot(self) -> AggregateSnapshot: ...


class ReadOnlyPermissionProbe(Protocol):
    def verify_write_rejection(self) -> bool:
        """Test a guaranteed zero-row UPDATE; unexpected acceptance is a failure."""
        ...


def _text(value: str, name: str) -> None:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ValueError(f"{name} must be a nonempty, trimmed string")


def _boolean(value: bool, name: str) -> None:
    if not isinstance(value, bool):
        raise ValueError(f"{name} must be a boolean")


@dataclass(frozen=True, slots=True)
class DatabaseEngineIdentity:
    """Non-secret endpoint and driver identity observed by a bounded adapter."""

    engine: str
    version: str
    host: str
    port: int
    database: str
    driver: str
    driver_version: str

    def __post_init__(self) -> None:
        for name in ("engine", "version", "host", "database", "driver", "driver_version"):
            _text(getattr(self, name), name)
        if self.engine not in {"mariadb", "sqlserver"}:
            raise ValueError("Unsupported capability-proof database engine")
        if type(self.port) is not int or not 1 <= self.port <= 65535:
            raise ValueError("Database port must be an integer between 1 and 65535")


@dataclass(frozen=True, slots=True)
class DatabaseHealth:
    status: str
    connected: bool
    latency_ms: float
    checked_at: datetime

    def __post_init__(self) -> None:
        if self.status not in {"healthy", "unhealthy", "unavailable", "unknown"}:
            raise ValueError("Unsupported database health status")
        _boolean(self.connected, "connected")
        if self.status == "healthy" and not self.connected:
            raise ValueError("A healthy database must have a verified connection")
        if (isinstance(self.latency_ms, bool)
                or not isinstance(self.latency_ms, (int, float))
                or not math.isfinite(self.latency_ms) or self.latency_ms < 0):
            raise ValueError("Latency must be finite and nonnegative")
        if not isinstance(self.checked_at, datetime) or self.checked_at.utcoffset() is None:
            raise ValueError("Health measurement requires an aware timestamp")


@dataclass(frozen=True, slots=True)
class ReadOnlyQueryResult:
    """Fixed operation output, with no arbitrary SQL or connection object exposed."""

    operation: str
    counts: tuple[tuple[str, int], ...]
    source_database: str

    def __post_init__(self) -> None:
        _text(self.operation, "operation")
        _text(self.source_database, "source_database")
        if not isinstance(self.counts, tuple) or not self.counts:
            raise ValueError("Counts must be a nonempty immutable tuple")
        names: set[str] = set()
        for pair in self.counts:
            if not isinstance(pair, tuple) or len(pair) != 2:
                raise ValueError("Each count must be an immutable name/value pair")
            name, value = pair
            _text(name, "count name")
            if name in names:
                raise ValueError("Count names must be unique")
            if type(value) is not int or value < 0:
                raise ValueError("Counts must be nonnegative integers")
            names.add(name)


@dataclass(frozen=True, slots=True)
class ConnectionDiagnostic:
    transport: str
    encrypted: bool | None
    certificate_validated: bool | None
    reason_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        _text(self.transport, "transport")
        for name in ("encrypted", "certificate_validated"):
            value = getattr(self, name)
            if value is not None:
                _boolean(value, name)
        if self.certificate_validated is True and self.encrypted is not True:
            raise ValueError("A validated TLS certificate requires verified encryption")
        if not isinstance(self.reason_codes, tuple):
            raise ValueError("Reason codes must be an immutable tuple")
        for reason in self.reason_codes:
            _text(reason, "reason code")
        if len(set(self.reason_codes)) != len(self.reason_codes):
            raise ValueError("Reason codes must be unique")


@dataclass(frozen=True, slots=True)
class CapabilityReport:
    """Evidence from a bounded operation, not permission to execute arbitrary SQL."""

    identity: DatabaseEngineIdentity
    health: DatabaseHealth
    read: bool
    write: bool
    transaction: bool
    write_rejected: bool
    result: ReadOnlyQueryResult
    diagnostic: ConnectionDiagnostic

    def __post_init__(self) -> None:
        for name, expected in (
            ("identity", DatabaseEngineIdentity), ("health", DatabaseHealth),
            ("result", ReadOnlyQueryResult), ("diagnostic", ConnectionDiagnostic),
        ):
            if not isinstance(getattr(self, name), expected):
                raise ValueError(f"{name} has an invalid contract type")
        for name in ("read", "write", "transaction", "write_rejected"):
            _boolean(getattr(self, name), name)
        if self.result.source_database != self.identity.database:
            raise ValueError("Query result provenance must match the connected database")
        if self.write and self.write_rejected:
            raise ValueError("A denied bounded write cannot establish write capability")
        if (self.read or self.write or self.transaction) and not self.health.connected:
            raise ValueError("Verified capabilities require a verified connection")
