"""Past-only learned acquisition value in virtual operational-cost units."""
from __future__ import annotations
from copy import deepcopy
from collections import defaultdict
import math,random,statistics
from .contracts import *
from ..future_relevance.learning import _solve

FEATURES=('intercept','stock_fraction','position_fraction','backorder_fraction','transit_fraction','recent_sales','zero_fraction','censored_fraction','sales_variation','lead_mean','remaining_fraction','budget_fraction','cost','pending','delay','clock_sin','clock_cos','backorder_mode','visible_signal_mean','visible_congestion','visible_queue','warehouse_shelf_remaining','network_size')+tuple('known_'+c for c in CATEGORIES)

def features(snapshot,category):
    if snapshot.get('schema_version')!='dragonhydra.inventory-snapshot/1' or snapshot.get('synthetic') is not True or category not in CATEGORIES:raise ValueError('LOGISTICS_RELEVANCE_PUBLIC_SNAPSHOT_REQUIRED')
    day=integer(snapshot['day'],0,100000);visible=visible_evidence(snapshot);candidate=next(c for c in snapshot['candidates'] if c['category']==category)
    rows=[snapshot['inventory']['by_location'][loc][SKU] for loc in LOCATIONS]
    history=[r for loc in LOCATIONS for r in snapshot['history'][loc][-7:]]
    if any(r['available_day']>day or r['day']>day for r in history):raise ValueError('LOGISTICS_FUTURE_FEATURE_LEAKAGE')
    capacity=sum(r['capacity'] for r in rows) or 1
    values=[r['sales'] for r in history]
    past=[r for r in snapshot['completed_leadtimes'] if r['available_day']<=day and r['received_day']<=day]
    result={'intercept':1.,'stock_fraction':sum(r['on_hand'] for r in rows)/capacity,'position_fraction':sum(r['inventory_position'] for r in rows)/capacity,'backorder_fraction':sum(r['backorder'] for r in rows)/capacity,'transit_fraction':sum(r['in_transit'] for r in rows)/capacity,'recent_sales':statistics.fmean(values)/20 if values else 0.,'zero_fraction':sum(v==0 for v in values)/len(values) if values else 0.,'censored_fraction':sum(r['censored'] for r in history)/len(history) if history else 0.,'sales_variation':statistics.pstdev(values)/20 if len(values)>1 else 0.,'lead_mean':statistics.fmean(r['received_day']-r['ordered_day'] for r in past)/14 if past else 3/14,'remaining_fraction':min(5,snapshot['days_remaining'])/5,'budget_fraction':snapshot['budget_remaining']/100,'cost':candidate['cost'],'pending':float(candidate['availability']=='PENDING'),'delay':max(0,candidate['available_day']-day)/5,'clock_sin':math.sin(2*math.pi*day/7),'clock_cos':math.cos(2*math.pi*day/7),'backorder_mode':float(snapshot['demand_mode']=='backorder')}
    for c in CATEGORIES:result['known_'+c]=float(c in visible)
    signals=[value for c,row in visible.items() if c in ('demand_signal','downstream_intent') for value in row['value'].values()]
    result['visible_signal_mean']=statistics.fmean(signals) if signals else 0.
    result['visible_congestion']=float(visible.get('supplier_status',{}).get('value',{}).get('delay_band')=='CONGESTED')
    result['visible_queue']=visible.get('carrier_queue',{}).get('value',{}).get('queue_days',0)/5
    result['warehouse_shelf_remaining']=min((lot['expiry_day']-day for lot in snapshot['inventory']['lots'] if lot['location']=='warehouse'),default=0)/30
    result['network_size']=len(snapshot['network']['nodes'])/32
    for value in result.values():finite(value,-1e6,1e6)
    return {key:result[key] for key in FEATURES}

def _seal(payload):
    h=digest(payload);return {**deepcopy(payload),'content_sha256':h,'model_id':'logistics-ridge/1-'+h[:24]}
def validate(model):
    if not isinstance(model,dict) or model.get('schema_version')!='dragonhydra.logistics-relevance-model/1' or model.get('frozen') is not True:raise ValueError('LOGISTICS_FROZEN_MODEL_REQUIRED')
    payload={k:v for k,v in model.items() if k not in ('content_sha256','model_id')};expected=_seal(payload)
    if model.get('content_sha256')!=expected['content_sha256'] or model.get('model_id')!=expected['model_id'] or model.get('features')!=list(FEATURES):raise ValueError('LOGISTICS_MODEL_CONTENT_MISMATCH')
    if model['available_clock']<model['training_label_cutoff']:raise ValueError('LOGISTICS_MODEL_PRECEDES_TRAINING_LABELS')
    if set(model['parameters'])!=set(CATEGORIES):raise ValueError('LOGISTICS_MODEL_CATEGORY_SCHEMA')
    for row in model['parameters'].values():
        if set(row)!={'centers','scales','coefficients'} or any(len(values)!=len(FEATURES) for values in row.values()):raise ValueError('LOGISTICS_MODEL_MATRIX_SHAPE')
        for value in row['centers']+row['coefficients']:finite(value,-1e12,1e12)
        for value in row['scales']:finite(value,1e-12,1e12)
    if 'selection' in model:
        selection=model['selection']
        if set(model['training_group_ids'])&set(selection['validation_group_ids']):raise ValueError('LOGISTICS_MODEL_SHARED_PREFIX_LEAKAGE')
        if model['training_label_cutoff']>selection['validation_decision_cutoff'] or model['available_clock']<selection['validation_label_cutoff']:raise ValueError('LOGISTICS_MODEL_SELECTION_TIME_LEAKAGE')
    return model
def _validate_rows(rows,split):
    if not rows:raise ValueError('LOGISTICS_TRAINING_EXAMPLES_REQUIRED')
    for row in rows:
        if row['split']!=split or row['category'] not in CATEGORIES or set(row['features'])!=set(FEATURES):raise ValueError('LOGISTICS_ROW_SCHEMA_OR_SPLIT_INVALID')
        if not row['decision_clock']<=row['acquisition_clock']<row['label_available_clock']:raise ValueError('LOGISTICS_LABEL_TEMPORAL_LEAKAGE')
        if row['feature_cutoff']!=row['decision_clock']:raise ValueError('LOGISTICS_FEATURE_CUTOFF_LEAKAGE')
        finite(row['label'],-1e6,1e6)
        for value in row['features'].values():finite(value,-1e6,1e6)
        if 'snapshot' in row and (row['snapshot_sha256']!=digest(row['snapshot']) or row['features']!=features(row['snapshot'],row['category']) or row['snapshot']['decision_clock']!=row['decision_clock']):raise ValueError('LOGISTICS_TRAINING_FEATURE_PROVENANCE_MISMATCH')
    return rows
def fit(rows,regularization=1.):
    rows=_validate_rows(rows,'TRAIN');finite(regularization,.0001,1000)
    groups={r['group_id'] for r in rows}
    if len(groups)<3:raise ValueError('LOGISTICS_INDEPENDENT_TRAIN_GROUPS_REQUIRED')
    parameters={};uncertainty={}
    for category in CATEGORIES:
        selected=[r for r in rows if r['category']==category]
        if len(selected)<3:raise ValueError('LOGISTICS_CATEGORY_TRAINING_REQUIRED')
        centers=[0. if name=='intercept' else statistics.fmean(r['features'][name] for r in selected) for name in FEATURES]
        scales=[1. if name=='intercept' else max(1e-8,statistics.pstdev(r['features'][name] for r in selected)) for name in FEATURES]
        x=[[(r['features'][k]-c)/s for k,c,s in zip(FEATURES,centers,scales)] for r in selected]
        size=len(FEATURES);matrix=[[math.fsum(v[i]*v[j] for v in x)+(regularization if i==j else 0) for j in range(size)] for i in range(size)]
        vector=[math.fsum(v[i]*r['label'] for v,r in zip(x,selected)) for i in range(size)]
        coefficients=_solve(matrix,vector)
        parameters[category]={'centers':centers,'scales':scales,'coefficients':coefficients}
        residuals=[r['label']-math.fsum(a*b for a,b in zip(coefficients,v)) for r,v in zip(selected,x)]
        per_group=defaultdict(list)
        for r,error in zip(selected,residuals):per_group[r['group_id']].append(error)
        means=[statistics.fmean(errors) for errors in per_group.values()]
        uncertainty[category]={'training_rows':len(selected),'root_groups':len(per_group),'residual_rmse':math.sqrt(statistics.fmean(e*e for e in residuals)),'root_mean_residual_se':statistics.stdev(means)/math.sqrt(len(means)) if len(means)>1 else None,'calibration_state':'UNVERIFIED'}
    return _seal({'schema_version':'dragonhydra.logistics-relevance-model/1','frozen':True,'features':list(FEATURES),'parameters':parameters,'uncertainty':uncertainty,'regularization':regularization,'threshold':0.,'training_group_ids':sorted(groups),'training_label_cutoff':max(r['label_available_clock'] for r in rows),'available_clock':max(r['label_available_clock'] for r in rows),'cost_unit':'VIRTUAL_CREDIT','target':'FIVE_DAY_GROSS_COST_REDUCTION_AT_ELIGIBLE_ACQUISITION','prior_genesis61_result':'NO_ESTABLISHED_ADVANTAGE_OVER_ACQUIRE_NONE'})
def predict_features(x,category,model):
    p=model['parameters'][category]
    value=math.fsum(coef*(x[name]-center)/scale for name,center,scale,coef in zip(FEATURES,p['centers'],p['scales'],p['coefficients']))
    return finite(value,-1e9,1e9)
def estimate(snapshot,category,model):
    validate(model)
    if model['available_clock']>snapshot['decision_clock']:raise ValueError('LOGISTICS_MODEL_NOT_AVAILABLE_AT_DECISION')
    x=features(snapshot,category);quote=next(c['cost'] for c in snapshot['candidates'] if c['category']==category)
    return {'category':category,'estimated_value':predict_features(x,category,model),'estimated_cost':quote,'state':'EXPERIMENTAL_NOT_CALIBRATED','model_id':model['model_id'],'uncertainty':model['uncertainty'][category]}
def select(train,validation):
    _validate_rows(train,'TRAIN');_validate_rows(validation,'VALIDATION')
    t={r['group_id'] for r in train};v={r['group_id'] for r in validation}
    if t&v:raise ValueError('LOGISTICS_SHARED_PREFIX_SPLIT_LEAKAGE')
    if max(r['label_available_clock'] for r in train)>min(r['decision_clock'] for r in validation):raise ValueError('LOGISTICS_TRAIN_LABELS_AFTER_VALIDATION_DECISION')
    best=None;trials=[]
    for regularization in (.1,1.,10.):
        model=fit(train,regularization)
        errors=[(predict_features(r['features'],r['category'],model)-r['label'])**2 for r in validation]
        mse=statistics.fmean(errors);trials.append({'regularization':regularization,'mse':mse})
        if best is None or mse<best[0]:best=(mse,model)
    payload={k:v for k,v in best[1].items() if k not in ('content_sha256','model_id')}
    payload['available_clock']=max(payload['training_label_cutoff'],max(r['label_available_clock'] for r in validation))
    payload['selection']={'validation_group_ids':sorted(v),'validation_decision_cutoff':min(r['decision_clock'] for r in validation),'validation_label_cutoff':max(r['label_available_clock'] for r in validation),'trials':trials,'selection_mse':best[0],'no_final_test_access':True}
    return _seal(payload)

def choose(snapshot,strategy,model=None):
    if strategy not in ACQUISITIONS:raise ValueError('LOGISTICS_ACQUISITION_POLICY_UNSUPPORTED')
    candidates=snapshot['candidates'];budget=finite(snapshot['budget_remaining'],0,100);actions=[]
    randomizer=random.Random(int(digest([snapshot['episode_id'],snapshot['day'],'random-acquisition'])[:16],16))
    predictions={}
    if strategy=='learned':
        validate(model)
        if snapshot['days_remaining']<5:return [{'action':'DO_NOTHING','category':None,'estimated_value':None,'reason':'TRUNCATED_VALUE_HORIZON_NOT_TRAINED'}]
        predictions={c['category']:estimate(snapshot,c['category'],model)['estimated_value'] for c in candidates if c['availability'] in ('AVAILABLE','PENDING')}
        candidates=sorted(candidates,key=lambda c:predictions.get(c['category'],-1e12)-c['cost'],reverse=True)
    for c in candidates:
        category=c['category'];value=predictions.get(category)
        useful=False
        if strategy=='all':useful=True
        elif strategy=='random':useful=randomizer.random()<.3
        elif strategy=='handcrafted':
            x=features(snapshot,category)
            useful=(category=='demand_signal' and x['censored_fraction']>0) or (category=='supplier_status' and x['transit_fraction']>.15)
        elif strategy=='learned':useful=value is not None and value>c['cost']+.0002
        reason='NEGATIVE_OR_UNVERIFIED_VALUE'
        if c['availability'] in ('ACQUIRED','UNOBSERVABLE'):action='IGNORE';reason='REDUNDANT_OR_UNOBSERVABLE'
        elif not useful:action='IGNORE'
        elif c['cost']>budget+1e-12:action='IGNORE';reason='BUDGET_EXHAUSTED'
        elif c['availability']=='PENDING':action='DEFER';reason='NOT_YET_OBSERVABLE'
        else:action='ACQUIRE';reason='SELECTED_WITHIN_BUDGET';budget-=c['cost']
        actions.append({'category':category,'action':action,'estimated_value':value,'estimated_cost':c['cost'],'predicted_at':snapshot['day'],'reason':reason})
    if not any(a['action'] in ('ACQUIRE','DEFER') for a in actions):actions.append({'action':'DO_NOTHING','category':None,'estimated_value':None,'reason':'NO_JUSTIFIED_ADDITIONAL_INFORMATION'})
    return actions
