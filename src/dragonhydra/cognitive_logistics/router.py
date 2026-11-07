"""Inventory-domain operations inside the existing authenticated virtual host."""
from typing import Literal
from fastapi import Depends, Path as PathParameter
from pydantic import BaseModel, ConfigDict, Field
from ..kernel.contracts import ModuleDefinition
from . import VERSION

RESOURCE_ID=r'^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$'
Universe=Literal['stable','intermittent','seasonal','supplier_disruption','perishable','multi_location']
Policy=Literal['reorder_point','order_up_to','base_stock','s_S','probabilistic_cost']
Acquisition=Literal['none','all','random','handcrafted','learned']
Method=Literal['compare_methods','bounded_method_search','counterfactual']

class Input(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)

class Episode(Input):
    universe: Universe='stable'
    demand_mode: Literal['lost_sales','backorder']='lost_sales'
    seed: int=Field(default=400042,ge=0,le=2147483647)
    days: int=Field(default=60,ge=10,le=120)
    budget: float=Field(default=10.0,ge=0,le=100,allow_inf_nan=False)

class Decision(Input):
    policy: Policy='order_up_to'
    acquisition: Acquisition='none'
    request_id: str=Field(min_length=1,max_length=128,pattern=RESOURCE_ID)
    expected_revision: int=Field(ge=0,le=1000000)

class Advance(Input):
    days: int=Field(default=1,ge=1,le=30)
    expected_revision: int=Field(ge=0,le=1000000)

class Training(Input):
    seed: int=Field(default=42,ge=0,le=2147483647)
    cases: int=Field(default=10,ge=10,le=100)

class Analysis(Input):
    method: Method='compare_methods'

def definition(service):
    capabilities=(
        ('logistics_public_reads',('status','episodes','episode','models','experiments','experiment')),
        ('virtual_inventory_episodes',('create_episode',)),
        ('replenishment_information_decisions',('decide',)),
        ('virtual_supply_chain_time',('advance',)),
        ('frozen_acquisition_training',('train',)),
        ('bounded_logistics_analysis',('analyze',)),
    )
    return ModuleDefinition('cognitive_logistics','Cognitive logistics research',
        'Virtual inventory conservation, demand forecasts and budgeted replenishment information decisions.',
        'Research',dependencies=('sqlite_storage',),capabilities=tuple(k for k,_ in capabilities),
        origin='experimental',version=VERSION,configuration_requirements=('sqlite_state',),
        supported_operations=tuple(op for _,ops in capabilities for op in ops),
        data_domains=('virtual_inventory','synthetic_demand','virtual_supply_network'),
        verification_references=('tests/test_logistics_api.py',),
        implementation_reference=type(service).__module__+'.'+type(service).__name__,capability_operations=capabilities)

def register_routes(router,service,admin,kernel):
    prefix='/logistics'
    @router.get(prefix+'/status')
    def status():return service.status()
    @router.get(prefix+'/episodes')
    def episodes():return service.episodes()
    @router.get(prefix+'/episodes/{episode_id}')
    def episode(episode_id: str=PathParameter(pattern=RESOURCE_ID)):return service.episode(episode_id)
    @router.get(prefix+'/models')
    def models():return service.models()
    @router.get(prefix+'/experiments')
    def experiments():return service.experiments()
    @router.get(prefix+'/experiments/{experiment_id}')
    def experiment(experiment_id: str=PathParameter(pattern=RESOURCE_ID)):return service.experiment(experiment_id)
    def execute(operation,*args,**kwargs):return kernel.execute('cognitive_logistics',operation,*args,**kwargs)
    @router.post(prefix+'/episodes',dependencies=[Depends(admin)])
    def create_episode(body: Episode):return execute('create_episode',**body.model_dump())
    @router.post(prefix+'/episodes/{episode_id}/decisions',dependencies=[Depends(admin)])
    def decide(body: Decision,episode_id: str=PathParameter(pattern=RESOURCE_ID)):
        return execute('decide',episode_id,**body.model_dump())
    @router.post(prefix+'/episodes/{episode_id}/advance',dependencies=[Depends(admin)])
    def advance(body: Advance,episode_id: str=PathParameter(pattern=RESOURCE_ID)):
        return execute('advance',episode_id,**body.model_dump())
    @router.post(prefix+'/episodes/{episode_id}/analyses',dependencies=[Depends(admin)])
    def analyze(body: Analysis,episode_id: str=PathParameter(pattern=RESOURCE_ID)):
        return execute('analyze',episode_id,**body.model_dump())
    @router.post(prefix+'/training',dependencies=[Depends(admin)])
    def train(body: Training):return execute('train',**body.model_dump())
