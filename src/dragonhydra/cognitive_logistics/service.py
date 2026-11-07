"""Transactional virtual operations. Public reads never run forecasts or actions."""
from copy import deepcopy
import json,threading
from . import VERSION
from .contracts import *
from .contracts import request_id as validate_request_id
from .journal import Journal
from .world import World
from .relevance import estimate,validate

class LogisticsService:
    contract_version='core-next.engine/1'
    def __init__(self,directory,config=None):
        config=config or {}
        if set(config)-{'acquisition_budget','max_episodes'}:raise ValueError('LOGISTICS_SERVICE_CONFIG_INVALID')
        self.limit=finite(config.get('acquisition_budget',100),0,100000)
        self.max_episodes=integer(config.get('max_episodes',128),1,512)
        self.journal=Journal(directory);self.lock=threading.RLock();self.closed=False;self.training=False
    def _open(self):
        if self.closed:raise ValueError('LOGISTICS_SERVICE_CLOSED')
    def _world(self,db,episode_id):
        row=db.execute('SELECT world,sha256 FROM episodes WHERE id=?',(episode_id,)).fetchone()
        if not row:raise LookupError('LOGISTICS_EPISODE_NOT_FOUND')
        data=json.loads(row[0])
        if digest(data)!=row[1]:raise ValueError('LOGISTICS_WORLD_HASH_MISMATCH')
        return World.from_dict(data)
    def _model(self,db):
        name=Journal.meta(db,'active_model')
        if not name:return None
        row=db.execute('SELECT payload FROM models WHERE id=?',(name,)).fetchone()
        if not row:raise ValueError('LOGISTICS_BOUND_MODEL_MISSING')
        return validate(json.loads(row[0]))
    def _view(self,world,model=None):
        snapshot=world.snapshot();calls=world.cache.calls
        forecasts={loc:world.cache.demand(snapshot,loc,'sba',5) for loc in LOCATIONS}
        lead=world.cache.lead(snapshot)
        estimates=[]
        for category in CATEGORIES:
            if model is not None and model['available_clock']<=world.clock:
                estimates.append(estimate(snapshot,category,model))
            else:estimates.append({'category':category,'estimated_value':None,'estimated_cost':next(c['cost'] for c in snapshot['candidates'] if c['category']==category),'state':'UNTRAINED_OR_NOT_AVAILABLE_AT_CUTOFF'})
        units=world.cache.calls-calls
        inference=sum(r['estimated_value'] is not None for r in estimates)
        price=units*.001+inference*.0002
        if price:
            world.costs.record(identity('public-view-computation',[world.episode_id,world.day,world.revision,world.cache.calls,model['model_id'] if model else None]),'computation',price,world.day)
        return {'episode_id':world.episode_id,'synthetic':True,'universe':world._family,'snapshot':snapshot,'current_forecasts':forecasts,'lead_forecast':lead,'network':{**deepcopy(world.network_config),'shipments':deepcopy(list(world._orders().values()))},'estimates':estimates,'metrics':world.metrics(model.get('train_naive_scale') if model else None),'model_id':model['model_id'] if model else None,'prior_genesis61_result':'Learned acquisition did not establish superiority over acquire-nothing.'}
    def _limit(self,db,world):world._external_remaining=max(0,self.limit-Journal.meta(db,'acquisition_spent',0.))
    def _save(self,db,world,view,previous_spent=0.):
        delta=world.spent-previous_spent
        if delta< -1e-9:raise ValueError('LOGISTICS_ACQUISITION_LEDGER_REWIND')
        total=Journal.meta(db,'acquisition_spent',0.)+delta
        if total>self.limit+1e-8:raise ValueError('LOGISTICS_GLOBAL_ACQUISITION_BUDGET_EXCEEDED')
        Journal.put_meta(db,'acquisition_spent',total)
        for decision in world.decisions:
            Journal.insert(db,'decisions',decision['decision_id'],decision,world.episode_id)
            for receipt in decision['acquisitions']:Journal.insert(db,'acquisitions',receipt['acquisition_id'],receipt,world.episode_id)
            for collection in ('forecasts','daily_forecasts'):
                for location,forecast in decision[collection].items():Journal.insert(db,'forecasts',identity('forecast',[decision['decision_id'],collection,location]),{'decision_id':decision['decision_id'],'location':location,**forecast},world.episode_id)
        for event in world.inventory.to_dict()['events']:Journal.insert(db,'events',identity('inventory-event',[world.episode_id,event['operation_id']]),event,world.episode_id)
        for row in world.outcomes:
            Journal.insert(db,'outcomes',identity('inventory-outcome',[world.episode_id,row['day']]),row,world.episode_id)
        # Observed trajectory cost is an outcome record, not a causal attribution.
        pending=db.execute("SELECT d.payload FROM decisions d LEFT JOIN evaluations e ON json_extract(e.payload,'$.decision_id')=d.id WHERE d.episode_id=? AND e.id IS NULL AND json_extract(d.payload,'$.day')+json_extract(d.payload,'$.horizon')<=? ORDER BY d.rowid",(world.episode_id,world.day)).fetchall()
        for encoded_decision in pending:
            decision=json.loads(encoded_decision[0])
            maturity=decision['day']+decision['horizon']
            if maturity<=world.day:
                eligible=[r for r in world.outcomes if decision['day']<r['day']<=maturity]
                result={'schema_version':'dragonhydra.logistics-decision-evaluation/1','evaluation_id':identity('decision-evaluation',decision['decision_id']),'decision_id':decision['decision_id'],'available_day':maturity,'decision_day':decision['day'],'observed_trajectory_cost':sum(sum(r['costs'].values()) for r in eligible),'eligible_demand':sum(r['demand'] for r in eligible),'eligible_fulfilled':sum(r['fulfilled'] for r in eligible),'classification':'OBSERVED_FACT','causal_attribution':'NOT_ESTABLISHED_BY_A_SINGLE_TRAJECTORY','synthetic':True}
                Journal.insert(db,'evaluations',result['evaluation_id'],result,world.episode_id)
        raw=world.to_dict();encoded=canonical(raw)
        db.execute('INSERT INTO episodes VALUES(?,?,?,?) ON CONFLICT(id) DO UPDATE SET world=excluded.world,sha256=excluded.sha256,view=excluded.view',(world.episode_id,encoded,digest(raw),canonical(view)))
    def create_episode(self,universe='stable',seed=400042,days=60,budget=10.,demand_mode='lost_sales'):
        self._open();world=World(universe,seed,days,budget,demand_mode)
        with self.lock,self.journal.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute('SELECT 1 FROM episodes WHERE id=?',(world.episode_id,)).fetchone():return {'episode_id':world.episode_id,'reused':True,'synthetic':True}
            if db.execute('SELECT count(*) FROM episodes').fetchone()[0]>=self.max_episodes:raise ValueError('LOGISTICS_EPISODE_LIMIT')
            self._limit(db,world);view=self._view(world,self._model(db));self._save(db,world,view);db.commit()
        return {'episode_id':world.episode_id,'synthetic':True}
    def episodes(self):
        with self.journal.connect() as db:return {'items':[json.loads(r[0]) for r in db.execute('SELECT view FROM episodes ORDER BY rowid DESC LIMIT 512')],'synthetic':True}
    def episode(self,episode_id):
        with self.journal.connect() as db:
            row=db.execute('SELECT view FROM episodes WHERE id=?',(episode_id,)).fetchone()
            if not row:raise LookupError('LOGISTICS_EPISODE_NOT_FOUND')
            return {**json.loads(row[0]),'decisions':Journal.items(db,'decisions',episode_id,120),'evaluations':Journal.items(db,'evaluations',episode_id,120),'analyses':Journal.items(db,'analyses',episode_id,50)}
    def decide(self,episode_id,policy='order_up_to',acquisition='none',request_id=None,expected_revision=None):
        self._open();validate_request_id(request_id);integer(expected_revision)
        fingerprint=digest([episode_id,policy,acquisition,request_id,expected_revision])
        with self.lock,self.journal.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            old=db.execute('SELECT fingerprint,payload FROM requests WHERE id=?',(request_id,)).fetchone()
            if old:
                if old[0]!=fingerprint:raise ValueError('LOGISTICS_IDEMPOTENCY_CONFLICT')
                return json.loads(old[1])
            if db.execute('SELECT count(*) FROM decisions').fetchone()[0]>=20000:raise ValueError('LOGISTICS_DECISION_LIMIT')
            world=self._world(db,episode_id)
            if world.revision!=expected_revision:raise ValueError('LOGISTICS_STALE_REVISION')
            previous=world.spent;self._limit(db,world);model=self._model(db) if acquisition=='learned' else None
            result=world.execute(policy,acquisition,model,decision_id=identity('manual-decision',[episode_id,request_id]))
            view=self._view(world,self._model(db));self._save(db,world,view,previous)
            db.execute('INSERT INTO requests VALUES(?,?,?)',(request_id,fingerprint,canonical(result)));db.commit()
        return result
    def advance(self,episode_id,days=1,expected_revision=None):
        self._open();integer(days,1,30)
        with self.lock,self.journal.connect() as db:
            db.execute('BEGIN IMMEDIATE');world=self._world(db,episode_id)
            if world.revision!=integer(expected_revision):raise ValueError('LOGISTICS_STALE_REVISION')
            if days>world.end_day-world.day:raise ValueError('LOGISTICS_ADVANCE_PAST_END')
            previous=world.spent;self._limit(db,world)
            for _ in range(days):
                world.step()
                if world.pending and world.day<world.end_day:
                    pending=deepcopy(world.pending)
                    if any(c['category']==pending['category'] and c['availability']=='AVAILABLE' for c in world.candidates()):
                        result=world.execute(pending['policy'],pending['acquisition'],pending['model'],pending['method'])
                        world.decisions[-1]['resumes_decision_id']=pending['original_decision_id']
            view=self._view(world,self._model(db));self._save(db,world,view,previous);db.commit()
        return self.episode(episode_id)
    def analyze(self,episode_id,method='compare_methods'):
        self._open()
        from .analytics import analyze
        with self.lock,self.journal.connect() as db:
            db.execute('BEGIN IMMEDIATE');world=self._world(db,episode_id);previous=world.spent
            result=analyze(world,method)
            operation=identity('analysis',[episode_id,method,world.revision])
            price=finite(result['computation_units'],0,1000000)*.001
            world.costs.record(operation,'computation',price,world.day);world.revision+=1
            result={**result,'analysis_id':operation,'charged_computation_cost':price,'synthetic':True}
            Journal.insert(db,'analyses',operation,result,episode_id)
            view=self._view(world,self._model(db));self._save(db,world,view,previous);db.commit()
        return result
    def models(self):
        with self.journal.connect() as db:return {'items':Journal.items(db,'models',limit=32),'synthetic':True}
    def experiments(self):
        with self.journal.connect() as db:return {'items':Journal.items(db,'experiments',limit=32),'synthetic':True}
    def experiment(self,experiment_id):
        with self.journal.connect() as db:
            row=db.execute('SELECT payload FROM experiments WHERE id=?',(experiment_id,)).fetchone()
            if not row:raise LookupError('LOGISTICS_EXPERIMENT_NOT_FOUND')
            return json.loads(row[0])
    def train(self,seed=42,cases=10):
        self._open();integer(seed,0,2147483647);integer(cases,10,100)
        key=identity('training-request',[seed,cases])
        with self.lock:
            with self.journal.connect() as db:
                existing=Journal.meta(db,key)
                if existing:return self.experiment(existing)
            self.training=True
            try:
                from .experiments import train_and_evaluate
                result=train_and_evaluate(seed=seed,cases=cases,evaluation_cases=min(2,cases),evaluation_days=14)
                result['report']['scope']='Dashboard preview: independent two-root evaluation per family; use the predeclared offline study for scientific conclusions.'
                model=validate(result['model']);name=identity('logistics-experiment',[seed,cases,model['model_id'],'dashboard-preview'])
                result={**result,'experiment_id':name,'synthetic':True}
                with self.journal.connect() as db:
                    db.execute('BEGIN IMMEDIATE');Journal.insert(db,'models',model['model_id'],model);Journal.insert(db,'experiments',name,result)
                    Journal.put_meta(db,'active_model',model['model_id']);Journal.put_meta(db,key,name)
                    for row in db.execute('SELECT id FROM episodes').fetchall():
                        world=self._world(db,row[0]);previous=world.spent;view=self._view(world,model);self._save(db,world,view,previous)
                    db.commit()
                return result
            finally:self.training=False
    def status(self):
        with self.journal.connect() as db:
            active=Journal.meta(db,'active_model');spent=Journal.meta(db,'acquisition_spent',0.)
            count=db.execute('SELECT count(*) FROM decisions').fetchone()[0]
        return {'schema_version':'dragonhydra.logistics-status/1','version':VERSION,'synthetic':True,'mode':'VIRTUAL_ONLY','training':self.training,'active_model_id':active,'acquisition_budget':self.limit,'acquisition_spent':spent,'acquisition_remaining':max(0,self.limit-spent),'decisions':count,'inventory_conservation':'ENFORCED_ON_EVERY_OPERATION','real_external_connections':0,'real_erp_wms_pos_tms':False,'prior_genesis61_result':'No established net predictive advantage over acquire-nothing.','new_decision_superiority':'MEASURED_EXPERIMENT_ONLY_NOT_GUARANTEED'}
    def observe(self):return {'state':'DEGRADED','reason':'VIRTUAL_EXPERIMENTAL_DOMAIN_ONLY','metrics':{'configured':True,'retained_observation_count':self.status()['decisions']},'evidence':('Inventory and logistics experimental assumptions; no commercial or real-world claim',)}
    def close(self):self.closed=True
    def stop(self):self.close()
