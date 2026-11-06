"""Future relevance routes share the existing authenticated virtual application."""
from typing import Literal
from fastapi import Depends, Path as PathParameter
from pydantic import BaseModel, ConfigDict, Field, model_validator
from ..kernel.contracts import ModuleDefinition
from . import VERSION

Universe = Literal['constant','card_sensitive','tempo_signal','noisy_signal','clock_sensitive',
                   'possession_inverse','late_card_interaction']
Target = Literal['GOAL_OCCURRENCE','FULL_TIME_RESULT','NEXT_GOAL_SIDE','REMAINING_GOALS']
Horizon = Literal['1','5','10','30','FULL_TIME']
Policy = Literal['acquire_all','acquire_none','random','handcrafted','learned']
RESOURCE_ID = r'^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$'


class Input(BaseModel):
    model_config = ConfigDict(extra='forbid',strict=True)


class Episode(Input):
    universe: Universe = 'constant'
    seed: int = Field(default=400042,ge=0,le=2147483647)
    target: Target = 'GOAL_OCCURRENCE'
    horizon: Horizon = '10'
    minute: float = Field(default=60.0,ge=45,le=89,allow_inf_nan=False)
    budget: float = Field(default=0.12,ge=0,le=100,allow_inf_nan=False)

    @model_validator(mode='after')
    def appropriate_horizon(self):
        if self.target == 'FULL_TIME_RESULT' and self.horizon != 'FULL_TIME':
            raise ValueError('FULL_TIME_RESULT_REQUIRES_FULL_TIME')
        return self


class Decision(Input):
    policy: Policy
    request_id: str = Field(min_length=1,max_length=128,pattern=RESOURCE_ID)
    expected_revision: int = Field(ge=0,le=1000000)


class Advance(Input):
    minutes: float = Field(default=10.0,ge=0.1,le=50,allow_inf_nan=False)
    expected_revision: int = Field(ge=0,le=1000000)


class Training(Input):
    seed: int = Field(default=42,ge=0,le=2147483647)
    cases_per_family: int = Field(default=200,ge=10,le=1000)


def definition(service):
    capabilities = (
        ('future_relevance_reads',('status','models','model','episodes','episode','experiments','experiment')),
        ('virtual_episode_creation',('create_episode',)),
        ('budgeted_information_decisions',('decide',)),
        ('eligible_virtual_outcomes',('advance',)),
        ('frozen_policy_training',('train',)),
    )
    return ModuleDefinition('future_relevance','Future relevance research',
        'Synthetic pre-observation information decisions, frozen policies and held-out retrospective evaluation.',
        'Research',dependencies=('sqlite_storage',),capabilities=tuple(k for k,_ in capabilities),
        origin='experimental',version=VERSION,configuration_requirements=('sqlite_state',),
        supported_operations=tuple(op for _,ops in capabilities for op in ops),
        data_domains=('virtual_information_decisions','synthetic_future_outcomes'),
        verification_references=('tests/test_future_api.py',),
        implementation_reference=type(service).__module__+'.'+type(service).__name__,
        capability_operations=capabilities)


def register_routes(router,service,admin,kernel):
    prefix='/future'
    @router.get(prefix+'/status')
    def status(): return service.status()
    @router.get(prefix+'/models')
    def models(): return service.models()
    @router.get(prefix+'/models/{model_id}')
    def model(model_id: str=PathParameter(pattern=RESOURCE_ID)): return service.model(model_id)
    @router.get(prefix+'/episodes')
    def episodes(): return service.episodes()
    @router.get(prefix+'/episodes/{episode_id}')
    def episode(episode_id: str=PathParameter(pattern=RESOURCE_ID)): return service.episode(episode_id)
    @router.get(prefix+'/experiments')
    def experiments(): return service.experiments()
    @router.get(prefix+'/experiments/{experiment_id}')
    def experiment(experiment_id: str=PathParameter(pattern=RESOURCE_ID)): return service.experiment(experiment_id)
    def execute(operation,*args,**kwargs): return kernel.execute('future_relevance',operation,*args,**kwargs)
    @router.post(prefix+'/episodes',dependencies=[Depends(admin)])
    def create_episode(body: Episode): return execute('create_episode',**body.model_dump())
    @router.post(prefix+'/episodes/{episode_id}/decisions',dependencies=[Depends(admin)])
    def decide(body: Decision,episode_id: str=PathParameter(pattern=RESOURCE_ID)):
        return execute('decide',episode_id,**body.model_dump())
    @router.post(prefix+'/episodes/{episode_id}/advance',dependencies=[Depends(admin)])
    def advance(body: Advance,episode_id: str=PathParameter(pattern=RESOURCE_ID)):
        return execute('advance',episode_id,**body.model_dump())
    @router.post(prefix+'/training',dependencies=[Depends(admin)])
    def train(body: Training): return execute('train',**body.model_dump())
