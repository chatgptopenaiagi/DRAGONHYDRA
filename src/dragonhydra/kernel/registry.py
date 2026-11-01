"""Validated composition graph and cached health; metadata is not execution proof."""
from dataclasses import asdict
from datetime import timedelta
from threading import RLock

from .contracts import Observation, STATES, iso, utc_now


class ModuleRegistry:
    def __init__(self, definitions, engines, *, ttl_seconds=300, clock=utc_now, disabled=(), installation_id=''):
        self.definitions = {item.id: item for item in definitions}
        if len(self.definitions) != len(definitions):
            raise ValueError('DUPLICATE_MODULE_ID')
        if set(engines) != set(self.definitions):
            raise ValueError('MODULE_ENGINE_BINDING_MISMATCH')
        self.engines = dict(engines)
        for item in definitions:
            if item.schema_version != 'core-next.module/1':
                raise ValueError('MODULE_SCHEMA_VERSION_MISMATCH')
            if getattr(self.engines[item.id], 'contract_version', None) != 'core-next.engine/1':
                raise ValueError('ENGINE_CONTRACT_VERSION_MISMATCH')
            operations = dict(item.capability_operations)
            if (set(operations) != set(item.capabilities) or
                    any(set(value)-set(item.supported_operations) for value in operations.values())):
                raise ValueError('UNSUPPORTED_MODULE_CAPABILITY_OPERATION')
            if any(not callable(getattr(self.engines[item.id], op, None)) for op in item.supported_operations):
                raise ValueError('MODULE_OPERATION_IMPLEMENTATION_MISSING')
            dependencies = dict(item.capability_dependencies)
            if (set(dependencies)-set(item.capabilities) or
                    any(set(value)-set(item.dependencies+item.optional_dependencies) for value in dependencies.values())):
                raise ValueError('UNDECLARED_CAPABILITY_DEPENDENCY')
        self.disabled = frozenset(disabled)
        if self.disabled - self.definitions.keys():
            raise ValueError('UNKNOWN_DISABLED_MODULE')
        if type(ttl_seconds) is not int or not 1 <= ttl_seconds <= 3600:
            raise ValueError('INVALID_OBSERVATION_TTL')
        self.ttl, self.clock, self.lock = ttl_seconds, clock, RLock()
        self.installation_id = installation_id
        self._order = []
        visiting, visited = set(), set()
        def visit(identifier):
            if identifier in visiting:
                raise ValueError('MODULE_DEPENDENCY_CYCLE')
            if identifier in visited:
                return
            visiting.add(identifier)
            for dependency in self.definitions[identifier].dependencies:
                if dependency not in self.definitions:
                    raise ValueError('UNKNOWN_MODULE_DEPENDENCY')
                visit(dependency)
            visiting.remove(identifier)
            visited.add(identifier)
            self._order.append(identifier)
        for identifier in self.definitions:
            visit(identifier)
        self.observations = {}
        self.last_operations = {}
        self.running = False

    def record(self, identifier, state, reason, *, metrics=None, evidence=()):
        if identifier not in self.definitions:
            raise LookupError('MODULE_NOT_FOUND')
        at = self.clock()
        with self.lock:
            previous = self.observations.get(identifier)
            combined = {**(dict(previous.metrics) if previous else {}), **dict(metrics or {})}
            sampled = at if metrics is not None else previous.metrics_sampled_at if previous else None
            last_success = at if state == 'READY' else previous.last_success if previous else None
            value = Observation(state, reason, at, at+timedelta(seconds=self.ttl), combined,
                                tuple(evidence), self.installation_id, identifier, last_success, sampled)
            self.observations[identifier] = value

    def record_operation(self, identifier, operation, state, reason, *, evidence=()):
        """Operation evidence cannot renew a separately sampled count batch."""
        self.record(identifier, state, reason, evidence=evidence)
        with self.lock:
            self.last_operations[identifier] = {'operation': operation, 'state': state,
                'observed_at': iso(self.clock()), 'evidence': list(evidence)}

    def start(self):
        with self.lock:
            if self.running:
                return
            self.running = True
        for identifier in self._order:
            self.refresh(identifier)

    def refresh(self, identifier):
        if identifier not in self.definitions:
            raise LookupError('MODULE_NOT_FOUND')
        if identifier in self.disabled:
            self.record(identifier, 'UNAVAILABLE', 'MODULE_DISABLED_BY_PROFILE')
            return
        try:
            result = self.engines[identifier].observe()
            self.record(identifier, result['state'], result['reason'],
                        metrics=result.get('metrics'), evidence=result.get('evidence', ()))
        except Exception:
            self.record(identifier, 'DEGRADED', 'BOUNDED_LOCAL_OBSERVATION_FAILED')

    def stop(self):
        with self.lock:
            self.running = False
        for identifier in reversed(self._order):
            try:
                self.engines[identifier].stop()
            except Exception:
                self.record(identifier, 'DEGRADED', 'MODULE_STOP_FAILED')
            else:
                self.record(identifier, 'STOPPED', 'KERNEL_STOPPED')

    def item(self, identifier):
        """Pure cached read: does not touch an engine, database, network or job."""
        if identifier not in self.definitions:
            raise LookupError('MODULE_NOT_FOUND')
        with self.lock:
            definition, observation = self.definitions[identifier], self.observations.get(identifier)
            if observation is None:
                state, reason = 'UNVERIFIED', 'NO_BOUNDED_OBSERVATION'
            else:
                state, reason = observation.state, observation.reason
                if state != 'STOPPED' and self.clock() >= observation.expires_at:
                    state, reason = 'EXPIRED', 'OBSERVATION_EXPIRED'
            dependencies = []
            for dependency in definition.dependencies:
                dep = self.item(dependency)
                dependencies.append({'id': dependency, 'state': dep['state'], 'reason': dep['reason']})
            if state == 'READY' and any(dep['state'] != 'READY' for dep in dependencies):
                state, reason = 'DEGRADED', 'DEPENDENCY_NOT_READY'
            def passive_state(dep):
                if dep not in self.definitions:
                    return 'NOT_IMPLEMENTED'
                if dep in self.disabled:
                    return 'UNAVAILABLE'
                value = self.observations.get(dep)
                if value is None:
                    return 'UNVERIFIED'
                return 'EXPIRED' if value.state != 'STOPPED' and self.clock() >= value.expires_at else value.state
            optional = [{'id': dep, 'state': passive_state(dep),
                         'reason': 'OPTIONAL_MODULE_MISSING' if dep not in self.definitions else 'OPTIONAL_DEPENDENCY'}
                        for dep in definition.optional_dependencies]
            capability_status = []
            for cap in definition.capabilities:
                needed = dict(definition.capability_dependencies).get(cap, ())
                missing = [dep for dep in needed if passive_state(dep) != 'READY']
                capability_status.append({'id': cap, 'available': state == 'READY' and not missing,
                    'reason': 'OPTIONAL_DEPENDENCY_MISSING_OR_DISABLED' if missing else reason,
                    'operations': list(dict(definition.capability_operations)[cap])})
            raw = {'state': observation.state, 'reason': observation.reason,
                   'metrics': dict(observation.metrics), 'evidence': list(observation.evidence)} if observation else {
                       'state': 'UNVERIFIED', 'reason': reason, 'metrics': {}, 'evidence': []}
            raw.update(installation_id=self.installation_id, module_id=identifier,
                       observed_at=iso(observation.observed_at) if observation else None,
                       expires_at=iso(observation.expires_at) if observation else None,
                       last_success=iso(observation.last_success) if observation and observation.last_success else None)
            sampled = observation.metrics_sampled_at if observation else None
            raw.update(metrics_sampled_at=iso(sampled) if sampled else None,
                metrics_expires_at=iso(sampled+timedelta(seconds=self.ttl)) if sampled else None,
                metrics_state=('EXPIRED' if self.clock() >= sampled+timedelta(seconds=self.ttl) else 'CURRENT') if sampled else 'UNVERIFIED',
                last_operation=dict(self.last_operations[identifier]) if identifier in self.last_operations else None)
            configuration_state = 'DISABLED' if identifier in self.disabled else 'UNVERIFIED'
            if identifier not in self.disabled and type(raw['metrics'].get('configured')) is bool:
                configuration_state = 'CONFIGURED' if raw['metrics']['configured'] else 'NOT_CONFIGURED'
            operation = raw['last_operation']
            runtime_state = 'UNVERIFIED'
            if state == 'STOPPED':
                runtime_state = 'STOPPED'
            elif operation is not None:
                from datetime import datetime
                at = datetime.fromisoformat(operation['observed_at'].replace('Z', '+00:00'))
                runtime_state = 'EXPIRED' if self.clock() >= at+timedelta(seconds=self.ttl) else operation['state']
            sensitive = ('secret', 'token', 'password', 'credential', 'api_key', 'private_key')
            sanitized = {k: v for k, v in raw['metrics'].items() if not any(word in k.lower() for word in sensitive)}
            canonical = {'implementation_state': 'BOUND', 'configuration_state': configuration_state,
                'runtime_state': runtime_state, 'reason_code': reason,
                'human_readable_reason': reason.replace('_', ' ').capitalize()+'.',
                'last_success_at': raw['last_success'], 'evidence_expires_at': raw['expires_at'],
                'sanitized_metrics': sanitized, 'evidence_reference': list(raw['evidence'])}
            raw.update(canonical)
            return {**asdict(definition), 'state': state, 'reason': reason,
                    **canonical, 'display_name': definition.name, 'kind': definition.origin,
                    'responsibility': definition.description, 'actual_version_or_build': definition.version,
                    'implemented_capabilities': list(definition.capabilities),
                    'optional_dependency_status': optional, 'capability_status': capability_status,
                    'required_dependencies': list(definition.dependencies),
                    'installation_id': self.installation_id, 'module_id': identifier,
                    'last_success': raw['last_success'],
                    'observed_at': iso(observation.observed_at) if observation else None,
                    'expires_at': iso(observation.expires_at) if observation else None,
                    'dependency_status': dependencies, 'observation': raw,
                    'operations': [{'id': 'status', 'label': 'Inspect module', 'method': 'GET',
                                    'path': '/modules/'+identifier, 'enabled': True, 'reason': None}]}

    def items(self):
        return [self.item(identifier) for identifier in self._order]
