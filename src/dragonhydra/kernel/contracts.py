"""Explicit module definitions and short-lived observations, without implicit probes."""
from dataclasses import dataclass, field
from datetime import datetime, timezone
import re
from typing import Callable, Mapping, Protocol

STATES = frozenset({'NOT_IMPLEMENTED', 'NOT_CONFIGURED', 'UNVERIFIED', 'READY', 'DEGRADED',
                    'UNAVAILABLE', 'NOT_APPLICABLE', 'UNKNOWN', 'EXPIRED', 'STOPPED'})


def utc_now():
    return datetime.now(timezone.utc)


def iso(value):
    return value.isoformat(timespec='microseconds').replace('+00:00', 'Z')


@dataclass(frozen=True)
class KernelConfig:
    installation_id: str
    environment_id: str = 'source-checkout'
    product: str = 'DRAGONHYDRA CORE NEXT'
    edition: str = 'CORE NEXT'
    build_id: str | None = None
    source_commit: str | None = None
    version: str | None = None
    observation_ttl_seconds: int = 300
    disabled_modules: tuple[str, ...] = ()

    def __post_init__(self):
        if self.product != 'DRAGONHYDRA CORE NEXT' or self.edition != 'CORE NEXT':
            raise ValueError('CORE_NEXT_IDENTITY_REQUIRED')
        for value in (self.installation_id, self.environment_id):
            if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}', value):
                raise ValueError('INVALID_INSTALLATION_IDENTITY')
        if type(self.observation_ttl_seconds) is not int or not 1 <= self.observation_ttl_seconds <= 3600:
            raise ValueError('INVALID_OBSERVATION_TTL')
        object.__setattr__(self, 'disabled_modules', tuple(self.disabled_modules))

    def identity(self):
        return {key: getattr(self, key) for key in ('product', 'edition', 'installation_id',
                'environment_id', 'build_id', 'source_commit', 'version')}


@dataclass(frozen=True)
class ModuleDefinition:
    id: str
    name: str
    description: str
    category: str
    dependencies: tuple[str, ...] = ()
    capabilities: tuple[str, ...] = ()
    origin: str = 'built-in'
    version: str = '1'
    optional_dependencies: tuple[str, ...] = ()
    configuration_requirements: tuple[str, ...] = ()
    supported_operations: tuple[str, ...] = ()
    data_domains: tuple[str, ...] = ()
    verification_references: tuple[str, ...] = ()
    implementation_reference: str = ''
    schema_version: str = 'core-next.module/1'
    capability_operations: tuple[tuple[str, tuple[str, ...]], ...] = ()
    capability_dependencies: tuple[tuple[str, tuple[str, ...]], ...] = ()


class Engine(Protocol):
    """Only explicit lifecycle/refresh may invoke observe; status never calls it."""
    def observe(self) -> Mapping: ...
    def stop(self) -> None: ...


@dataclass(frozen=True)
class Observation:
    state: str
    reason: str
    observed_at: datetime
    expires_at: datetime
    metrics: Mapping = field(default_factory=dict)
    evidence: tuple[str, ...] = ()
    installation_id: str = ''
    module_id: str = ''
    last_success: datetime | None = None
    metrics_sampled_at: datetime | None = None

    def __post_init__(self):
        if self.state not in STATES or self.expires_at < self.observed_at:
            raise ValueError('INVALID_MODULE_OBSERVATION')
        if any(not isinstance(k, str) or not (v is None or type(v) in (str, bool, int, float))
               for k, v in self.metrics.items()):
            raise ValueError('INVALID_OBSERVATION_METRICS')
