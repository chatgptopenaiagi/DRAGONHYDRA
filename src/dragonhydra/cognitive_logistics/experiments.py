"""Frozen, coupled operational experiments. Final worlds never feed model fitting."""
from __future__ import annotations
from collections import defaultdict
from copy import deepcopy
import math,random,statistics,time
from .contracts import *
from .world import World
from .relevance import features,select,validate,predict_features,_seal

ARMS=tuple((p,'none') for p in POLICIES)+tuple(('order_up_to',a) for a in ACQUISITIONS if a!='none')
BASELINE='order_up_to/none'

def groups(values):
    grouped=defaultdict(list)
    for group,value in values:grouped[group].append(finite(value,-1e12,1e12))
    means=[statistics.fmean(rows) for rows in grouped.values()]
    if not means:return {'mean':None,'standard_error':None,'interval95':None,'groups':0}
    mean=statistics.fmean(means);se=statistics.stdev(means)/math.sqrt(len(means)) if len(means)>1 else None
    return {'mean':mean,'standard_error':se,'interval95':[mean-1.96*se,mean+1.96*se] if se is not None else None,'groups':len(means),'method':'Equal-weight independent-root means, normal approximation; family variants/branches within roots are dependent. No multiplicity adjustment.'}
def _seeds(seed,cases,split):
    integer(seed,0,2147483647);integer(cases,1,100)
    offset={'TRAIN':0,'VALIDATION':100000,'FINAL_TEST':200000}[split]
    return [offset+n for n in random.Random(int(digest([seed,split])[:16],16)).sample(range(1000,90000),100)[:cases]]
def make_rows(seed=42,cases=10,split='TRAIN'):
    if split not in ('TRAIN','VALIDATION'):raise ValueError('LOGISTICS_LABEL_PARTITION_INVALID')
    families=TRAIN_FAMILIES if split=='TRAIN' else VALIDATION_FAMILIES
    rows=[]
    for root_seed in _seeds(seed,cases,split):
        for family in families:
            base=World(family,root_seed,days=30,budget=(.25,2.,10.)[root_seed%3],demand_mode='backorder' if root_seed%4==0 else 'lost_sales')
            for prefix in (0,7):
                if prefix:base.run(7,policy='order_up_to',acquisition='none')
                context=base.clone()
                if prefix:
                    known=CATEGORIES[root_seed%len(CATEGORIES)]
                    if next(c['availability'] for c in context.candidates() if c['category']==known)=='AVAILABLE':context.acquire(known,identity('prior-known-context',[context.episode_id,context.day,known]))
                public=context.snapshot();end=context.day+5
                for candidate in public['candidates']:
                    if candidate['availability'] not in ('AVAILABLE','PENDING'):continue
                    common=context.clone()
                    delay=max(0,candidate['available_day']-common.day)
                    if delay>=5:continue
                    if delay:common.run(delay,policy='order_up_to',acquisition='none')
                    before,after=common.clone(),common.clone()
                    acquisition_clock=after.clock
                    probe=after.acquire(candidate['category'],identity('training-acquisition',[split,public['episode_id'],public['day'],candidate['category']]))
                    before.run(end-before.day,policy='order_up_to',acquisition='none')
                    after.run(end-after.day,policy='order_up_to',acquisition='none')
                    if [r['actual_demand_id'] for r in before.outcomes]!=[r['actual_demand_id'] for r in after.outcomes]:raise ValueError('LOGISTICS_ACQUISITION_CHANGED_HIDDEN_DEMAND')
                    value=before.costs.summary()['total']-(after.costs.summary()['total']-probe['actual_cost'])
                    row={'schema_version':'dragonhydra.logistics-value-row/1','split':split,'group_id':public['group_id'],'episode_id':public['episode_id'],'category':candidate['category'],'decision_clock':public['decision_clock'],'feature_cutoff':public['decision_clock'],'acquisition_clock':acquisition_clock,'label_available_clock':after.clock,'snapshot_sha256':digest(public),'snapshot':public,'features':features(public,candidate['category']),'label':value,'actual_acquisition_cost':probe['actual_cost'],'cost_without':before.costs.summary()['total'],'cost_with_excluding_acquisition':after.costs.summary()['total']-probe['actual_cost'],'label_scope':'Coupled five-day gross cost reduction; same observed prefix through eligibility; the acquisition fee is removed before fitting value.'}
                    if not row['decision_clock']<=row['acquisition_clock']<row['label_available_clock']:raise ValueError('LOGISTICS_GENERATED_LABEL_TIME_INVALID')
                    rows.append(row)
    return rows
def train_model(seed=42,cases=10):
    train=make_rows(seed,cases,'TRAIN');validation=make_rows(seed,cases,'VALIDATION')
    model=select(train,validation)
    # A fixed past TRAIN scaling reference, never calculated from final outcomes.
    errors=[];seen=set()
    for row in train:
        key=(row['episode_id'],row['decision_clock'])
        if key in seen:continue
        seen.add(key);history=row['snapshot']['history']
        by_location={loc:{r['day']:r['sales'] for r in history[loc] if not r['censored']} for loc in LOCATIONS}
        common=sorted(set(by_location[LOCATIONS[0]])&set(by_location[LOCATIONS[1]]))
        totals={d:sum(by_location[loc][d] for loc in LOCATIONS) for d in common}
        errors.extend(abs(totals[d]-totals[d-1]) for d in common if d-1 in totals)
    scale=statistics.fmean(errors) if errors else None
    payload={k:v for k,v in model.items() if k not in ('content_sha256','model_id')}
    payload['train_naive_scale']=scale;model=_seal(payload)
    payload={k:v for k,v in model.items() if k not in ('content_sha256','model_id')}
    payload['training_pending_mean']={category:statistics.fmean(r['label'] for r in train if r['category']==category and r['acquisition_clock']>r['decision_clock']) if any(r['category']==category and r['acquisition_clock']>r['decision_clock'] for r in train) else None for category in CATEGORIES}
    model=_seal(payload)
    summary={'train_rows':len(train),'validation_rows':len(validation),'train_root_groups':len({r['group_id'] for r in train}),'validation_root_groups':len({r['group_id'] for r in validation}),'pending_train_rows':sum(r['acquisition_clock']>r['decision_clock'] for r in train),'train_rows_sha256':digest(train),'validation_rows_sha256':digest(validation),'train_families':list(TRAIN_FAMILIES),'validation_families':list(VALIDATION_FAMILIES),'available_clock':model['available_clock'],'final_worlds_constructed':False,'feature_provenance_verified':all(r['features']==features(r['snapshot'],r['category']) and digest(r['snapshot'])==r['snapshot_sha256'] for r in train+validation)}
    return {'model':model,'training_summary':summary,'training_rows':train,'validation_rows':validation}
def _forecast_evaluation(world,methods):
    """Record predictions before outcomes on one common baseline-observed history."""
    from .forecast import forecast_demand
    book={method:[] for method in methods};calls=0
    while world.day<world.end_day:
        snapshot=world.snapshot();forecasts={}
        for method in methods:
            forecasts[method]={loc:forecast_demand(snapshot['history'][loc],method=method,horizon=1,cutoff=world.day) for loc in LOCATIONS};calls+=len(LOCATIONS)
        world.step(policy='order_up_to',acquisition='none')
        row=world.outcomes[-1]
        for method in methods:
            mean=sum(f['mean'] for f in forecasts[method].values());error=mean-row['demand']
            book[method].append({'group_id':world.group_id,'error':error,'absolute_error':abs(error),'prediction_day':snapshot['day'],'outcome_day':row['day']})
    return book,calls
def evaluate(model,seed=42,cases=10,days=20,forecast_comparison=True):
    from .forecast import METHODS
    model=validate(model);integer(days,10,60)
    frozen=model['content_sha256'];used=set(model['training_group_ids'])|set(model['selection']['validation_group_ids'])
    results=defaultdict(list);forecast_rows=defaultdict(list);diagnostic_calls=0;records=[];prospective=[]
    for root_seed in _seeds(seed,cases,'FINAL_TEST'):
        for family in (*TRAIN_FAMILIES,*UNSEEN_FAMILIES):
            base=World(family,root_seed,days=days)
            if base.group_id in used or base.clock<=model['available_clock']:raise ValueError('LOGISTICS_FINAL_ROOT_OR_TIME_LEAKAGE')
            public_hash=digest(base.snapshot());actual_ids=None
            for policy,acquisition in ARMS:
                world=base.clone()
                if digest(world.snapshot())!=public_hash:raise ValueError('LOGISTICS_BASELINE_OBSERVATION_MISMATCH')
                world.run(policy=policy,acquisition=acquisition,model=model if acquisition=='learned' else None)
                current_ids=[r['actual_demand_id'] for r in world.outcomes]
                if actual_ids is None:actual_ids=current_ids
                elif current_ids!=actual_ids:raise ValueError('LOGISTICS_POLICY_CHANGED_UNDERLYING_DEMAND')
                metrics=world.metrics(model.get('train_naive_scale'))
                row={'episode_id':base.episode_id,'group_id':base.group_id,'family':family,'rule_scope':'FAMILIAR' if family in TRAIN_FAMILIES else 'UNSEEN','inventory_policy':policy,'acquisition_policy':acquisition,'metrics':metrics,'costs':world.costs.summary(),'acquisitions':sum(len(d['acquisitions']) for d in world.decisions),'actual_forecast_calls':world.cache.calls,'decision_trace_sha256':digest([{k:v for k,v in d.items() if k!='latency_ms'} for d in world.decisions]),'conservation_valid':world.inventory.verify_conservation()['valid'],'acquisition_budget_remaining':world.budget-world.spent}
                results[policy+'/'+acquisition].append(row);records.append(row)
            if forecast_comparison:
                book,calls=_forecast_evaluation(base.clone(),METHODS);diagnostic_calls+=calls
                for method,rows in book.items():forecast_rows[method].extend(rows)
            # Every final root/family gets an evaluation-only prospective probe;
            # no selection based on whether the model predicted a large gain.
            initial=base.snapshot();category='downstream_intent'
            candidate=next(c for c in initial['candidates'] if c['category']==category)
            predicted=predict_features(features(initial,category),category,model)
            common=base.clone();common.run(candidate['available_day']-common.day)
            before,after=common.clone(),common.clone()
            receipt=after.acquire(category,identity('final-prospective',[base.episode_id,category]))
            before.run(base.day+5-before.day);after.run(base.day+5-after.day)
            actual=before.costs.summary()['total']-(after.costs.summary()['total']-receipt['actual_cost'])
            prospective.append({'group_id':base.group_id,'family':family,'predicted_at':initial['decision_clock'],'acquired_at':(root_seed//100000)*1000000+receipt['received_day'],'predicted_gross_value':predicted,'observed_gross_value':actual})
    if validate(model)['content_sha256']!=frozen:raise ValueError('LOGISTICS_FINAL_EVALUATION_CHANGED_MODEL')
    baseline={r['episode_id']:r for r in results[BASELINE]};comparison=[]
    for arm,rows in results.items():
        def paired(scope=None,key='total_cost'):
            chosen=[r for r in rows if scope is None or r['rule_scope']==scope]
            return groups([(r['group_id'],r['metrics'][key]-baseline[r['episode_id']]['metrics'][key]) for r in chosen if r['metrics'][key] is not None and baseline[r['episode_id']]['metrics'][key] is not None])
        sample=rows[0]
        row={'inventory_policy':sample['inventory_policy'],'acquisition_policy':sample['acquisition_policy'],'cases':len(rows),'independent_root_groups':len({r['group_id'] for r in rows}),'total_cost':statistics.fmean(r['metrics']['total_cost'] for r in rows),'fill_rate':statistics.fmean(r['metrics']['fill_rate'] for r in rows if r['metrics']['fill_rate'] is not None),'cycle_service_level':statistics.fmean(r['metrics']['cycle_service_level'] for r in rows if r['metrics']['cycle_service_level'] is not None),'forecast_mae':statistics.fmean(r['metrics']['forecast_mae'] for r in rows),'acquisition_cost':statistics.fmean(r['costs']['acquisition'] for r in rows),'computation_cost':statistics.fmean(r['costs']['computation'] for r in rows),'all_cost_components':{k:statistics.fmean(r['costs'][k] for r in rows) for k in COST_KEYS},'paired_cost_vs_baseline':paired(),'paired_fill_rate_vs_baseline':paired(key='fill_rate'),'familiar':{'cost_difference':paired('FAMILIAR'),'fill_difference':paired('FAMILIAR','fill_rate')},'unseen_rules':{'cost_difference':paired('UNSEEN'),'fill_difference':paired('UNSEEN','fill_rate')},'physical_conservation_all_pass':all(r['conservation_valid'] for r in rows),'budget_violations':sum(r['acquisition_budget_remaining']< -1e-9 for r in rows),'acquisitions':sum(r['acquisitions'] for r in rows),'actual_forecast_calls':sum(r['actual_forecast_calls'] for r in rows)}
        comparison.append(row)
    forecasts=[{'method':method,'predictions':len(rows),'independent_groups':len({r['group_id'] for r in rows}),'mae':statistics.fmean(r['absolute_error'] for r in rows),'bias':statistics.fmean(r['error'] for r in rows),'point_in_time_all_pass':all(r['prediction_day']<r['outcome_day'] for r in rows),'scope':'One common acquire-none/order-up-to observed history per root/family; daily aggregate target. Diagnostic computations never enter a policy decision.'} for method,rows in forecast_rows.items()]
    learned=next(r for r in comparison if r['acquisition_policy']=='learned')
    pending_baseline=model['training_pending_mean']['downstream_intent']
    prospective_report={'category':'downstream_intent','cases':len(prospective),'all_predictions_before_observation':all(r['predicted_at']<r['acquired_at'] for r in prospective),'mean_squared_error':statistics.fmean((r['predicted_gross_value']-r['observed_gross_value'])**2 for r in prospective),'constant_train_baseline':pending_baseline,'constant_train_baseline_mse':statistics.fmean((pending_baseline-r['observed_gross_value'])**2 for r in prospective) if pending_baseline is not None else None,'bias':groups([(r['group_id'],r['predicted_gross_value']-r['observed_gross_value']) for r in prospective]),'calibration':'UNVERIFIED','scope':'Pre-reveal estimate at t; coupled same-prefix branches reveal at t+1 and settle at fixed t+5. Evaluation-only after all actual policy arms; no final-label feedback.'}
    return {'schema_version':'dragonhydra.logistics-study/1','synthetic':True,'status':'MEASURED_RESEARCH_ONLY','seed':seed,'evaluation_days':days,'evaluation_cases_per_family':cases,'final_test_root_groups':cases,'small_sample':cases<30,'familiar_rule_families':list(TRAIN_FAMILIES),'unseen_rule_families':list(UNSEEN_FAMILIES),'final_access_after_model_freeze':True,'model_id':model['model_id'],'model_content_sha256':frozen,'group_splits_disjoint':True,'policy_comparison':comparison,'forecast_comparison':forecasts,'forecast_diagnostic_calls':diagnostic_calls,'evaluation_records_sha256':digest(records),'evaluation_records':records,'future_value_prediction':prospective_report,'cost_unit':'VIRTUAL_CREDIT','per_episode_acquisition_budget':10.,'per_arm_experiment_budget':cases*5*10.,'per_arm_budget_definition':'Sum of bounded episode allocations, no arm can spend more than this explicit experiment cap. All arms have identical episode allocations.','net_decision_success':'NOT_ESTABLISHED; inspect cost AND service paired intervals separately','learned_cost_difference':learned['paired_cost_vs_baseline'],'learned_fill_difference':learned['paired_fill_rate_vs_baseline'],'prior_genesis61_result':'No established net predictive advantage over acquire-none. This is a new independent inventory experiment.','limitations':['Only fictional rules, costs and observations; no commercial or real-world accuracy claim.','All family variants of a seed are one dependent root group, not five independent samples.','Normal intervals are approximate and unadjusted for multiple comparisons.','Acquisition changes observation visibility; exogenous demand is identical across arms.','Completed lead histories and censored sales depend on prior decisions; that endogeneity is retained.','Single-SKU bounded network/replenishment heuristics; no multi-echelon or vehicle-routing optimality.','Configured virtual compute prices cover registered mathematical operations; wall/CPU overhead is measured separately.','Poisson predictive distributions can be misspecified for intermittent, seasonal and censored demand.']}
def train_and_evaluate(seed=42,cases=10,evaluation_cases=None,evaluation_days=20):
    started=time.perf_counter();trained=train_model(seed,cases)
    model=validate(trained['model']);frozen=model['content_sha256']
    report=evaluate(model,seed,evaluation_cases if evaluation_cases is not None else cases,evaluation_days)
    if validate(model)['content_sha256']!=frozen:raise ValueError('LOGISTICS_MODEL_CHANGED_AFTER_FREEZE')
    report['training_summary']=trained['training_summary'];report['elapsed_seconds']=time.perf_counter()-started
    return {'model':model,'report':report,'synthetic':True}
