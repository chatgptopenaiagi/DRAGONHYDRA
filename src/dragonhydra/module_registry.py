"""Versioned module definitions and bounded, passive installation observations.

Definitions describe implemented software, not installed or running processes.
Status reads never initialize a store, contact a provider/model, or launch work.
The workstation supervisor is the sole external-process observer; its short-lived
receipt must identify this running kernel before it can contribute readiness.
"""
from __future__ import annotations

from collections import Counter
from contextlib import closing
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import time
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .build_meta import VERSION
from .local_ai import LocalAIError


REGISTRY_VERSION = 'module-registry/1'
RuntimeState = Literal['not_implemented', 'installed_not_configured',
                       'configured_unverified', 'ready', 'degraded',
                       'unavailable', 'not_applicable']
STATES = ('not_implemented', 'installed_not_configured', 'configured_unverified',
          'ready', 'degraded', 'unavailable', 'not_applicable')
CONFIGURATION_REFERENCES = frozenset({
    'product.sqlite', 'product.retained_evidence', 'product.jobs', 'product.worker',
    'product.local_ai', 'product.provider_settings', 'workstation.observer',
    'workstation.apache', 'workstation.joomla', 'workstation.mariadb',
    'workstation.launcher', 'android.endpoint_pairing', 'cognition.memory',
})
METRIC_KEYS = frozenset({
    'process_id', 'worker_alive', 'queued_jobs', 'running_jobs', 'stale_running_jobs',
    'enabled_schedules', 'retained_fixture_versions', 'connector_observations',
    'raw_documents', 'cognitive_records', 'prediction_records', 'outcome_records',
    'evaluation_records', 'table_count', 'configured', 'core_store_ready',
    'api_version', 'probe_http_status', 'listener_present', 'authenticated',
    'component_enabled', 'root_is_component', 'pid',
})
# A definition cannot promote a roadmap label into an implemented capability.
# Each admitted claim has an owning source reference, and calculation claims
# additionally have a declared, implemented operation. Repository tests verify
# these static references against their actual owners.
CAPABILITY_REFERENCES = {
    'serve Joomla HTTP requests': ('packaging/windows/workstation/Workstation.ps1', None),
    'component administration': ('server/joomla/com_dragonhydra/admin', None),
    'server-side signed bridge': ('server/joomla/com_dragonhydra/admin', None),
    'workspace navigation': ('server/joomla/com_dragonhydra/site', 'read_matches'),
    'retained sports views': ('server/joomla/com_dragonhydra/site', 'read_matches'),
    'local pairing': ('src/dragonhydra/api.py', None),
    'signed Joomla bridge': ('src/dragonhydra/api.py', None),
    'typed read operations': ('src/dragonhydra/api.py', 'read_modules'),
    'retained fixtures': ('src/dragonhydra/public_results.py', 'read_matches'),
    'source identity': ('src/dragonhydra/public_results.py', 'internal_public_retention'),
    'provider adapters': ('src/dragonhydra/connectors', 'read_connections'),
    'odds conversion': ('src/dragonhydra/market_signals.py', 'internal_market_signals'),
    'retained market history': ('src/dragonhydra/product.py', 'read_odds'),
    **{name: ('src/dragonhydra/cognition/models.py', 'internal_cognitive_forecast')
       for name in ('frequency', 'poisson_goals', 'elo', 'recency', 'ensemble')},
    'constrained source-fact explanations': ('src/dragonhydra/local_ai.py', 'run_local_explanation'),
    'immutable records': ('src/dragonhydra/cognition/memory.py', None),
    'receipt chronology': ('src/dragonhydra/cognition/memory.py', None),
    'per-match history': ('src/dragonhydra/system_workflow.py', 'read_cognition_history'),
    'Brier score': ('src/dragonhydra/cognition/evaluation.py', 'evaluate_forecast'),
    'log loss': ('src/dragonhydra/cognition/evaluation.py', 'evaluate_forecast'),
    'chronological evaluation': ('src/dragonhydra/cognition/evaluation.py', 'cli_observed_evaluation'),
    'workspace client': ('client/desktop', None),
    'official external opener': ('client/desktop', None),
    'launcher pairing': ('packaging/windows/workstation', None),
    'retained sports client': ('android/dragonhydra_mobile', None),
    'explicit endpoint pairing': ('android/dragonhydra_mobile', None),
    'retained application records': ('src/dragonhydra/product.py', None),
    'durable jobs': ('src/dragonhydra/jobs.py', None),
    'Joomla database transport': ('packaging/windows/workstation/Workstation.ps1', None),
    'source documents': ('src/dragonhydra/public_results.py', None),
    'acquisition receipts': ('src/dragonhydra/connectors/store.py', None),
    'leases': ('src/dragonhydra/jobs.py', 'read_job'),
    'idempotent submission': ('src/dragonhydra/jobs.py', 'create_export'),
    'owned results': ('src/dragonhydra/jobs.py', 'read_job'),
    'exports': ('src/dragonhydra/jobs.py', 'create_export'),
    'configured schedule dispatch': ('src/dragonhydra/connectors/service.py', 'internal_scheduler'),
    'owned child supervision': ('packaging/windows/workstation/Workstation.ps1', 'internal_supervisor'),
    'bounded passive heartbeat': ('packaging/windows/workstation/Workstation.ps1', 'internal_supervisor'),
}


class Schema(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)


class ConfigurationRequirement(Schema):
    reference: str
    required: bool = True
    description: str


class Operation(Schema):
    operation_id: str = Field(pattern=r'^[a-z][a-z0-9_]{1,79}$')
    label: str
    kind: Literal['http', 'cli', 'internal']
    reference: str
    read_only: bool
    required_role: Literal['reader', 'admin']


def _op(operation_id, label, reference, *, read_only=True, role='reader', kind='http'):
    return Operation(operation_id=operation_id, label=label, kind=kind,
                     reference=reference, read_only=read_only, required_role=role)


OPERATIONS = {op.operation_id: op for op in (
    _op('read_modules', 'Refresh module status', 'GET /dragon/api/v1/system/modules'),
    _op('read_system', 'Read system information', 'GET /dragon/api/v1/system'),
    _op('read_matches', 'Browse retained matches', 'GET /dragon/api/v1/matches'),
    _op('read_teams', 'Browse retained teams', 'GET /dragon/api/v1/teams'),
    _op('read_competitions', 'Browse retained competitions', 'GET /dragon/api/v1/competitions'),
    _op('read_connections', 'Read provider status', 'GET /dragon/api/v1/connections'),
    _op('read_predictions', 'Calculate a current statistical prior', 'GET /dragon/api/v1/matches/{match_id}/predictions'),
    _op('read_analysis_package', 'Read supported analysis', 'GET /dragon/api/v1/matches/{match_id}/analysis-package'),
    _op('read_odds', 'Read retained odds', 'GET /dragon/api/v1/matches/{match_id}/odds'),
    _op('read_cognition_history', 'Read persisted cognition', 'GET /dragon/api/v1/matches/{match_id}/cognition-history'),
    _op('create_forecast', 'Persist a prospective forecast', 'POST /dragon/api/v1/matches/{match_id}/forecasts', read_only=False, role='admin'),
    _op('evaluate_forecast', 'Evaluate later retained outcomes', 'POST /dragon/api/v1/matches/{match_id}/evaluations', read_only=False, role='admin'),
    _op('read_job', 'Read an owned job', 'GET /dragon/api/v1/jobs/{job_id}'),
    _op('create_export', 'Create an owned export', 'POST /dragon/api/v1/exports', read_only=False),
    _op('download_export', 'Download an owned export', 'GET /dragon/api/v1/exports/{job_id}/download'),
    _op('configure_local_ai', 'Configure optional local AI', 'PUT /dragon/api/v1/local-model/configuration', read_only=False, role='admin'),
    _op('run_local_explanation', 'Run an optional local explanation', 'POST /dragon/api/v1/matches/{match_id}/local-explanations', read_only=False),
    _op('cli_memory_history', 'Inspect cognitive history through CLI', 'dragon memory', kind='cli', read_only=False, role='admin'),
    _op('cli_observed_evaluation', 'Evaluate observed outcomes through CLI', 'dragon evaluate', kind='cli', read_only=False, role='admin'),
    _op('internal_market_signals', 'Market probability calculations', 'dragonhydra.market_signals.convert_odds', kind='internal'),
    _op('internal_public_retention', 'Retain a verified public acquisition', 'dragonhydra.public_results.ingest_bytes', kind='internal', read_only=False, role='admin'),
    _op('internal_cognitive_forecast', 'Compute a bounded statistical forecast', 'dragonhydra.cognition.models.forecast', kind='internal'),
    _op('internal_scheduler', 'Run configured due schedules', 'dragonhydra.connectors.service.Connections.schedule_due', kind='internal', read_only=False, role='admin'),
    _op('internal_supervisor', 'Observe owned workstation children', 'packaging/windows/workstation/Workstation.ps1', kind='internal'),
)}


class ModuleDefinition(Schema):
    schema_version: Literal[1] = 1
    module_id: str = Field(pattern=r'^[a-z][a-z0-9_]{1,79}$')
    display_name: str
    kind: Literal['service', 'engine', 'client', 'storage', 'scheduler', 'supervisor']
    category: Literal['infra', 'data', 'odds_prediction', 'optional_ai', 'memory_evaluation']
    description: str
    implementation_reference: tuple[str, ...]
    actual_build_or_module_version: str
    required_for_core: bool = False
    required_dependencies: tuple[str, ...] = ()
    optional_dependencies: tuple[str, ...] = ()
    implemented_capabilities: tuple[str, ...]
    configuration_requirements: tuple[ConfigurationRequirement, ...] = ()
    supported_operations: tuple[Operation, ...] = ()
    data_domains: tuple[str, ...] = ()
    verification_refs: tuple[str, ...] = ()


class RegistryDefinitions(Schema):
    schema_version: Literal[1] = 1
    modules: tuple[ModuleDefinition, ...]

    @model_validator(mode='after')
    def references_are_implemented_and_acyclic(self):
        ids = [module.module_id for module in self.modules]
        if len(set(ids)) != len(ids):
            raise ValueError('DUPLICATE_MODULE_ID')
        graph = {}
        for module in self.modules:
            required, optional = set(module.required_dependencies), set(module.optional_dependencies)
            if (len(required) != len(module.required_dependencies) or
                    len(optional) != len(module.optional_dependencies) or required & optional):
                raise ValueError('DUPLICATE_DEPENDENCY')
            if (required | optional) - set(ids):
                raise ValueError('UNKNOWN_DEPENDENCY')
            graph[module.module_id] = required | optional
            if any(req.reference not in CONFIGURATION_REFERENCES for req in module.configuration_requirements):
                raise ValueError('UNKNOWN_CONFIGURATION_REFERENCE')
            operation_ids = [op.operation_id for op in module.supported_operations]
            if len(set(operation_ids)) != len(operation_ids):
                raise ValueError('DUPLICATE_OPERATION')
            if any(OPERATIONS.get(op.operation_id) != op for op in module.supported_operations):
                raise ValueError('UNIMPLEMENTED_OPERATION_CLAIM')
            if len(set(module.implemented_capabilities)) != len(module.implemented_capabilities):
                raise ValueError('DUPLICATE_CAPABILITY')
            for capability in module.implemented_capabilities:
                owner = CAPABILITY_REFERENCES.get(capability)
                if (not owner or owner[0] not in module.implementation_reference or
                        (owner[1] and owner[1] not in operation_ids)):
                    raise ValueError('UNIMPLEMENTED_CAPABILITY_CLAIM')
        visiting, visited = set(), set()

        def visit(module_id):
            if module_id in visiting:
                raise ValueError('DEPENDENCY_CYCLE')
            if module_id in visited:
                return
            visiting.add(module_id)
            for dependency in graph[module_id]:
                visit(dependency)
            visiting.remove(module_id)
            visited.add(module_id)

        for module_id in ids:
            visit(module_id)
        return self


def _definition(module_id, name, kind, category, description, references, capabilities,
                *, required=(), optional=(), config=(), operations=(), domains=(),
                core=False, version=VERSION, tests=()):
    return ModuleDefinition(
        module_id=module_id, display_name=name, kind=kind, category=category,
        description=description, implementation_reference=tuple(references),
        actual_build_or_module_version=version, required_for_core=core,
        required_dependencies=tuple(required), optional_dependencies=tuple(optional),
        implemented_capabilities=tuple(capabilities),
        configuration_requirements=tuple(ConfigurationRequirement(
            reference=item[0], description=item[1], required=item[2] if len(item) == 3 else True)
                                         for item in config),
        supported_operations=tuple(OPERATIONS[key] for key in operations),
        data_domains=tuple(domains), verification_refs=tuple(tests))


DEFINITIONS = RegistryDefinitions(modules=(
    _definition('web_server', 'Apache and PHP', 'service', 'infra',
                'Loopback web serving and PHP execution observed by the owning workstation supervisor.',
                ['packaging/windows/workstation/Workstation.ps1'], ['serve Joomla HTTP requests'],
                optional=['supervisor'], config=[('workstation.apache', 'Owned Apache configuration')], version='external-runtime-unverified'),
    _definition('administration', 'Joomla administration', 'service', 'infra',
                'Existing Joomla administrator and DRAGONHYDRA component; anonymous reachability is not administrator authentication.',
                ['server/joomla/com_dragonhydra/admin'], ['component administration', 'server-side signed bridge'],
                required=['web_server', 'storage_mariadb', 'api_server'],
                config=[('workstation.joomla', 'Installed Joomla and component configuration')],
                operations=['read_modules'], domains=['administration'], version='0.4.1-dev.3'),
    _definition('website', 'Joomla sports workspace', 'service', 'infra',
                'Permission-protected Joomla-native retained sports views.',
                ['server/joomla/com_dragonhydra/site'], ['workspace navigation', 'retained sports views'],
                required=['web_server', 'storage_mariadb', 'api_server'],
                config=[('workstation.joomla', 'Installed Joomla site and Home menu')],
                operations=['read_matches', 'read_teams', 'read_competitions'], domains=['football'], version='0.4.1-dev.3'),
    _definition('api_server', 'Application API', 'service', 'infra',
                'Authenticated loopback FastAPI API using the selected installation state.',
                ['src/dragonhydra/api.py', 'src/dragonhydra/server.py'], ['local pairing', 'signed Joomla bridge', 'typed read operations'],
                required=['storage_sqlite'], optional=['supervisor'], core=True,
                operations=['read_modules', 'read_system'], tests=['tests/test_module_registry.py', 'tests/test_product_api.py']),
    _definition('data_engine', 'Retained data and connectors', 'engine', 'data',
                'Source-scoped retained observations and explicit provider acquisition workflows; status does not contact providers.',
                ['src/dragonhydra/public_results.py', 'src/dragonhydra/connectors'], ['retained fixtures', 'source identity', 'provider adapters'],
                required=['storage_sqlite', 'evidence_store'], config=[('product.provider_settings', 'Optional provider settings and protected credentials', False)],
                operations=['read_matches', 'read_teams', 'read_competitions', 'read_connections', 'internal_public_retention'], domains=['football', 'provider_observations']),
    _definition('odds_engine', 'Odds intelligence', 'engine', 'odds_prediction',
                'Implemented market mathematics and retained odds views; no claim of available live odds.',
                ['src/dragonhydra/market_signals.py', 'src/dragonhydra/product.py'], ['odds conversion', 'retained market history'],
                required=['data_engine'], operations=['read_odds', 'internal_market_signals'], domains=['odds'], version='market-signals/1'),
    _definition('prediction_engine', 'Statistical prediction', 'engine', 'odds_prediction',
                'Existing statistical models and explicitly requested prospective immutable forecasts.',
                ['src/dragonhydra/cognition/models.py', 'src/dragonhydra/system_workflow.py'], ['frequency', 'poisson_goals', 'elo', 'recency', 'ensemble'],
                required=['data_engine'], optional=['memory_engine'],
                operations=['read_predictions', 'read_analysis_package', 'create_forecast', 'internal_cognitive_forecast'], domains=['predictions'], version='football-models/1'),
    _definition('ai_engine', 'Optional local AI', 'engine', 'optional_ai',
                'Optional constrained local explanation; configuration presence does not prove model runtime availability.',
                ['src/dragonhydra/local_ai.py', 'src/dragonhydra/local_ai_settings.py'], ['constrained source-fact explanations'],
                required=['api_server'], config=[('product.local_ai', 'Optional loopback model endpoint and protected key')],
                operations=['configure_local_ai', 'run_local_explanation'], domains=['explanations']),
    _definition('memory_engine', 'Immutable cognitive memory', 'engine', 'memory_evaluation',
                'Append-only cognitive model, prediction, outcome and evaluation records in the selected SQLite store.',
                ['src/dragonhydra/cognition/memory.py', 'src/dragonhydra/system_workflow.py'], ['immutable records', 'receipt chronology', 'per-match history'],
                required=['storage_sqlite'], config=[('cognition.memory', 'Initialized cognitive schema; created only by explicit workflows')],
                operations=['read_cognition_history', 'cli_memory_history'], domains=['model_runs', 'predictions', 'outcomes', 'evaluations'], version='cognitive-memory/1'),
    _definition('evaluation_engine', 'Observed outcome evaluation', 'engine', 'memory_evaluation',
                'Scores genuine later outcomes against persisted prospective forecasts; unscored records remain unscored.',
                ['src/dragonhydra/cognition/evaluation.py', 'src/dragonhydra/system_workflow.py'], ['Brier score', 'log loss', 'chronological evaluation'],
                required=['memory_engine', 'data_engine'],
                operations=['read_cognition_history', 'evaluate_forecast', 'cli_observed_evaluation'], domains=['evaluations'], version='cognitive-evaluation/1'),
    _definition('windows_desktop', 'Windows desktop client', 'client', 'infra',
                'Tauri client and official workstation launcher; this API does not observe interactive desktop sessions.',
                ['client/desktop', 'packaging/windows/workstation'], ['workspace client', 'official external opener', 'launcher pairing'],
                required=['api_server'], config=[('workstation.launcher', 'Installed launcher and owner pairing metadata')]),
    _definition('android_client', 'Android client', 'client', 'infra',
                'Flutter Android client; source and APK evidence do not establish an attached, paired device.',
                ['android/dragonhydra_mobile'], ['retained sports client', 'explicit endpoint pairing'],
                required=['api_server'], config=[('android.endpoint_pairing', 'User-owned endpoint and protected device pairing')], version='0.4.0-alpha.1+4'),
    _definition('storage_sqlite', 'Application SQLite store', 'storage', 'data',
                'Authoritative retained application and job store for this selected installation.',
                ['src/dragonhydra/product.py', 'src/dragonhydra/jobs.py'], ['retained application records', 'durable jobs'],
                config=[('product.sqlite', 'Existing selected SQLite file')], core=True, domains=['retained_records', 'jobs']),
    _definition('storage_mariadb', 'Joomla MariaDB store', 'storage', 'infra',
                'Separate Joomla storage; a supervisor TCP observation does not prove SQL authentication or schema health.',
                ['packaging/windows/workstation/Workstation.ps1'], ['Joomla database transport'],
                optional=['supervisor'], config=[('workstation.mariadb', 'Owned Joomla MariaDB configuration')], version='external-runtime-unverified'),
    _definition('evidence_store', 'Retained source evidence', 'storage', 'data',
                'Original source documents retained inside the selected SQLite store.',
                ['src/dragonhydra/public_results.py', 'src/dragonhydra/connectors/store.py'], ['source documents', 'acquisition receipts'],
                required=['storage_sqlite'], config=[('product.retained_evidence', 'Retained source-document tables')], domains=['raw_documents', 'receipts']),
    _definition('durable_jobs', 'Durable job worker', 'service', 'infra',
                'Existing lease-based worker for explicit application jobs, with bounded passive queue observations.',
                ['src/dragonhydra/jobs.py'], ['leases', 'idempotent submission', 'owned results', 'exports'],
                required=['storage_sqlite'], config=[('product.jobs', 'Existing job schema'), ('product.worker', 'Running application worker')], core=True,
                operations=['read_job', 'create_export', 'download_export'], domains=['jobs']),
    _definition('scheduler', 'Provider schedule dispatcher', 'scheduler', 'infra',
                'The existing durable worker dispatches configured due provider schedules; status never triggers a schedule.',
                ['src/dragonhydra/jobs.py', 'src/dragonhydra/connectors/service.py'], ['configured schedule dispatch'],
                required=['durable_jobs', 'data_engine'], config=[('product.provider_settings', 'Explicit nonzero provider schedule intervals')],
                operations=['internal_scheduler']),
    _definition('supervisor', 'Workstation supervisor', 'supervisor', 'infra',
                'Existing workstation service controller and short-lived passive child observations.',
                ['packaging/windows/workstation/Workstation.ps1'], ['owned child supervision', 'bounded passive heartbeat'],
                config=[('workstation.observer', 'Current instance-bound supervisor heartbeat')], operations=['internal_supervisor']),
))


class Observation(Schema):
    installation_id: str
    module_id: str
    observed_at: str
    implementation_state: Literal['implemented', 'not_implemented']
    configuration_state: Literal['configured', 'not_configured', 'not_required', 'unknown', 'invalid']
    runtime_state: RuntimeState
    last_success_at: str | None
    evidence_expires_at: str
    reason_code: str
    reason: str
    sanitized_metrics: dict[str, bool | int | float | str]
    evidence_reference: tuple[str, ...]

    @model_validator(mode='after')
    def safe_metrics(self):
        if set(self.sanitized_metrics) - METRIC_KEYS:
            raise ValueError('UNKNOWN_METRIC')
        for key, value in self.sanitized_metrics.items():
            if isinstance(value, float) and not math.isfinite(value):
                raise ValueError('NONFINITE_METRIC')
            if isinstance(value, str) and (key != 'api_version' or value != VERSION):
                raise ValueError('UNSAFE_STRING_METRIC')
        return self


def _stamp(value):
    return value.astimezone(timezone.utc).isoformat(timespec='microseconds').replace('+00:00', 'Z')


def _clock(value):
    if not isinstance(value, str) or len(value) > 40:
        raise ValueError('INVALID_CLOCK')
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        raise ValueError('INVALID_CLOCK')
    return parsed.astimezone(timezone.utc)


def _json_file(path, limit):
    # Read one bounded snapshot; atomic producer replacement avoids torn data.
    with Path(path).open('rb') as stream:
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise ValueError('OBSERVATION_TOO_LARGE')
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError('INVALID_OBSERVATION')
    return data


def _supervisor_receipt(state, at, process_id):
    """Only current, matching supervisor evidence can attest external services."""
    path = state.parent / 'status.json'
    try:
        data = _json_file(path, 65536)
        if data.get('schema_version') != 2 or data.get('observer') != 'workstation-supervisor':
            return {}, 'SUPERVISOR_UNVERIFIED', None
        endpoint = _json_file(state / 'endpoint.json', 4096)
        address = data.get('api_url')
        if (not isinstance(address, str) or
                not re.fullmatch(r'http://127\.0\.0\.1:[0-9]{1,5}', address) or
                not 1 <= int(address.rsplit(':', 1)[1]) <= 65535):
            return {}, 'SUPERVISOR_INSTANCE_MISMATCH', None
        observations = data.get('observations', {})
        api_pid = observations.get('api_server', {}).get('sanitized_metrics', {}).get('pid')
        if (endpoint.get('url') != address or type(endpoint.get('pid')) is not int or
                endpoint['pid'] != process_id or type(api_pid) is not int or api_pid != process_id):
            return {}, 'SUPERVISOR_INSTANCE_MISMATCH', None
        observed, expires = _clock(data.get('observed_at')), _clock(data.get('evidence_expires_at'))
        if observed > at + timedelta(seconds=5) or not 0 < (expires-observed).total_seconds() <= 90:
            return {}, 'SUPERVISOR_CLOCK_INVALID', None
        if expires <= at:
            return {}, 'EVIDENCE_EXPIRED', (observed, expires)
        allowed = {'api_server', 'web_server', 'administration', 'website', 'storage_mariadb', 'supervisor'}
        receipts = {}
        for module_id in allowed:
            item = observations.get(module_id)
            if not isinstance(item, dict) or item.get('runtime_state') not in ('ready', 'degraded', 'unavailable', 'configured_unverified'):
                continue
            metrics = item.get('sanitized_metrics', {})
            if not isinstance(metrics, dict):
                continue
            metrics = {key: value for key, value in metrics.items()
                       if key in METRIC_KEYS and isinstance(value, (bool, int, float))
                       and (not isinstance(value, float) or math.isfinite(value))}
            # Interpret only known state, never echo producer free text/errors.
            success = _clock(item['last_success_at']) if item.get('last_success_at') else None
            if success and success > observed:
                continue
            if item['runtime_state'] == 'ready' and (success is None or (observed-success).total_seconds() > 90):
                continue
            receipts[module_id] = (item['runtime_state'], observed, expires, metrics, success)
        return receipts, 'SUPERVISOR_OBSERVED', (observed, expires)
    except FileNotFoundError:
        return {}, 'SUPERVISOR_UNVERIFIED', None
    except (OSError, UnicodeError, ValueError, TypeError, AttributeError, OverflowError):
        return {}, 'SUPERVISOR_EVIDENCE_INVALID', None


def _store_observation(path, *, deadline_seconds=.25):
    """No Product/Store constructors, schema initialization or read-write open."""
    metrics, tables = {}, set()
    try:
        deadline = time.monotonic() + deadline_seconds
        with closing(sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro', uri=True, timeout=.1)) as db:
            db.execute('PRAGMA query_only=ON')
            db.set_progress_handler(lambda: int(time.monotonic() > deadline), 1000)
            tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            metrics['table_count'] = len(tables)
            metrics['core_store_ready'] = ('product_schema' in tables and
                db.execute('SELECT version FROM product_schema').fetchone() == (1,))
            # Counts mean retained versions/observations, not current distinct fixtures.
            for table, metric in (('public_fixture_records', 'retained_fixture_versions'),
                                  ('connector_observations', 'connector_observations'),
                                  ('raw_sources', 'raw_documents'), ('cognitive_records', 'cognitive_records')):
                if table in tables:
                    metrics[metric] = db.execute('SELECT COUNT(*) FROM '+table).fetchone()[0]
            if 'cognitive_records' in tables:
                for kind, count in db.execute("SELECT kind,COUNT(*) FROM cognitive_records WHERE kind IN ('prediction','outcome','evaluation') GROUP BY kind"):
                    metrics[kind+'_records'] = count
            if 'connector_settings' in tables:
                metrics['enabled_schedules'] = db.execute('SELECT COUNT(*) FROM connector_settings WHERE interval_seconds>0').fetchone()[0]
            if 'product_jobs' in tables:
                counts = dict(db.execute("SELECT status,COUNT(*) FROM product_jobs WHERE status IN ('queued','running') GROUP BY status"))
                metrics.update(queued_jobs=counts.get('queued', 0), running_jobs=counts.get('running', 0))
                metrics['stale_running_jobs'] = db.execute("SELECT COUNT(*) FROM product_jobs WHERE status='running' AND (lease_until IS NULL OR lease_until<?)", (time.time(),)).fetchone()[0]
            return tables, metrics, 'STORE_READABLE'
    except (OSError, sqlite3.Error, ValueError):
        # Raw database exceptions can contain private paths; only a fixed reason escapes.
        return tables, metrics, 'STORE_READ_UNAVAILABLE'


def snapshot(product, jobs, *, at=None, process_id=None, role='reader'):
    """Return a fresh nonpersisted status without triggering any application work."""
    at = at or datetime.now(timezone.utc)
    if at.tzinfo is None:
        raise ValueError('UTC_CLOCK_REQUIRED')
    process_id = os.getpid() if process_id is None else process_id
    state = Path(product.state)
    installation_id = 'local-'+hashlib.sha256(str(state.resolve()).encode()).hexdigest()[:16]
    tables, metrics, store_reason = _store_observation(product.db_path)
    store_ok = store_reason == 'STORE_READABLE' and metrics.get('core_store_ready', False)
    receipts, supervisor_reason, supervisor_clocks = _supervisor_receipt(state, at, process_id)
    expires = at + timedelta(seconds=30)
    worker_alive = bool(jobs.thread and jobs.thread.is_alive() and not jobs.stop.is_set())
    observations = {}

    def observe(module_id, runtime_state, reason_code, reason, *, configuration='configured',
                values=None, refs=(), observed=None, expiry=None, last_success=None):
        observed = observed or at
        expiry = expiry or expires
        observations[module_id] = Observation(
            installation_id=installation_id, module_id=module_id,
            observed_at=_stamp(observed), implementation_state='implemented',
            configuration_state=configuration, runtime_state=runtime_state,
            last_success_at=_stamp(last_success or observed) if runtime_state == 'ready' else
                            _stamp(last_success) if last_success else None,
            evidence_expires_at=_stamp(expiry), reason_code=reason_code, reason=reason,
            sanitized_metrics=values or {}, evidence_reference=tuple(refs))

    observe('api_server', 'ready', 'CURRENT_AUTHENTICATED_REQUEST',
            'This authenticated API handler executed in the current kernel; other modules are assessed independently.',
            values={'process_id': process_id, 'api_version': VERSION}, refs=['runtime:authenticated-module-status'])
    observe('storage_sqlite', 'ready' if store_ok else 'unavailable', store_reason,
            'The selected application schema was read using a bounded read-only connection.' if store_ok else
            'The selected application store could not be verified by a bounded read-only query.',
            configuration='configured' if store_ok else 'unknown', values={key: metrics[key] for key in ('table_count', 'core_store_ready') if key in metrics}, refs=['sqlite:read-only-schema'])
    worker_state = ('degraded' if metrics.get('stale_running_jobs', 0) else 'ready') if worker_alive and store_ok else 'unavailable'
    observe('durable_jobs', worker_state, 'WORKER_OBSERVED' if worker_state == 'ready' else 'WORKER_UNAVAILABLE_OR_STALE',
            'The existing worker thread is alive and queue leases were inspected without dispatching jobs.' if worker_state == 'ready' else
            'The worker or store is unavailable, or a running lease is stale; no recovery was triggered.',
            values={**{key: metrics[key] for key in ('queued_jobs', 'running_jobs', 'stale_running_jobs') if key in metrics}, 'worker_alive': worker_alive}, refs=['runtime:existing-worker-thread', 'sqlite:job-aggregates'])
    for module_id in ('web_server', 'administration', 'website', 'storage_mariadb', 'supervisor'):
        if module_id in receipts:
            status, observed, expiry, values, last_success = receipts[module_id]
            reason = {'web_server': 'The owning supervisor observed the configured loopback Apache/PHP HTTP route.',
                      'administration': 'The owning supervisor observed the Joomla administrator entry page; authenticated administrator use is a separate acceptance test.',
                      'website': 'The owning supervisor observed the Joomla root response and component presentation marker.',
                      'storage_mariadb': 'The owning supervisor observed the configured database TCP listener and Joomla response; SQL permissions and schema integrity were not directly tested.',
                      'supervisor': 'The current instance-bound supervisor heartbeat is fresh.'}[module_id]
            if status != 'ready':
                reason = 'The current instance-bound supervisor did not verify this service as ready.'
            observe(module_id, status, 'SUPERVISOR_'+status.upper(), reason, values=values,
                    refs=['supervisor:'+module_id], observed=observed, expiry=expiry, last_success=last_success)
        else:
            observe(module_id, 'configured_unverified', supervisor_reason,
                    'No fresh, instance-bound supervisor observation verifies this external service.',
                    configuration='unknown', refs=['supervisor:passive-heartbeat'],
                    observed=supervisor_clocks[0] if supervisor_clocks else None,
                    expiry=supervisor_clocks[1] if supervisor_clocks else None)
    data_ok = store_ok and {'public_fixture_records', 'connector_observations'} <= tables
    observe('data_engine', 'ready' if data_ok else 'unavailable', 'RETAINED_STORE_READABLE' if data_ok else 'RETAINED_STORE_UNVERIFIED',
            'Retained data tables are readable; provider reachability and live synchronization were not tested.',
            values={key: metrics[key] for key in ('retained_fixture_versions', 'connector_observations') if key in metrics}, refs=['sqlite:retained-table-aggregates'])
    evidence_ok = store_ok and 'raw_sources' in tables
    observe('evidence_store', 'ready' if evidence_ok else 'unavailable', 'EVIDENCE_STORE_READABLE' if evidence_ok else 'EVIDENCE_STORE_UNVERIFIED',
            'Retained source-document storage is readable; record counts are not a content-integrity audit.',
            values={key: metrics[key] for key in ('raw_documents',) if key in metrics}, refs=['sqlite:source-document-count'])
    for module_id in ('odds_engine', 'prediction_engine'):
        observe(module_id, 'configured_unverified' if data_ok else 'unavailable', 'EXECUTION_NOT_REQUESTED',
                'Implemented calculation entry points are available; status refresh did not run a calculation or assert a successful model result.', refs=['definition:implemented-operations'])
    has_memory = store_ok and {'cognitive_records', 'cognitive_receipts'} <= tables
    observe('memory_engine', 'ready' if has_memory else 'installed_not_configured',
            'COGNITIVE_STORE_READABLE' if has_memory else 'COGNITIVE_SCHEMA_NOT_INITIALIZED',
            'Existing cognitive record tables are readable; immutability and prediction validity are verified by separate workflow tests.' if has_memory else
            'Cognitive memory is implemented but this installation has not initialized its schema; a read does not create it.',
            configuration='configured' if has_memory else 'not_configured',
            values={key: metrics[key] for key in ('cognitive_records', 'prediction_records', 'outcome_records', 'evaluation_records') if key in metrics}, refs=['sqlite:cognitive-schema-guard'])
    observe('evaluation_engine', 'configured_unverified' if has_memory else 'installed_not_configured', 'EVALUATION_NOT_REQUESTED',
            'Evaluation is implemented. This status read did not attach outcomes, score forecasts, or claim a performance result.',
            configuration='configured' if has_memory else 'not_configured', values={'evaluation_records': metrics.get('evaluation_records', 0)}, refs=['definition:observed-evaluation'])
    try:
        from .local_ai_settings import Settings
        configured = bool(Settings(state).public()['configured'])
        observe('ai_engine', 'configured_unverified' if configured else 'installed_not_configured',
                'OPTIONAL_AI_NOT_PROBED' if configured else 'OPTIONAL_AI_NOT_CONFIGURED',
                'Optional model configuration presence was inspected without reading a key or contacting a model. Core retained-data operations are independent.',
                configuration='configured' if configured else 'not_configured', values={'configured': configured}, refs=['configuration:local-ai-presence'])
    except (OSError, ValueError, RuntimeError, LocalAIError):
        observe('ai_engine', 'unavailable', 'OPTIONAL_AI_SETTINGS_INVALID',
                'Optional local model settings are invalid or unavailable; core retained-data operations are independent.', configuration='invalid', refs=['configuration:local-ai-presence'])
    for module_id in ('windows_desktop', 'android_client'):
        observe(module_id, 'configured_unverified', 'CLIENT_SESSION_NOT_OBSERVED',
                'The client implementation exists; this API has no current evidence of an installed, running, paired client.',
                configuration='unknown', refs=['definition:client-implementation'])
    schedules = metrics.get('enabled_schedules', 0)
    observe('scheduler', ('ready' if worker_alive else 'unavailable') if schedules else 'not_applicable',
            'SCHEDULE_DISPATCHER_OBSERVED' if schedules else 'NO_ENABLED_SCHEDULES',
            'Enabled schedules exist and the existing worker state was inspected without running them.' if schedules else
            'No enabled provider schedules are present; no schedule was created or dispatched.',
            configuration='configured' if schedules else 'not_required', values={'enabled_schedules': schedules, 'worker_alive': worker_alive}, refs=['sqlite:schedule-configuration', 'runtime:existing-worker-thread'])
    # A process can answer while one of its essential dependencies has failed.
    # Keep its direct evidence, but do not present the dependent module as ready.
    for _ in range(len(DEFINITIONS.modules)):
        changed = False
        for definition in DEFINITIONS.modules:
            observation = observations[definition.module_id]
            if observation.runtime_state == 'ready' and any(
                    observations[key].runtime_state != 'ready'
                    for key in definition.required_dependencies):
                observations[definition.module_id] = observation.model_copy(update={
                    'runtime_state': 'degraded', 'reason_code': 'REQUIRED_DEPENDENCY_UNVERIFIED',
                    'reason': 'Direct module evidence exists, but a required dependency is not verified ready.'})
                changed = True
        if not changed:
            break
    entries = []
    for definition in DEFINITIONS.modules:
        observation = observations[definition.module_id]
        operations = []
        for operation in definition.supported_operations:
            permission = operation.required_role == 'reader' or role == 'admin'
            usable = observation.runtime_state not in ('not_implemented', 'unavailable')
            # Reads can explain empty/uninitialized data. Explicit writes still use
            # their existing route checks and owned-job authorization when invoked.
            available = permission and usable and operation.kind == 'http'
            operations.append({**operation.model_dump(), 'available': available,
                               'reason': 'Use the existing authenticated operation; its own checks apply.' if available else
                               'Administrator permission is required.' if not permission else
                               'This is an internal or CLI entry point; it is not an HTTP control action.' if operation.kind != 'http' else
                               'The module is not currently available.'})
        dependencies = [{'module_id': key, 'required': required,
                         'runtime_state': observations[key].runtime_state}
                        for required, keys in ((True, definition.required_dependencies), (False, definition.optional_dependencies))
                        for key in keys]
        entries.append({'definition': definition.model_dump(mode='json'),
                        'observation': observation.model_dump(mode='json'),
                        'dependencies': dependencies, 'operations': operations})
    counts = Counter(observation.runtime_state for observation in observations.values())
    core = [observations[definition.module_id].runtime_state for definition in DEFINITIONS.modules if definition.required_for_core]
    core_state = 'ready' if all(status == 'ready' for status in core) else 'unavailable' if all(status == 'unavailable' for status in core) else 'degraded'
    return {'schema_version': 1, 'registry_version': REGISTRY_VERSION, 'as_of': _stamp(at),
            'installation_id': installation_id, 'core_state': core_state,
            'summary': {'total_modules': len(entries), 'counts': {state: counts.get(state, 0) for state in STATES},
                        'core_required': len(core), 'core_ready': core.count('ready')},
            'modules': entries, 'read_only': True, 'network_probes': False}
