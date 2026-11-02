"""Validated composition graph and cached health; metadata is not execution proof."""
from dataclasses import asdict
from datetime import timedelta
import os
import re
from threading import RLock
from uuid import uuid4

from .contracts import Observation, STATES, CONFIGURATION_REFERENCES, iso, utc_now


class ModuleRegistry:
    def __init__(self, definitions, engines, *, supporting=None, ttl_seconds=300, clock=utc_now, disabled=(), installation_id='', build_identity='source-checkout'):
        self.definitions = {item.id: item for item in definitions}
        if len(self.definitions) != len(definitions):
            raise ValueError('DUPLICATE_MODULE_ID')
        supporting = dict(supporting or {})
        if set(engines)&set(supporting) or set(engines)|set(supporting) != set(self.definitions):
            raise ValueError('MODULE_ENGINE_BINDING_MISMATCH')
        self.engines = dict(engines)
        self.supporting = supporting
        self.bindings = {**self.engines,**supporting}
        for item in definitions:
            if not re.fullmatch(r'[a-z][a-z0-9_]{0,79}',item.id):
                raise ValueError('INVALID_MODULE_ID')
            if set(item.configuration_requirements)-CONFIGURATION_REFERENCES:
                raise ValueError('UNKNOWN_CONFIGURATION_REFERENCE')
            if (len(set(item.dependencies))!=len(item.dependencies)
                    or len(set(item.optional_dependencies))!=len(item.optional_dependencies)
                    or set(item.dependencies)&set(item.optional_dependencies)):
                raise ValueError('DUPLICATE_MODULE_DEPENDENCY')
            if item.schema_version != 'core-next.module/1':
                raise ValueError('MODULE_SCHEMA_VERSION_MISMATCH')
            if item.layer not in ('engine','supporting'):
                raise ValueError('INVALID_MODULE_LAYER')
            if (item.layer=='engine') != (item.id in self.engines):
                raise ValueError('MODULE_LAYER_BINDING_MISMATCH')
            expected = 'core-next.engine/1' if item.layer=='engine' else 'core-next.support/1'
            if getattr(self.bindings[item.id], 'contract_version', None) != expected:
                raise ValueError('ENGINE_CONTRACT_VERSION_MISMATCH')
            operations = dict(item.capability_operations)
            if (set(operations) != set(item.capabilities) or
                    any(set(value)-set(item.supported_operations) for value in operations.values())):
                raise ValueError('UNSUPPORTED_MODULE_CAPABILITY_OPERATION')
            if any(not callable(getattr(self.bindings[item.id], op, None)) for op in item.supported_operations):
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
        self.build_identity = build_identity
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
        self.operation_observations = {}
        self.running = False

    def record(self, identifier, state, reason, *, metrics=None, evidence=(), observer_identity=None, verification_scope=('LIGHTWEIGHT_LOCAL_OBSERVATION',), observed_at=None, expires_at=None, last_success_at=None):
        if identifier not in self.definitions:
            raise LookupError('MODULE_NOT_FOUND')
        at = observed_at or self.clock()
        if at.utcoffset() is None or at>self.clock():raise ValueError('INVALID_OBSERVATION_CLOCK')
        expiry=expires_at or at+timedelta(seconds=self.ttl)
        if expiry.utcoffset() is None or not at<expiry<=at+timedelta(seconds=self.ttl):raise ValueError('INVALID_OBSERVATION_EXPIRY')
        with self.lock:
            previous = self.observations.get(identifier)
            if previous and previous.observed_at>at:
                return # A slow local batch cannot overwrite newer real work.
            # A new local sample replaces the old batch. Failed/empty samples
            # cannot renew old counters; explicit operations with metrics=None
            # retain the original count clock without pretending to resample.
            combined = dict(metrics) if metrics is not None else dict(previous.metrics) if previous else {}
            sampled = at if metrics is not None and combined else previous.metrics_sampled_at if metrics is None and previous else None
            metrics_expiry = expiry if metrics is not None and combined else previous.metrics_expiry if metrics is None and previous else None
            last_success = at if state == 'READY' else previous.last_success if previous and previous.last_success and previous.last_success<=at else None
            if last_success_at is not None:last_success=last_success_at
            value = Observation(state, reason, at, expiry, combined,
                                tuple(evidence), self.installation_id, identifier, last_success, sampled,
                                uuid4().hex, observer_identity or 'core-next.kernel:'+str(os.getpid()),
                                self.build_identity,tuple(verification_scope),metrics_expiry)
            self.observations[identifier] = value

    def record_operation(self, identifier, operation, state, reason, *, evidence=(), update_module=True):
        """Operation evidence cannot renew a separately sampled count batch."""
        with self.lock:
            if operation not in self.definitions[identifier].supported_operations:
                raise ValueError('UNKNOWN_MODULE_OPERATION')
            if update_module:
                self.record(identifier, state, reason, evidence=evidence,verification_scope=('EXPLICIT_OPERATION:'+operation,))
                proof=self.observations[identifier]
            else:
                at=self.clock()
                proof=Observation(state,reason,at,at+timedelta(seconds=self.ttl),{},tuple(evidence),
                    self.installation_id,identifier,at if state=='READY' else None,None,uuid4().hex,
                    'core-next.kernel:'+str(os.getpid()),self.build_identity,('EXPLICIT_OPERATION:'+operation,))
            self.operation_observations[(identifier,operation)] = proof
            self.last_operations[identifier] = {'operation': operation, 'state': state,
                'observed_at': iso(proof.observed_at), 'evidence': list(evidence)}

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
            result = self.bindings[identifier].observe()
            self.record(identifier, result['state'], result['reason'],
                        metrics=result.get('metrics'), evidence=result.get('evidence', ()),
                        observed_at=result.get('observed_at'),expires_at=result.get('expires_at'),last_success_at=result.get('last_success_at'))
        except Exception:
            self.record(identifier, 'DEGRADED', 'BOUNDED_LOCAL_OBSERVATION_FAILED',metrics={})

    def stop(self):
        with self.lock:
            self.running = False
        for identifier in reversed(self._order):
            if identifier in self.supporting:
                self.record(identifier,'UNVERIFIED','KERNEL_OBSERVER_STOPPED',metrics={})
                continue
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
                if observation.observed_at>self.clock():
                    state, reason = 'UNKNOWN', 'OBSERVATION_CLOCK_IN_FUTURE'
                elif state != 'STOPPED' and self.clock() >= observation.expires_at:
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
                missing = [dep for dep in (*definition.dependencies,*needed) if dep not in self.definitions or self.item(dep)['state'] != 'READY']
                operations = []
                for op in dict(definition.capability_operations)[cap]:
                    proof = self.operation_observations.get((identifier,op))
                    # Supporting status probes actually execute that narrow
                    # operation. Engine storage/configuration probes do not
                    # establish every calculation or mutation in the module.
                    if proof is None and op=='status' and definition.layer=='supporting':proof=observation
                    op_state = proof.state if proof else 'UNVERIFIED'
                    op_reason = proof.reason if proof else 'NO_OPERATION_EVIDENCE'
                    if proof and proof.observed_at>self.clock():op_state,op_reason='UNKNOWN','OBSERVATION_CLOCK_IN_FUTURE'
                    elif proof and self.clock()>=proof.expires_at:op_state,op_reason='EXPIRED','OBSERVATION_EXPIRED'
                    if identifier in self.disabled or state=='STOPPED':op_state,op_reason='UNAVAILABLE','MODULE_NOT_RUNNING'
                    if missing:op_state,op_reason='DEGRADED','CAPABILITY_DEPENDENCY_NOT_READY'
                    operations.append({'id':op,'state':op_state,'reason':op_reason,
                        'observed_at':iso(proof.observed_at) if proof else None,
                        'expires_at':iso(proof.expires_at) if proof else None,
                        'observation_id':proof.observation_id if proof else None,
                        'verification_scope':list(proof.verification_scope) if proof else [],
                        'evidence_reference':list(proof.evidence) if proof else []})
                verified = [op for op in operations if op['state']=='READY']
                capability_status.append({'id':cap,'available':bool(verified),
                    'state':'READY' if verified else 'DEGRADED' if missing else 'UNVERIFIED',
                    'reason':'EXPLICIT_OPERATION_SCOPE_ONLY' if verified else 'CAPABILITY_DEPENDENCY_NOT_READY' if missing else 'NO_CURRENT_SUCCESSFUL_OPERATION_EVIDENCE',
                    'operations':[op['id'] for op in operations],
                    'verified_operations':[op['id'] for op in verified],
                    'operation_status':operations})
            raw = {'state': observation.state, 'reason': observation.reason,
                   'metrics': dict(observation.metrics), 'evidence': list(observation.evidence)} if observation else {
                       'state': 'UNVERIFIED', 'reason': reason, 'metrics': {}, 'evidence': []}
            raw.update(installation_id=self.installation_id, module_id=identifier,
                       observed_at=iso(observation.observed_at) if observation else None,
                       expires_at=iso(observation.expires_at) if observation else None,
                       last_success=iso(observation.last_success) if observation and observation.last_success else None)
            raw.update(observation_id=observation.observation_id if observation else None,
                observer_identity=observation.observer_identity if observation else None,
                build_identity=observation.build_identity if observation else self.build_identity,
                verification_scope=list(observation.verification_scope) if observation else [])
            sampled = observation.metrics_sampled_at if observation else None
            metrics_expiry = (observation.metrics_expiry or sampled+timedelta(seconds=self.ttl)) if sampled else None
            raw.update(metrics_sampled_at=iso(sampled) if sampled else None,
                metrics_expires_at=iso(metrics_expiry) if metrics_expiry else None,
                metrics_state=('EXPIRED' if self.clock() >= metrics_expiry else 'CURRENT') if sampled else 'UNVERIFIED',
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
            sanitized = dict(raw['metrics'])
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

    def items(self,scope='all'):
        if scope not in ('all','engines','supporting'):raise ValueError('INVALID_MODULE_SCOPE')
        return [self.item(identifier) for identifier in self._order
                if scope=='all' or self.definitions[identifier].layer==('engine' if scope=='engines' else 'supporting')]

    def inventory(self):
        engines=sum(item.layer=='engine' for item in self.definitions.values())
        return {'engines':engines,'supporting':len(self.definitions)-engines,'total':len(self.definitions)}
