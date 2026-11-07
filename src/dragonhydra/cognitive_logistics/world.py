"""Seeded virtual supply chain. Decision code sees snapshot(), never this object."""
from __future__ import annotations
from copy import deepcopy
import hashlib,math,random,time
from .contracts import *
from .computation import ForecastCache

def rng(seed,*labels):return random.Random(int(digest([seed,*labels])[:16],16))
def poisson(random_source,mean):
    finite(mean,0,100)
    if mean==0:return 0
    limit=math.exp(-mean);value=1.;n=0
    while value>limit and n<1000:n+=1;value*=random_source.random()
    return n-1

class World:
    INITIAL_DAY=28
    def __init__(self,universe='stable',seed=400042,days=60,budget=10.,demand_mode='lost_sales'):
        from .state import InventoryState
        from .network import Network
        from .costs import CostLedger
        if universe not in FAMILIES or demand_mode not in ('lost_sales','backorder'):raise ValueError('LOGISTICS_VIRTUAL_CONFIGURATION_INVALID')
        integer(seed,0,2147483647);integer(days,5,120);finite(budget,0,100)
        self._family=universe;self._seed=seed;self.days=days;self.demand_mode=demand_mode
        self._demand_multiplier=1.;self._delay_extra=0
        self.day=self.INITIAL_DAY;self.revision=0;self.budget=float(budget);self.spent=0.
        self.episode_id=identity('inventory-episode',[universe,seed,days,budget,demand_mode])
        self.group_id=identity('inventory-root',seed)
        self.network_config={'nodes':{'supplier':{'kind':'supplier','capacity':5000},'warehouse':{'kind':'warehouse','capacity':200},'retail_a':{'kind':'retail','capacity':50},'retail_b':{'kind':'retail','capacity':50}},'edges':[
            {'id':'virtual-s-w','source':'supplier','dest':'warehouse','distance':20.,'lead_time':2,'unit_cost':.05,'reliability':.94,'capacity':30},
            {'id':'virtual-w-a','source':'warehouse','dest':'retail_a','distance':5.,'lead_time':1,'unit_cost':.02,'reliability':.97,'capacity':20},
            {'id':'virtual-w-b','source':'warehouse','dest':'retail_b','distance':8.,'lead_time':1,'unit_cost':.03,'reliability':.95,'capacity':20}]}
        if universe=='multi_location':
            self.network_config['nodes']['distribution_center']={'kind':'distribution','capacity':80}
            self.network_config['nodes']['supplier_b']={'kind':'supplier','capacity':2000}
            self.network_config['edges']=self.network_config['edges'][:1]+[
                {'id':'virtual-sb-w','source':'supplier_b','dest':'warehouse','distance':15.,'lead_time':3,'unit_cost':.035,'reliability':.85,'capacity':15},
                {'id':'virtual-w-dc','source':'warehouse','dest':'distribution_center','distance':3.,'lead_time':1,'unit_cost':.02,'reliability':.98,'capacity':18},
                {'id':'virtual-dc-a','source':'distribution_center','dest':'retail_a','distance':4.,'lead_time':1,'unit_cost':.02,'reliability':.98,'capacity':12},
                {'id':'virtual-dc-b','source':'distribution_center','dest':'retail_b','distance':6.,'lead_time':1,'unit_cost':.025,'reliability':.95,'capacity':12}]
        config={'nodes':deepcopy(self.network_config['nodes']),'initial':{'supplier':{SKU:1000},'warehouse':{SKU:40},'retail_a':{SKU:12},'retail_b':{SKU:12}},'shelf_life':8 if universe=='perishable' else 14,'initial_day':self.day}
        if universe=='multi_location':config['initial']['supplier_b']={SKU:500}
        self.inventory=InventoryState(config);self.network=Network(self.network_config);self.costs=CostLedger()
        self.history={loc:[] for loc in LOCATIONS}
        for loc in LOCATIONS:
            # Explicit fictional warm-up evidence, before this stock ledger starts.
            if seed%11:
                for d in range(self.INITIAL_DAY):self.history[loc].append({'day':d,'available_day':d,'sales':self._demand(loc,d),'censored':False})
        self.completed_leadtimes=[];self.acquired={};self._arrivals={};self.outcomes=[];self.decisions=[]
        self.cache=ForecastCache();self.edge_usage={};self.last_decision_day=None
        self._accounted_cost={k:0. for k in COST_KEYS};self._external_remaining=None
        self.control={'policy':'order_up_to','acquisition':'none','model':None,'method':'sba'}
        self.pending=None;self.interventions=[];self._delay_extra=0;self._demand_multiplier=1.
    @property
    def end_day(self):return self.INITIAL_DAY+self.days
    @property
    def clock(self):return (self._seed//100000)*1000000+self.day
    def _traffic(self,loc,day):return rng(self._seed,'traffic',loc,day//4).random()>=.5
    def _congested(self,day):return self._family=='supplier_disruption' and (day//8+self._seed%7)%4==0
    def _demand(self,loc,day):
        r=rng(self._seed,'demand',loc,day);base=4. if loc=='retail_a' else 5.
        if self._family=='intermittent':return poisson(r,10) if r.random()<.18 else 0
        if self._family=='seasonal':base*= (.5,.7,.8,1.,1.4,2.,1.3)[day%7]
        if self._family=='multi_location':base*=1.7 if ((day//5)%2==0)==(loc=='retail_a') else .5
        traffic=self._traffic(loc,day)
        if self._family!='perishable':base*=1.3 if traffic else .7
        else:base*=.8 if traffic else 1.2 # Unseen proxy relationship, not an oracle.
        return poisson(r,min(50,base*self._demand_multiplier))
    def _sensor(self,category):
        r=rng(self._seed,'observation',category,self.day)
        if category in ('demand_signal','downstream_intent'):
            lookahead=1 if category=='downstream_intent' else 0
            return {loc:(.8 if (self._traffic(loc,self.day+lookahead) if r.random()<.8 else not self._traffic(loc,self.day+lookahead)) else .2) for loc in LOCATIONS}
        if category=='supplier_status':return {'delay_band':'CONGESTED' if self._congested(self.day) else 'NORMAL'}
        if category=='carrier_queue':return {'queue_days':2 if self._congested(self.day) else (1 if r.random()<.15 else 0)}
        raise ValueError('LOGISTICS_INFORMATION_UNSUPPORTED')
    def candidates(self):
        result=[]
        for category in CATEGORIES:
            available=self.INITIAL_DAY+1 if category=='downstream_intent' else self.INITIAL_DAY
            if category=='carrier_queue' and self.day%13==0:available=self.day+1
            last=self.acquired.get(category)
            availability='AVAILABLE' if available<=self.day else 'PENDING'
            if last and self.day-last['observed_day']<=1:availability='ACQUIRED'
            if self.day>=self.end_day:availability='UNOBSERVABLE'
            result.append({'category':category,'availability':availability,'available_day':available,'cost':round(.015+rng(self._seed,'quote',category).random()*.035,6),'freshness_days':self.day-last['observed_day'] if last else None})
        return result
    def snapshot(self):
        summary=self.inventory.summary()
        public_conservation={k:v for k,v in summary['global'].items() if k not in ('demanded','lost_sales')}
        summary={'by_location':summary['by_location'],'conservation':public_conservation,'global':public_conservation,'orders':summary['orders'],'lots':deepcopy(self.inventory.to_dict()['lots'])}
        # Actual censored demand and privileged lead schedules do not cross here.
        remaining=self.budget-self.spent
        if self._external_remaining is not None:remaining=min(remaining,self._external_remaining)
        return {'schema_version':'dragonhydra.inventory-snapshot/1','synthetic':True,'source_mode':'VIRTUAL','episode_id':self.episode_id,'group_id':self.group_id,'revision':self.revision,'day':self.day,'decision_clock':self.clock,'days_remaining':max(0,self.end_day-self.day),'horizon':5,'demand_mode':self.demand_mode,'inventory':summary,'history':deepcopy(self.history),'completed_leadtimes':deepcopy(self.completed_leadtimes),'candidates':self.candidates(),'acquired':deepcopy(self.acquired),'budget_remaining':max(0.,remaining),'network':deepcopy(self.network_config)}
    def acquire(self,category,decision_id):
        request_id(decision_id)
        match=next((c for c in self.candidates() if c['category']==category),None)
        if not match:raise ValueError('LOGISTICS_INFORMATION_UNSUPPORTED')
        if match['availability']!='AVAILABLE':raise ValueError('LOGISTICS_INFORMATION_NOT_AVAILABLE_OR_REDUNDANT')
        if match['cost']>self.snapshot()['budget_remaining']+1e-12:raise ValueError('LOGISTICS_ACQUISITION_BUDGET_EXHAUSTED')
        receipt={'schema_version':'dragonhydra.inventory-acquisition/1','acquisition_id':identity('information',[decision_id,category,self.day]),'decision_id':decision_id,'category':category,'observed_day':self.day,'available_day':max(match['available_day'],self.day),'received_day':self.day,'actual_cost':match['cost'],'value':self._sensor(category),'source':'virtual-observation-generator','synthetic':True}
        self.costs.record(receipt['acquisition_id'],'acquisition',match['cost'],self.day)
        self.spent+=match['cost']
        if self._external_remaining is not None:self._external_remaining-=match['cost']
        self.acquired[category]=receipt;self.revision+=1
        return deepcopy(receipt)
    def _orders(self):return self.inventory.to_dict()['orders']
    def _ship(self,source,dest,quantity,decision_id,route):
        if quantity<=0:return None
        order_id=identity('shipment',[decision_id,source,dest,quantity])
        promised=self.day+max(1,route['lead_time']+2)
        self.inventory.place_order(order_id,source,dest,SKU,quantity,self.day,promised)
        self.inventory.dispatch(order_id,self.day)
        r=rng(self._seed,'actual-lead',self.day,source,dest)
        processing=1;transport=max(1,route['lead_time']);receiving=1
        disruption=(3 if self._congested(self.day) else (2 if r.random()>route['reliability'] else 0))+self._delay_extra
        actual=min(14,processing+transport+receiving+disruption)
        self._arrivals[order_id]={'due':self.day+actual,'processing':processing,'transport':transport,'receiving':receiving,'disruption':disruption,'ordered_day':self.day,'promised_day':promised,'source':source,'dest':dest,'route':route}
        self.costs.record(order_id+'-order','ordering',.5,self.day)
        self.costs.record(order_id+'-transport','transport',quantity*route['unit_cost'],self.day)
        return {'shipment_id':order_id,'source':source,'dest':dest,'quantity':quantity,'promised_day':promised,'route':route,'actual_arrival':'UNREVEALED'}
    def execute(self,policy='order_up_to',acquisition='none',model=None,method='sba',decision_id=None,force_category=None,reference=False):
        from .policies import recommend
        from .relevance import choose
        if self.day>=self.end_day:raise ValueError('LOGISTICS_EPISODE_COMPLETE')
        if policy not in POLICIES or acquisition not in ACQUISITIONS:raise ValueError('LOGISTICS_POLICY_UNSUPPORTED')
        if acquisition=='learned' and policy!='order_up_to':raise ValueError('LOGISTICS_LEARNED_CONTEXT_REQUIRES_ORDER_UP_TO')
        started=time.perf_counter();before=self.snapshot();before_cost=self.costs.summary();calls=self.cache.calls
        decision_id=decision_id or identity('inventory-decision',[self.episode_id,self.day,self.revision,policy,acquisition])
        request_id(decision_id)
        choices=choose(before,acquisition,model)
        self.pending=None
        if force_category:choices=[{'category':force_category,'action':'ACQUIRE','estimated_value':None,'cost':next(c['cost'] for c in self.candidates() if c['category']==force_category),'reason':'CONTROLLED_VIRTUAL_LABEL_PROBE'}]
        acquired=[]
        for action in choices:
            if action['action']=='ACQUIRE':acquired.append(self.acquire(action['category'],decision_id))
            if action['action']=='DEFER':self.pending={'policy':policy,'acquisition':acquisition,'model':deepcopy(model),'method':method,'original_decision_id':decision_id,'category':action['category'],'predicted_at':self.day,'estimated_value':action.get('estimated_value')}
        visible=self.snapshot();lead=self.cache.lead(visible,reference)
        forecasts={loc:self.cache.demand(visible,loc,method,5,reference) for loc in LOCATIONS}
        daily={loc:self.cache.demand(visible,loc,method,1,reference) for loc in LOCATIONS}
        shipments=[];recommendations={};candidate_units=0;route_calls=0
        # Bounded upstream order; all receiving stock is represented once.
        summary=self.inventory.summary()['by_location']
        upstream=summary['warehouse'][SKU];target=100
        amount=max(0,min(30,target-upstream['inventory_position'],upstream['capacity']-upstream['on_hand']-upstream['on_order']))
        route_metric='cost_reliability' if policy=='probabilistic_cost' else 'cost'
        if amount:
            sources={loc:summary[loc][SKU]['atp'] for loc,node in self.network_config['nodes'].items() if node['kind']=='supplier'}
            route_calls+=1;allocation=self.network.allocate(sources,'warehouse',amount,metric=route_metric,edge_usage=self.edge_usage)
            for part in allocation['allocations']:
                route=part['path'];quantity=part['qty'];shipment=self._ship(part['source'],'warehouse',quantity,decision_id,route)
                if shipment:shipments.append(shipment)
            self.edge_usage=allocation['edge_usage']
        for loc in LOCATIONS:
            row=self.inventory.summary()['by_location'][loc][SKU]
            route_calls+=1
            quote=self.network.shortest_path('warehouse',loc,metric=route_metric)
            shelf_remaining=min((lot['expiry_day']-self.day for lot in self.inventory.to_dict()['lots'] if lot['location']=='warehouse'),default=14)
            prices={'holding':.02,'ordering':.5,'shortage':5.,'transport':quote['unit_cost'] if quote else .05,'spoilage':1. if shelf_remaining<=lead['mean']+5 else 0.,'acquisition':0.,'computation':0.}
            recommendation=recommend(row,forecasts[loc],lead,policy=policy,params={'costs':prices})
            recommendation['evidence']['spoilage_proxy']='Unit excess penalty enabled when observed oldest warehouse lot life is no longer than mean lead plus five days; a heuristic, not a calibrated expiry probability.'
            recommendations[loc]=recommendation;candidate_units+=len(recommendation.get('candidates',[]))
            allocated=0
            amount=min(recommendation['quantity'],self.inventory.summary()['by_location']['warehouse'][SKU]['atp'])
            if amount:
                route_calls+=1;route=self.network.shortest_path('warehouse',loc,metric=route_metric,edge_usage=self.edge_usage)
                if route:
                    amount=min(amount,route['capacity']);shipment=self._ship('warehouse',loc,amount,decision_id,route)
                    if shipment:shipments.append(shipment);allocated=amount
                    for edge in route['edge_ids']:self.edge_usage[edge]=self.edge_usage.get(edge,0)+amount
            recommendation['allocated_quantity']=allocated
            recommendation['supply_or_route_constrained']=allocated<recommendation['quantity']
            recommendation['service_guarantee']='NOT_ESTABLISHED; forecast service assumes the recommended quantity, and realized service additionally depends on allocation, delays and model misspecification.'
        inference=sum(a.get('estimated_value') is not None for a in choices)
        actual_calls=self.cache.calls-calls
        computational_cost=actual_calls*.001+candidate_units*.00002+route_calls*.0001+inference*.0002
        self.costs.record(decision_id+'-compute','computation',computational_cost,self.day)
        self.last_decision_day=self.day;self.control={'policy':policy,'acquisition':acquisition,'model':deepcopy(model),'method':method}
        self.revision+=1
        receipt={'schema_version':'dragonhydra.inventory-decision/1','decision_id':decision_id,'episode_id':self.episode_id,'group_id':self.group_id,'day':self.day,'decision_clock':self.clock,'target':'FIVE_DAY_RELEVANT_COST','horizon':min(5,self.end_day-self.day),'policy':policy,'acquisition_policy':acquisition,'model_id':model['model_id'] if model else None,'state_revision_before':before['revision'],'state_revision_after':self.revision,'actions':choices,'acquisitions':acquired,'recommendations':recommendations,'forecasts':forecasts,'daily_forecasts':daily,'lead_forecast':lead,'shipments':shipments,'actual_forecast_calls':actual_calls,'optimization_candidates':candidate_units,'routing_calls':route_calls,'value_estimates':inference,'computation_cost':computational_cost,'cost_before':before_cost,'cost_after':self.costs.summary(),'budget_remaining':self.snapshot()['budget_remaining'],'latency_ms':(time.perf_counter()-started)*1000,'evidence_cutoff':self.day,'evaluation_state':'OUTCOME_NOT_YET_ELIGIBLE','synthetic':True}
        canonical(receipt);self.decisions.append(deepcopy(receipt));return receipt
    def step(self,policy=None,acquisition=None,model=None,method=None,reference=False):
        if self.day>=self.end_day:raise ValueError('LOGISTICS_EPISODE_COMPLETE')
        control={**self.control}
        for key,value in (('policy',policy),('acquisition',acquisition),('model',model),('method',method)):
            if value is not None:control[key]=value
        before_cost=deepcopy(self._accounted_cost)
        previous_spoilage=self.inventory.summary()['global']['spoilage']
        if self.last_decision_day!=self.day:self.execute(**control,reference=reference)
        last=self.decisions[-1];day=self.day+1
        self.inventory.expire(day,operation_id=identity('expiry',[self.episode_id,day]))
        deliveries=[];retail_cycle=False
        for order_id,schedule in sorted(list(self._arrivals.items())):
            if schedule['due']>day:continue
            status=self._orders()[order_id]['status']
            if status not in ('IN_TRANSIT','ORDERED'):
                del self._arrivals[order_id];continue
            try:self.inventory.receive(order_id,day)
            except ValueError as error:
                if 'CAPACITY' not in str(error):raise
                continue # Observable arrival waits outside facility; ownership remains transit.
            total=day-schedule['ordered_day']
            completed={'ordered_day':schedule['ordered_day'],'received_day':day,'available_day':day,'processing':schedule['processing'],'transport':schedule['transport'],'receiving':schedule['receiving'],'disruption':max(0,total-schedule['processing']-schedule['transport']-schedule['receiving'])}
            self.completed_leadtimes.append(completed)
            deliveries.append({'promised_day':schedule['promised_day'],'received_day':day,'lead_time':total})
            retail_cycle|=schedule['dest'] in LOCATIONS
            del self._arrivals[order_id]
        spoiled=self.inventory.summary()['global']['spoilage']-previous_spoilage
        self.costs.record(identity('spoil-cost',[self.episode_id,day]),'spoilage',spoiled,day)
        # Explicit external production is the only new physical stock source.
        supplier=self.inventory.summary()['by_location']['supplier'][SKU]
        if supplier['on_hand']<500:
            qty=min(1000,5000-supplier['on_hand'])
            self.inventory.produce('supplier',SKU,qty,day,operation_id=identity('production',[self.episode_id,day]))
        total_demand=total_fulfilled=total_lost=total_backorder=0;stockout=False
        for loc in LOCATIONS:
            actual=self._demand(loc,day)
            observed_available=self.inventory.summary()['by_location'][loc][SKU]['atp']
            movement=self.inventory.demand(loc,SKU,actual,day,mode=self.demand_mode,operation_id=identity('customer',[self.episode_id,day,loc]))
            fulfilled=movement['fulfilled'];lost=movement['lost_sales'];backordered=movement['backordered']
            total_demand+=actual;total_fulfilled+=fulfilled;total_lost+=lost;total_backorder+=backordered;stockout|=(fulfilled<actual)
            # The source can observe depletion, not invisible lost demand. Even
            # zero sales with zero available stock give only a lower bound.
            censored=self.demand_mode=='lost_sales' and fulfilled>=observed_available
            self.history[loc].append({'day':day,'available_day':day,'sales':actual if self.demand_mode=='backorder' else fulfilled,'censored':censored})
        self.costs.record(identity('shortage-cost',[self.episode_id,day]),'shortage',(total_lost+total_backorder)*5.,day)
        summary=self.inventory.summary()
        on_hand=summary['global']['on_hand']
        self.costs.record(identity('holding-cost',[self.episode_id,day]),'holding',(on_hand+summary['global']['in_transit'])*.02,day)
        daily=last['daily_forecasts'];combined_mean=sum(daily[loc]['mean'] for loc in LOCATIONS)
        # Convolution of independent configured Poisson daily forecasts has the summed mean.
        from .forecast import combine_demand
        aggregate=combine_demand([daily[loc] for loc in LOCATIONS])
        costs=cost_difference(before_cost,self.costs.summary())
        self._accounted_cost=self.costs.summary()
        row={'day':day,'available_day':day,'demand':total_demand,'fulfilled':total_fulfilled,'backordered':total_backorder,'lost_sales':total_lost,'on_hand':on_hand,'stockout':stockout,'cycle_complete':retail_cycle,'deliveries':deliveries,'forecast':{'mean':aggregate['mean'],'quantiles':aggregate['quantiles'],'interval90':aggregate['interval90'],'horizon':1,'cutoff':self.day},'costs':costs,'spoiled':spoiled,'actual_demand_id':identity('demand-outcome',[self._seed,day,total_demand]),'synthetic':True}
        self.outcomes.append(row);self.day=day;self.revision+=1;self.edge_usage={}
        self.inventory.verify_conservation();canonical(row)
        return deepcopy(row)
    def run(self,count=None,**control):
        count=min(count if count is not None else self.end_day-self.day,self.end_day-self.day)
        for _ in range(integer(count,0,120)):self.step(**control)
        return self
    def to_dict(self):
        result={'schema_version':'dragonhydra.inventory-private-world/1','universe':self._family,'seed':self._seed,'days':self.days,'budget':self.budget,'demand_mode':self.demand_mode,'day':self.day,'revision':self.revision,'spent':self.spent,'network_config':self.network_config,'inventory':self.inventory.to_dict(),'costs':self.costs.to_dict(),'history':self.history,'completed_leadtimes':self.completed_leadtimes,'acquired':self.acquired,'private_arrivals':self._arrivals,'outcomes':self.outcomes,'decisions':self.decisions[-1:],'cache':self.cache.to_dict(),'edge_usage':self.edge_usage,'last_decision_day':self.last_decision_day,'control':self.control,'pending':self.pending,'interventions':self.interventions,'delay_extra':self._delay_extra,'demand_multiplier':self._demand_multiplier,'accounted_cost':self._accounted_cost,'external_remaining':self._external_remaining}
        return deepcopy(result)
    @classmethod
    def from_dict(cls,data):
        from .state import InventoryState
        from .network import Network
        from .costs import CostLedger
        if data.get('schema_version')!='dragonhydra.inventory-private-world/1':raise ValueError('LOGISTICS_WORLD_SCHEMA_MISMATCH')
        obj=cls.__new__(cls)
        obj._family=data['universe'];obj._seed=data['seed'];obj.days=data['days'];obj.budget=data['budget'];obj.demand_mode=data['demand_mode']
        obj.episode_id=identity('inventory-episode',[obj._family,obj._seed,obj.days,obj.budget,obj.demand_mode]);obj.group_id=identity('inventory-root',obj._seed)
        obj.inventory=InventoryState.from_dict(data['inventory']);obj.costs=CostLedger.from_dict(data['costs']);obj.network=Network(data['network_config']);obj.cache=ForecastCache.from_dict(data['cache'])
        for key in ('day','revision','spent','network_config','history','completed_leadtimes','acquired','outcomes','decisions','edge_usage','last_decision_day','control','pending','interventions'):setattr(obj,key,deepcopy(data[key]))
        obj._arrivals=deepcopy(data['private_arrivals']);obj._delay_extra=data['delay_extra'];obj._demand_multiplier=data['demand_multiplier'];obj._accounted_cost=deepcopy(data['accounted_cost']);obj._external_remaining=data['external_remaining'];obj.inventory.verify_conservation();return obj
    def clone(self):return self.from_dict(self.to_dict())
    def metrics(self,naive_scale=None):
        from .metrics import evaluate_outcomes,FIELDS
        result=evaluate_outcomes([{k:r[k] for k in FIELDS} for r in self.outcomes],cutoff=self.day,naive_scale=naive_scale)
        result['costs']={k:self.costs.summary()[k] for k in COST_KEYS}
        result['total_cost']=self.costs.summary()['total']
        result['unsettled_current_period_costs']=cost_difference(self._accounted_cost,self.costs.summary())
        due=[o for o in self._orders().values() if o['promised_day']<=self.day and self.network_config['nodes'][o['source']]['kind']=='supplier']
        success=sum(o['received_day'] is not None and o['received_day']<=o['promised_day'] and o['received_qty']==o['ordered_qty'] for o in due)
        result['completed_delivery_on_time_rate']=result['supplier_reliability']
        result['supplier_reliability']=success/len(due) if due else None
        result['supplier_reliability_denominator']=len(due)
        result['supplier_reliability_scope']='All supplier-origin orders with observable due promises, including spoiled and overdue failures; future promises excluded.'
        result['backorder_outstanding']=sum(self.inventory.summary()['by_location'][loc][SKU]['backorder'] for loc in LOCATIONS)
        return result
    def intervene(self,kind,amount=None):
        """Explicit bounded simulator interventions; no explanation executes code."""
        if self.day>=self.end_day:raise ValueError('LOGISTICS_INTERVENTION_AFTER_COMPLETION')
        operation=identity('intervention',[self.episode_id,self.day,self.revision,kind,amount])
        if kind=='supplier_delay':self._delay_extra=integer(2 if amount is None else amount,0,5)
        elif kind=='capacity_reduction':
            factor=finite(.75 if amount is None else amount,.25,1)
            current=self.inventory.summary()['by_location']['warehouse'][SKU]
            capacity=int(current['capacity']*factor)
            self.inventory.set_capacity('warehouse',capacity,self.day,operation)
            self.network_config['nodes']['warehouse']['capacity']=capacity
        elif kind=='demand_shock':self._demand_multiplier=finite(1.5 if amount is None else amount,.25,3)
        elif kind=='policy_change':
            if amount not in (None,'base_stock'):raise ValueError('LOGISTICS_INTERVENTION_POLICY_UNSUPPORTED')
            self.control['policy']='base_stock'
        elif kind=='shelf_life':self.inventory.set_shelf_life(integer(8 if amount is None else amount,1,30),self.day,operation)
        else:raise ValueError('LOGISTICS_INTERVENTION_UNSUPPORTED')
        from .network import Network
        self.network=Network(self.network_config);self.revision+=1
        receipt={'intervention_id':operation,'kind':kind,'amount':amount,'day':self.day,'group_id':self.group_id,'classification':'TESTED_INTERVENTION','causal_scope':'Only the explicitly changed virtual mechanism; no real-world causal claim.'}
        self.interventions.append(receipt);return receipt
