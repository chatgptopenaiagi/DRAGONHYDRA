"""Additive synthetic routes inside the product's existing authentication router."""
from pathlib import Path
import json
from typing import Any, Literal

from fastapi import Depends, Path as PathParameter, Query
from pydantic import BaseModel, ConfigDict, Field

from ..kernel.contracts import ModuleDefinition
from . import VERSION

VIRTUAL_ID = r'^virtual-[A-Za-z0-9_.:-]{1,100}$'
Universe = Literal['constant', 'card_sensitive', 'tempo_signal', 'noisy_signal', 'clock_sensitive']
Mode = Literal['DEMONSTRATION', 'REPLAY']


class Input(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)


class Empty(Input):
    pass


class Scenario(Input):
    scenario_id: Literal['standard', 'universe'] = 'standard'
    source_mode: Mode = 'DEMONSTRATION'
    universe: Universe = 'constant'
    seed: int = Field(default=42, ge=0, le=2147483647)


class Replay(Input):
    action: Literal['step', 'start', 'pause', 'resume']
    speed: int = Field(default=100, ge=1, le=100)
    steps: int = Field(default=1, ge=1, le=100)


class Investigation(Input):
    forecast_revision: int | None = Field(default=None, ge=1, le=1000000)


class Branch(Input):
    at_revision: int = Field(ge=0, le=1000000)
    branch_name: str = Field(default='fork', min_length=1, max_length=64)
    seed: int = Field(default=42, ge=0, le=2147483647)
    universe: Universe = 'constant'


class Experiment(Input):
    seed: int = Field(default=42, ge=0, le=2147483647)
    cases: int = Field(default=400, ge=1, le=2000)


class Event(Input):
    schema_version: Literal['dragonhydra.live-event/1']
    event_id: str = Field(pattern=VIRTUAL_ID)
    source_id: str = Field(pattern=VIRTUAL_ID)
    match_id: str = Field(pattern=VIRTUAL_ID)
    event_type: str = Field(min_length=1, max_length=40)
    event_time: str = Field(min_length=1, max_length=40)
    received_at: str = Field(min_length=1, max_length=40)
    sequence: int = Field(ge=1, le=1000000)
    revision: int = Field(ge=1, le=1000000)
    participant: Literal['HOME', 'AWAY', 'NONE']
    attributes: dict[str, Any]
    source_mode: Mode
    quality_state: Literal['VALIDATED']


def definition(service):
    capabilities = (
        ('synthetic_event_research', ('status', 'matches', 'match', 'timeline', 'events', 'ingest', 'create_scenario')),
        ('virtual_replay', ('replay_control',)),
        ('bounded_virtual_investigation', ('investigate', 'tools', 'budgets')),
        ('synthetic_evaluation', ('evaluate', 'evaluation_report')),
        ('virtual_branches', ('branch',)),
        ('relevance_experiments', ('run_experiment', 'experiments')),
    )
    return ModuleDefinition('realtime_research', 'Synthetic realtime research',
        'Virtual-clock fictional events, bounded probability research and local simulated tool investigations.',
        'Research', dependencies=('sqlite_storage',), capabilities=tuple(k for k, _ in capabilities),
        origin='experimental', version=VERSION, configuration_requirements=('sqlite_state',),
        supported_operations=tuple(op for _, operations in capabilities for op in operations),
        data_domains=('synthetic_events', 'virtual_forecasts', 'virtual_investigations'),
        verification_references=('tests/test_realtime_api.py',),
        implementation_reference=type(service).__module__ + '.' + type(service).__name__,
        capability_operations=capabilities)


def validate_virtual_context(state, source_root):
    """Refuse retained profiles or real source resources before Product creates state."""
    state, source = Path(state).absolute(), Path(source_root).absolute()
    for path in (state, source):
        for part in (path, *path.parents):
            if part.exists() and (part.is_symlink() or getattr(part.lstat(), 'st_file_attributes', 0) & 0x400):
                raise ValueError('VIRTUAL_REPARSE_PATH_REJECTED')
    if source != state / 'virtual-source' or not source.is_dir() or any(source.iterdir()):
        raise ValueError('EMPTY_VIRTUAL_SOURCE_REQUIRED')
    forbidden = ('installation-profile.json', 'workstation.json', 'research-storage.json', 'joomla-bridge.json', 'local-ai.json', 'vault')
    if any((state / name).exists() for name in forbidden):
        raise ValueError('VIRTUAL_PROFILE_ADOPTION_REJECTED')
    marker = state / '.genesis6-runtime.json'
    if marker.exists():
        try:
            if marker.is_symlink() or getattr(marker.lstat(), 'st_file_attributes', 0) & 0x400 or marker.stat().st_size > 4096:
                raise ValueError()
            record = json.loads(marker.read_text(encoding='utf-8'))
            if (record.get('schema_version') != 'dragonhydra.genesis6-runtime/1'
                    or record.get('state') != str(state) or record.get('synthetic_only') is not True
                    or record.get('virtual_credentials_only') is not True):
                raise ValueError()
        except (OSError, ValueError, AttributeError):
            raise ValueError('VIRTUAL_RUNTIME_MARKER_INVALID') from None
    elif (state / 'core.sqlite3').exists():
        raise ValueError('VIRTUAL_EXISTING_PRODUCT_STATE_REJECTED')


def register_routes(router, service, admin, kernel):
    prefix = '/realtime'

    @router.get(prefix + '/status')
    def status(): return service.status()

    @router.get(prefix + '/matches')
    def matches(): return service.matches()

    @router.get(prefix + '/matches/{match_id}')
    def match(match_id: str = PathParameter(pattern=VIRTUAL_ID)): return service.match(match_id)

    @router.get(prefix + '/matches/{match_id}/timeline')
    def timeline(match_id: str = PathParameter(pattern=VIRTUAL_ID), limit: int = Query(default=200, ge=1, le=200)):
        return service.timeline(match_id, limit=limit)

    @router.get(prefix + '/matches/{match_id}/events')
    def events(match_id: str = PathParameter(pattern=VIRTUAL_ID)): return service.events(match_id)

    @router.get(prefix + '/tools')
    def tools(): return service.tools()

    @router.get(prefix + '/budgets')
    def budgets(): return service.budgets()

    @router.get(prefix + '/evaluation')
    def evaluation(): return service.evaluation_report()

    @router.get(prefix + '/experiments')
    def experiments(): return service.experiments()

    def execute(operation, *args, **kwargs):
        return kernel.execute('realtime_research', operation, *args, **kwargs)

    @router.post(prefix + '/scenarios', dependencies=[Depends(admin)])
    def scenario(body: Scenario): return execute('create_scenario', **body.model_dump())

    @router.post(prefix + '/replay/{match_id}', dependencies=[Depends(admin)])
    def replay(body: Replay, match_id: str = PathParameter(pattern=VIRTUAL_ID)):
        return execute('replay_control', match_id, **body.model_dump())

    @router.post(prefix + '/events', dependencies=[Depends(admin)])
    def ingest(body: Event): return execute('ingest', body.model_dump())

    @router.post(prefix + '/matches/{match_id}/investigations', dependencies=[Depends(admin)])
    def investigate(body: Investigation, match_id: str = PathParameter(pattern=VIRTUAL_ID)):
        return execute('investigate', match_id, **body.model_dump())

    @router.post(prefix + '/matches/{match_id}/branches', dependencies=[Depends(admin)])
    def branch(body: Branch, match_id: str = PathParameter(pattern=VIRTUAL_ID)):
        return execute('branch', match_id, **body.model_dump())

    @router.post(prefix + '/evaluation', dependencies=[Depends(admin)])
    def evaluate(body: Empty): return execute('evaluate')

    @router.post(prefix + '/experiments/relevance', dependencies=[Depends(admin)])
    def experiment(body: Experiment): return execute('run_experiment', **body.model_dump())
