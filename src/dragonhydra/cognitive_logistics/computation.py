"""Explicit, testable forecast dependencies; cached and reference results agree."""
from copy import deepcopy
from .contracts import LOCATIONS,canonical,digest,visible_evidence

class ForecastCache:
    def __init__(self):
        self.values={};self.calls=0;self.hits=0
    def to_dict(self):
        return {'calls':self.calls,'hits':self.hits,'entries':[{'key':list(k),'value':deepcopy(v),'sha256':digest([list(k),v])} for k,v in self.values.items()]}
    @classmethod
    def from_dict(cls,data):
        obj=cls()
        if len(data['entries'])>128:raise ValueError('LOGISTICS_CACHE_BOUND_EXCEEDED')
        for row in data['entries']:
            if digest([row['key'],row['value']])!=row['sha256']:raise ValueError('LOGISTICS_CACHE_HASH_MISMATCH')
            obj.values[tuple(row['key'])]=deepcopy(row['value'])
        obj.calls=data['calls'];obj.hits=data['hits'];return obj
    def _get(self,key,calculate,reference):
        if not reference and key in self.values:
            self.hits+=1;return deepcopy(self.values[key])
        value=calculate();canonical(value);self.calls+=1
        if not reference:
            if len(self.values)>=128:self.values.pop(next(iter(self.values)))
            self.values[key]=deepcopy(value)
        return value
    def demand(self,snapshot,location,method='sba',horizon=5,reference=False):
        from .forecast import forecast_demand
        day=snapshot['day'];history=snapshot['history'][location]
        evidence={k:v for k,v in visible_evidence(snapshot).items() if k in ('demand_signal','downstream_intent')}
        key=('demand',location,method,horizon,digest([history,evidence,day]))
        def calculate():
            result=forecast_demand(history,method=method,horizon=horizon,cutoff=day)
            # Observed synthetic proxy, not privileged future demand or an AI number.
            factors=[]
            for category,row in evidence.items():
                index=row['value'].get(location,.5)
                factors.append(1.3 if index>=.5 else .7)
            factor=sum(factors)/len(factors) if factors else 1.
            if factor!=1:
                # Re-run the registered probabilistic constructor at the adjusted
                # point estimate; no pre-existing sports probability is reused.
                from .forecast import rescale_demand
                result=rescale_demand(result,factor)
            result['acquired_evidence_ids']=[row['acquisition_id'] for row in evidence.values()]
            return result
        return self._get(key,calculate,reference)
    def lead(self,snapshot,reference=False):
        from .forecast import forecast_leadtime
        day=snapshot['day'];history=snapshot['completed_leadtimes']
        evidence={k:v for k,v in visible_evidence(snapshot).items() if k in ('supplier_status','carrier_queue')}
        key=('lead',digest([history,evidence,day]))
        def calculate():
            result=forecast_leadtime(history,cutoff=day)
            shift=0
            if 'supplier_status' in evidence and evidence['supplier_status']['value']['delay_band']=='CONGESTED':shift+=2
            if 'carrier_queue' in evidence:shift+=evidence['carrier_queue']['value']['queue_days']
            if shift:
                combined={}
                capped_mass=0.
                for row in result['pmf']:
                    if row['days']+shift>14:capped_mass+=row['probability']
                    n=min(14,row['days']+shift);combined[n]=combined.get(n,0)+row['probability']
                result['pmf']=[{'days':n,'probability':p} for n,p in sorted(combined.items())]
                result['mean']=sum(n*p for n,p in combined.items())
                result['variance']=sum((n-result['mean'])**2*p for n,p in combined.items())
                result['components_scope']='Unadjusted completed-history component marginals; the conditional total additionally includes observed proxy delays and a 14-day cap.'
                result['conditional_delay_days']=shift
                result['cap_probability_mass']=capped_mass
                result['assumptions']=list(result['assumptions'])+['Observed virtual congestion/queue shifts a bounded lead-time mixture; individual future arrival remains hidden.']
            result['acquired_evidence_ids']=[row['acquisition_id'] for row in evidence.values()]
            return result
        return self._get(key,calculate,reference)
