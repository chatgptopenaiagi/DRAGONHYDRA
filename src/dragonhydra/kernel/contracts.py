"""Explicit module definitions and short-lived observations, without implicit probes."""
from dataclasses import dataclass, field
from datetime import datetime, timezone
import math
import re
from types import MappingProxyType
from typing import Callable, Mapping, Protocol

STATES = frozenset({'NOT_IMPLEMENTED', 'NOT_CONFIGURED', 'UNVERIFIED', 'READY', 'DEGRADED',
                    'UNAVAILABLE', 'NOT_APPLICABLE', 'UNKNOWN', 'EXPIRED', 'STOPPED'})

# Only finite, bounded counters/flags may leave the registry. Paths, provider
# settings, exception strings and arbitrary adapter fields are never metrics.
METRIC_KEYS = frozenset({'public_fixture_records','connector_observations','retained_observation_count',
    'cognitive_records','cognitive_receipts','configured','process_id','worker_alive',
    'queued_jobs','running_jobs','enabled_schedules','listener_present','http_status',
    'table_count','schema_complete','artifact_present','observations_completed',
    'observations_failed','observer_running','last_cycle_ms','registry_count'})
CONFIGURATION_REFERENCES = frozenset({'sqlite_state','retained_provider_scope','eligible_future_fixture',
    'same_source_training_evidence','eligible_persisted_prediction_and_later_outcome',
    'protected_server_endpoint','protected_server_credential','workstation_profile',
    'web_document_root','php_runtime','apache_configuration','joomla_component',
    'mariadb_endpoint','core_sqlite','worker','provider_settings','endpoint_pairing',
    'external_android_pairing','package_manifest'})


def sanitized_metrics(values):
    result = {}
    for key,value in dict(values).items():
        if key not in METRIC_KEYS:
            continue
        if value is not None and (type(value) not in (bool,int,float)
                or (type(value) in (int,float) and (not math.isfinite(value) or abs(value)>10**15))):
            raise ValueError('INVALID_OBSERVATION_METRICS')
        result[key] = value
    return result


def utc_now():
    return datetime.now(timezone.utc)


def iso(value):
    return value.astimezone(timezone.utc).isoformat(timespec='microseconds').replace('+00:00', 'Z')


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
    observation_interval_seconds: int | None = None

    def __post_init__(self):
        if self.product != 'DRAGONHYDRA CORE NEXT' or self.edition != 'CORE NEXT':
            raise ValueError('CORE_NEXT_IDENTITY_REQUIRED')
        for value in (self.installation_id, self.environment_id):
            if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}', value):
                raise ValueError('INVALID_INSTALLATION_IDENTITY')
        if type(self.observation_ttl_seconds) is not int or not 1 <= self.observation_ttl_seconds <= 3600:
            raise ValueError('INVALID_OBSERVATION_TTL')
        if self.observation_interval_seconds is None:
            object.__setattr__(self,'observation_interval_seconds',min(30,max(1,self.observation_ttl_seconds//3)))
        if type(self.observation_interval_seconds) is not int or not 1 <= self.observation_interval_seconds <= min(300,self.observation_ttl_seconds):
            raise ValueError('INVALID_OBSERVATION_INTERVAL')
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
    layer: str = 'engine'
    runtime_owner: str = 'CORE NEXT Python kernel'


class Engine(Protocol):
    """Only explicit lifecycle/refresh may invoke observe; status never calls it."""
    def observe(self) -> Mapping: ...
    def stop(self) -> None: ...


@dataclass(frozen=True)
class ServiceIdentity:
    """Fresh running-service/supervisor binding, never an account or ACL claim."""
    service_name: str
    installation_id: str
    source_commit: str
    build_id: str
    observed_at: datetime
    evidence_expires_at: datetime
    verification_scope: str = 'BOUND_SUPERVISOR_SERVICE_IDENTITY_ONLY'

    def __post_init__(self):
        if (not isinstance(self.service_name,str) or not re.fullmatch(r'Dragonhydra[A-Za-z0-9_-]{0,60}',self.service_name)
                or not isinstance(self.installation_id,str) or not re.fullmatch(r'core-next-[a-f0-9]{32}',self.installation_id)
                or not isinstance(self.source_commit,str) or not re.fullmatch(r'[a-f0-9]{40}',self.source_commit)
                or not isinstance(self.build_id,str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:+-]{0,127}',self.build_id)
                or self.verification_scope != 'BOUND_SUPERVISOR_SERVICE_IDENTITY_ONLY'
                or not isinstance(self.observed_at,datetime) or not isinstance(self.evidence_expires_at,datetime)
                or self.observed_at.utcoffset() is None or self.evidence_expires_at.utcoffset() is None
                or not 0<(self.evidence_expires_at-self.observed_at).total_seconds()<=90):
            raise ValueError('INVALID_SERVICE_IDENTITY')


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
    observation_id: str = ''
    observer_identity: str = ''
    build_identity: str = ''
    verification_scope: tuple[str, ...] = ()
    metrics_expiry: datetime | None = None
    service_identity: ServiceIdentity | None = None

    def __post_init__(self):
        if (self.state not in STATES or not isinstance(self.observed_at,datetime)
                or not isinstance(self.expires_at,datetime) or self.observed_at.utcoffset() is None
                or self.expires_at.utcoffset() is None or self.expires_at <= self.observed_at):
            raise ValueError('INVALID_MODULE_OBSERVATION')
        if self.last_success is not None and (self.last_success.utcoffset() is None or self.last_success>self.observed_at):
            raise ValueError('INVALID_LAST_SUCCESS_CLOCK')
        if self.metrics_expiry is not None and (self.metrics_sampled_at is None or self.metrics_expiry.utcoffset() is None or self.metrics_expiry<=self.metrics_sampled_at):
            raise ValueError('INVALID_METRICS_EXPIRY')
        identity=self.service_identity
        if identity is not None and (not isinstance(identity,ServiceIdentity)
                or self.module_id!='runtime_supervisor' or identity.installation_id!=self.installation_id
                or identity.build_id+':'+identity.source_commit!=self.build_identity
                or not identity.observed_at<=self.observed_at<identity.evidence_expires_at<=self.expires_at):
            raise ValueError('UNBOUND_SERVICE_IDENTITY')
        object.__setattr__(self,'metrics',MappingProxyType(sanitized_metrics(self.metrics)))
