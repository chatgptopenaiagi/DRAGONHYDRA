"""Single application composition root with explicit engine/runtime bindings."""
import hashlib
from collections import Counter
from dataclasses import replace

from .contracts import KernelConfig, ModuleDefinition, utc_now
from .engines import DataEngine, OddsEngine, PredictionEngine, MemoryEngine, EvaluationEngine, AIEngine
from .registry import ModuleRegistry
from .supporting import SupportingObservations,definitions as supporting_definitions
from .local_observer import LocalObserver

DEFINITIONS = (
    ModuleDefinition('data', 'Retained sports data', 'Canonical source-scoped matches and retained evidence.',
                     'Data sources', capabilities=('retained_reads', 'canonical_identity', 'provenance')),
    ModuleDefinition('odds', 'Odds engine', 'Provider-bound prices and scope-checked deterministic market mathematics.',
                     'Odds & predictions', ('data',), ('retained_odds', 'market_signals', 'conditional_scenarios')),
    ModuleDefinition('prediction', 'Prediction engine', 'Existing frequency, Poisson, Elo, recency and ensemble models.',
                     'Odds & predictions', ('data',), ('current_forecast', 'explicit_forecast_persistence'),
                     optional_dependencies=('memory',)),
    ModuleDefinition('memory', 'Evidence memory', 'Immutable model, prediction, outcome, hypothesis and evaluation records.',
                     'Memory & evaluation', ('data',), ('as_of_memory', 'append_only_records')),
    ModuleDefinition('evaluation', 'Evaluation engine', 'Score only eligible persisted forecasts against later retained outcomes.',
                     'Memory & evaluation', ('memory',), ('observed_brier', 'log_loss', 'calibration'),
                     optional_dependencies=('prediction',)),
    ModuleDefinition('ai', 'Optional local AI', 'Constrained source-fact selection with labelled deterministic fallback.',
                     'AI', ('data',), ('evidence_package', 'optional_local_inference'), origin='optional'),
)

_CONTRACTS = {
    'data': (('sqlite_state',), ('rows', 'match_id', 'competition_id', 'team_id', 'present', 'find',
               'matches', 'competitions', 'team', 'standings', 'evidence'),
             ('source_observations', 'fixtures', 'teams', 'competitions', 'raw_evidence'),
             ('tests/test_public_results.py', 'tests/test_connectors_store.py', 'tests/core_next/test_kernel.py')),
    'odds': (('retained_provider_scope',), ('odds', 'signals', 'scenario'),
             ('provider_odds', 'market_snapshots', 'conditional_risk'),
             ('tests/test_market_signals.py', 'tests/test_scenario.py', 'tests/core_next/test_characterization.py')),
    'prediction': (('eligible_future_fixture', 'same_source_training_evidence'), ('predictions', 'persist'),
                   ('model_runs', 'prospective_predictions', 'uncertainty'),
                   ('tests/test_cognition_models.py', 'tests/core_next/test_kernel.py', 'tests/core_next/test_characterization.py')),
    'memory': (('sqlite_state',), ('view', 'history', 'record_model', 'record_prediction', 'attach_outcome'),
               ('immutable_memory', 'prediction_receipts', 'later_outcomes'),
               ('tests/test_cognition_memory.py', 'tests/core_next/test_kernel.py')),
    'evaluation': (('eligible_persisted_prediction_and_later_outcome',), ('evaluate', 'persist', 'evaluate_match'),
                   ('operational_evaluation', 'calibration', 'coverage'),
                   ('tests/test_cognition_evaluation.py', 'tests/core_next/test_kernel.py')),
    'ai': (('protected_server_endpoint', 'protected_server_credential'), ('explanation', 'explain', 'package'),
           ('retained_source_facts', 'frozen_context_packages'),
           ('tests/test_local_ai_api.py', 'tests/test_local_ai_context_api.py', 'tests/core_next/test_kernel.py')),
}
DEFINITIONS = tuple(replace(item, configuration_requirements=_CONTRACTS[item.id][0],
    supported_operations=_CONTRACTS[item.id][1], data_domains=_CONTRACTS[item.id][2],
    verification_references=_CONTRACTS[item.id][3]) for item in DEFINITIONS)

_CAPABILITIES = {
    'data': {'retained_reads': ('rows', 'matches', 'find', 'team', 'standings'),
             'canonical_identity': ('match_id', 'competition_id', 'team_id'), 'provenance': ('evidence',)},
    'odds': {'retained_odds': ('odds',), 'market_signals': ('signals',), 'conditional_scenarios': ('scenario',)},
    'prediction': {'current_forecast': ('predictions',), 'explicit_forecast_persistence': ('persist',)},
    'memory': {'as_of_memory': ('view', 'history'), 'append_only_records': ('record_model', 'record_prediction', 'attach_outcome')},
    'evaluation': {'observed_brier': ('evaluate', 'persist', 'evaluate_match'), 'log_loss': ('evaluate', 'evaluate_match'), 'calibration': ('evaluate', 'evaluate_match')},
    'ai': {'evidence_package': ('package', 'explanation'), 'optional_local_inference': ('explain',)},
}
DEFINITIONS = tuple(replace(item, capability_operations=tuple(_CAPABILITIES[item.id].items()),
    capability_dependencies=(('explicit_forecast_persistence', ('memory',)),) if item.id == 'prediction' else ())
    for item in DEFINITIONS)


class Kernel:
    def __init__(self, context, *, config=None, adapters=None, clock=utc_now):
        from ..build_meta import info
        from ..cognition import models, memory, evaluation
        from .. import market_signals, scenario, local_ai, local_ai_service
        from ..local_ai_settings import Settings
        from .ports import ApplicationContext, MemoryPort, AIContext
        if not isinstance(context, ApplicationContext):
            raise ValueError('EXPLICIT_APPLICATION_PORTS_REQUIRED')
        build = info()
        if config is None:
            config = KernelConfig('core-next-source-'+hashlib.sha256(str(context.storage.state).encode()).hexdigest()[:16],
                                  version=build['version'], source_commit=build['source_sha'])
        elif isinstance(config, dict):
            config = KernelConfig(**config)
        if not isinstance(config, KernelConfig):
            raise ValueError('INVALID_KERNEL_CONFIGURATION')
        config = replace(config, version=config.version or build['version'],
                         build_id=config.build_id or 'source-checkout')
        self.config, self.context = config, context
        overrides = dict(adapters or {})
        if set(overrides)-{item.id for item in DEFINITIONS}:
            raise ValueError('UNKNOWN_MODULE_ADAPTER')
        data = overrides.get('data') or DataEngine(context)
        memory_engine = overrides.get('memory') or MemoryEngine(context, memory, data=data)
        memory_port = MemoryPort(
            lambda cutoff: self.execute('memory', 'view', cutoff),
            lambda draft: self.execute('memory', 'record_model', draft),
            lambda draft: self.execute('memory', 'record_prediction', draft),
            lambda eid: self.execute('memory', 'attach_outcome', eid))
        ai_context = AIContext(context.storage.state, context.storage.db_path, data.find, data.present, data.evidence)
        self.engines = {
            'data': data, 'memory': memory_engine,
            'odds': overrides.get('odds') or OddsEngine(context, data, market_signals.compute_signals, scenario.price_scenario),
            'prediction': overrides.get('prediction') or PredictionEngine(context, data, models, memory_port),
            'evaluation': overrides.get('evaluation') or EvaluationEngine(context, memory_port,
                evaluation.evaluate_observed, memory.record_evaluation, data=data),
            'ai': overrides.get('ai') or AIEngine(context, data,
                lambda match: local_ai.build_package(ai_context, match),
                lambda match, selected: local_ai.build_context_package(ai_context, match, selected),
                lambda package, check: local_ai_service.explain(ai_context, package, check),
                lambda: Settings(context.storage.state).public()),
        }
        definitions = tuple(replace(item, version=build['version'],
            implementation_reference=type(self.engines[item.id]).__module__+'.'+type(self.engines[item.id]).__name__)
            for item in DEFINITIONS)
        self.supporting = SupportingObservations(context,config,clock)
        definitions=tuple(replace(item,dependencies=('sqlite_storage',)+item.dependencies) if item.id=='data' else item for item in definitions)
        definitions = definitions+supporting_definitions(build['version'])
        self.registry = ModuleRegistry(definitions, self.engines,supporting=self.supporting.bindings(),
            ttl_seconds=config.observation_ttl_seconds, clock=clock, disabled=config.disabled_modules,
            installation_id=config.installation_id, build_identity=(config.build_id or '')+':'+(config.source_commit or 'source-checkout'))
        self.observer=LocalObserver(self.registry,self.supporting,context.storage.state,self.identity(),
            interval=config.observation_interval_seconds,clock=clock)
        self.supporting.observer=self.observer

    def start(self):
        self.supporting.api_active=True
        self.observer.start()

    def stop(self):
        self.observer.stop()
        self.registry.stop()
        self.supporting.api_active=False

    def bind_worker(self,worker):self.supporting.worker=worker

    def observation_tick(self):return self.observer.tick()

    def observe_local(self,force=False):return self.observer.tick(force=force)

    def execute(self, identifier, operation, *args, **kwargs):
        if identifier not in self.engines:
            raise LookupError('MODULE_NOT_FOUND')
        if identifier in self.registry.disabled:
            raise ValueError('MODULE_DISABLED_BY_PROFILE')
        definition = self.registry.definitions[identifier]
        def disabled_dependency(module):
            return any(dep in self.registry.disabled or disabled_dependency(self.registry.definitions[dep])
                       for dep in module.dependencies)
        if disabled_dependency(definition):
            raise ValueError('MODULE_DEPENDENCY_DISABLED')
        engine = self.engines[identifier]
        if operation not in definition.supported_operations or not callable(getattr(engine, operation, None)):
            raise ValueError('UNKNOWN_MODULE_OPERATION')
        capability_dependencies = dict(definition.capability_dependencies)
        for capability, operations in definition.capability_operations:
            if operation not in operations:
                continue
            for dependency in capability_dependencies.get(capability, ()):
                if (dependency not in self.engines or dependency in self.registry.disabled
                        or disabled_dependency(self.registry.definitions[dependency])):
                    raise ValueError('MODULE_OPERATION_DEPENDENCY_UNAVAILABLE')
        try:
            result = getattr(engine, operation)(*args, **kwargs)
        except Exception:
            self.registry.record_operation(identifier, operation, 'DEGRADED', 'LAST_EXPLICIT_OPERATION_FAILED',
                evidence=('Explicit '+operation+' failed; original exception propagated',))
            raise
        available = not isinstance(result, dict) or result.get('available', True)
        # Optional AI fallback is successful deterministic delivery, not model readiness.
        if identifier == 'ai' and operation == 'explain':
            available = bool(result.get('local_ai', {}).get('accepted'))
        if identifier == 'ai' and operation in ('explanation', 'package'):
            self.registry.record_operation('ai', operation, 'READY',
                'DETERMINISTIC_PACKAGE_ONLY_NO_INFERENCE',
                evidence=('Actual retained-source '+operation+'; no model inference claimed',),update_module=False)
            # Model configuration remains the module-level requirement;
            # successful deterministic packaging is independent scoped proof.
            return result
        if identifier == 'evaluation' and operation == 'evaluate':
            available = any(group['metrics']['brier']['sample_size'] for group in result['groups'])
        if identifier == 'prediction' and operation == 'persist':
            available = available and bool(result['predictions'])
        if ((identifier == 'memory' and operation in ('record_model', 'record_prediction', 'attach_outcome'))
                or (identifier in ('prediction', 'evaluation') and operation == 'persist')):
            self.registry.refresh('memory')
            if identifier == 'evaluation':
                self.registry.refresh('evaluation')
        self.registry.record_operation(identifier, operation, 'READY' if available else 'UNAVAILABLE',
            'EXPLICIT_OPERATION_COMPLETED' if available else 'EXPLICIT_OPERATION_RETURNED_UNAVAILABLE',
            evidence=('Actual '+operation+' through composed engine',),
            update_module=not(identifier=='memory' and operation in ('view','history')))
        return result

    def dispatch_job(self, jobs, job):
        from .job_dispatch import JobDispatcher
        from ..connectors.statsbomb_context_jobs import run
        result = JobDispatcher(import_public=jobs.import_public, export=jobs.export,
            explanation=jobs.product.explanation,
            local_explanation=lambda package, check: self.execute('ai', 'explain', package, check),
            context_run=lambda item, check, claim: run(jobs.product, item, check, claim),
            provider_run=jobs.providers.run, check=jobs.check,
            require_claim=jobs.require_claim, stop=jobs.stop,
            forecast=lambda item: {**self.execute('prediction','persist',item['payload']['match_id'],run_id=item['id']), 'installation':self.identity()},
            evaluation=lambda item: {**self.execute('evaluation','evaluate_match',item['payload']['match_id'],item['id']), 'installation':self.identity()}).execute(job)
        if job['kind'] in ('import_public', 'connector_sync'):
            self.registry.refresh('data')
        return result

    def identity(self):
        return self.config.identity()

    def modules(self,scope='engines'):
        return {'schema_version': 'core-next.modules/1', 'installation': self.identity(),
                'items': self.registry.items(scope),'inventory':self.registry.inventory(),'scope':scope}

    def module(self, identifier):
        return {'schema_version': 'core-next.modules/1', 'installation': self.identity(),
                **self.registry.item(identifier)}

    def summary(self):
        return dict(Counter(item['state'] for item in self.registry.items()))
