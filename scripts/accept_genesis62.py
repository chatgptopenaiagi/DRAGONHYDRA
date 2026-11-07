"""Actual offline domain loop, immutable evidence and predeclared virtual study."""
from __future__ import annotations
from pathlib import Path
from copy import deepcopy
import argparse,gzip,json,socket,tempfile,time
from unittest.mock import patch
from dragonhydra.cognitive_logistics.contracts import *
from dragonhydra.cognitive_logistics.world import World
from dragonhydra.cognitive_logistics.service import LogisticsService
from dragonhydra.cognitive_logistics.server import source_identity
from dragonhydra.cognitive_logistics.experiments import train_model,evaluate
from dragonhydra.cognitive_logistics.relevance import validate,estimate

ROOT=Path(__file__).absolute().parents[1]
MATH_FILES=('contracts','state','network','costs','forecast','policies','computation','world','relevance','experiments')
def pins():
    import hashlib
    paths=[ROOT/'src/dragonhydra/cognitive_logistics'/f'{name}.py' for name in MATH_FILES]+[ROOT/'src/dragonhydra/future_relevance/learning.py']
    return {p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
def write(path,value):
    with path.open('x',encoding='utf-8') as f:json.dump(value,f,indent=2,sort_keys=True,allow_nan=False);f.write('\n')
def seed_actual_model(service,model):
    """Provision actual fitted parameters in this disposable fixture; no fake fit."""
    validate(model)
    with service.journal.connect() as db:
        service.journal.insert(db,'models',model['model_id'],model)
        service.journal.put_meta(db,'active_model',model['model_id']);db.commit()

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--seed',type=int,default=8821)
    parser.add_argument('--cases',type=int,default=40)
    parser.add_argument('--evaluation-cases',type=int)
    parser.add_argument('--days',type=int,default=20)
    parser.add_argument('--model',type=Path)
    args=parser.parse_args(argv);out=args.output.absolute()
    if out.exists() or '..' in out.parts:raise ValueError('GENESIS62_NEW_ORDINARY_OUTPUT_REQUIRED')
    if not any(p.name=='GENESIS-6.2-COGNITIVE-LOGISTICS' and out.is_relative_to(p/'evidence') for p in out.parents):raise ValueError('GENESIS62_OUTPUT_OUTSIDE_EVIDENCE')
    for p in (out,*out.parents):
        if p.exists() and (p.is_symlink() or getattr(p.lstat(),'st_file_attributes',0)&0x400):raise ValueError('GENESIS62_REPARSE_OUTPUT')
    build=source_identity()
    if build.get('source_dirty'):raise ValueError('GENESIS62_FROZEN_SOURCE_REQUIRED_FOR_ACCEPTANCE')
    out.mkdir(parents=True);before=pins();checks=[];started=time.perf_counter()
    report={'schema_version':'dragonhydra.genesis62-acceptance/1','status':'RUNNING','synthetic':True,'build':build,'checks':checks,'math_inputs_sha256':before,'predeclared':{'seed':args.seed,'training_cases':args.cases,'evaluation_cases':args.evaluation_cases or args.cases,'days':args.days,'no_final_test_tuning':True}}
    def check(name,condition):
        checks.append({'name':name,'status':'PASS' if condition else 'FAIL'})
        if not condition:raise AssertionError(name)
    try:
        with patch.object(socket,'socket',side_effect=AssertionError('OFFLINE_ACCEPTANCE_FORBIDS_NETWORK')):
            if args.model:
                artifact=json.loads(args.model.read_text(encoding='utf-8'))
                check('FROZEN_MODEL_IMPLEMENTATION_BOUND',artifact['math_inputs_sha256']==before and artifact['configuration']=={'seed':args.seed,'cases':args.cases})
                model=validate(artifact['model']);summary=artifact['training_summary']
                report['model_training']='NOT_REPEATED; ACTUAL_FROZEN_MODEL_IMPORTED_FROM_SOURCE_ACCEPTANCE'
            else:
                trained=train_model(args.seed,args.cases);model=validate(trained['model']);summary=trained['training_summary']
                artifact={'schema_version':'dragonhydra.logistics-frozen-model-artifact/1','model':model,'training_summary':summary,'configuration':{'seed':args.seed,'cases':args.cases},'build':build,'math_inputs_sha256':before}
                write(out/'MODEL.json',artifact)
                # Actual virtual examples, not production inputs or placeholder logs.
                with gzip.open(out/'TRAINING-EXAMPLES.json.gz','wt',encoding='utf-8') as f:json.dump({'train':trained['training_rows'],'validation':trained['validation_rows']},f,allow_nan=False)
                report['model_training']='ACTUAL_TRAIN_PLUS_VALIDATION_ONLY_FIT_THIS_RUN'
            model_hash=digest(model)
            check('TRAIN_VAL_ROOT_ISOLATION',not set(model['training_group_ids'])&set(model['selection']['validation_group_ids']))
            check('PROSPECTIVE_TRAINING_AND_PROVENANCE',summary['pending_train_rows']>0 and summary['feature_provenance_verified'])
            with tempfile.TemporaryDirectory(prefix='genesis62-acceptance-') as directory:
                service=LogisticsService(Path(directory));seed_actual_model(service,model)
                eid=service.create_episode(seed=400042,days=20)['episode_id'];initial=service.episode(eid)
                snapshot=initial['snapshot']
                check('SUPPLIER_WAREHOUSE_TWO_RETAILS',{'supplier','warehouse','retail_a','retail_b'}<=set(snapshot['inventory']['by_location']))
                check('PUBLIC_BOUNDARY_NO_FUTURE_STATE',not {'seed','universe','private_arrivals','outcomes','actual_future_demand'}&snapshot.keys())
                check('PHYSICAL_CONSERVATION_INITIAL',snapshot['inventory']['global']['physical_total']==snapshot['inventory']['global']['physical_expected'])
                check('EXACT_IP_ATP_AND_TRANSIT',all(row['inventory_position']==row['on_hand']+row['on_order']-row['backorder'] and row['atp']==row['on_hand']-row['reserved'] and row['in_transit']<=row['on_order'] for loc in snapshot['inventory']['by_location'].values() for row in loc.values()))
                predicted=estimate(snapshot,'downstream_intent',model)
                check('PREDICT_RELEVANCE_BEFORE_AVAILABILITY',snapshot['day']<next(c['available_day'] for c in snapshot['candidates'] if c['category']=='downstream_intent') and predicted['estimated_value'] is not None)
                decision=service.decide(eid,acquisition='all',request_id='virtual-end-to-end-inventory',expected_revision=snapshot['revision'])
                check('ACTUAL_SHIPMENTS_AND_UNREVEALED_ARRIVAL',bool(decision['shipments']) and all(s['actual_arrival']=='UNREVEALED' for s in decision['shipments']))
                check('DEFER_AND_ACQUIRE_ACTUAL_ACTIONS',any(a['action']=='DEFER' for a in decision['actions']) and bool(decision['acquisitions']))
                first_hash=digest(decision)
                check('DUPLICATE_REQUEST_NO_REPEAT_ACTION',digest(service.decide(eid,acquisition='all',request_id='virtual-end-to-end-inventory',expected_revision=snapshot['revision']))==first_hash)
                advanced=service.advance(eid,1,decision['state_revision_after'])
                check('DEFERRED_OBSERVATION_NOW_ELIGIBLE','downstream_intent' in advanced['snapshot']['acquired'])
                check('SINGLE_OWNER_TRANSIT',all(row['in_transit']<=row['on_order'] for loc in advanced['snapshot']['inventory']['by_location'].values() for row in loc.values()))
                retained_hash=digest(advanced);spent=service.status()['acquisition_spent'];service.close();service=LogisticsService(Path(directory))
                check('RESTART_EXACT_RETAINED_STATE',digest(service.episode(eid))==retained_hash and service.status()['acquisition_spent']==spent)
                final=service.advance(eid,9,advanced['snapshot']['revision'])
                check('ELIGIBLE_COST_AND_SERVICE_METRICS',final['metrics']['eligible_days']==10 and final['metrics']['fill_rate'] is not None)
                check('ALL_SEVEN_ACTUAL_COST_COMPONENTS',set(final['metrics']['costs'])==set(COST_KEYS) and abs(sum(final['metrics']['costs'].values())-final['metrics']['total_cost'])<1e-8)
                check('HISTORICAL_DECISION_UNCHANGED',digest(next(d for d in final['decisions'] if d['decision_id']==decision['decision_id']))==first_hash)
                check('HISTORICAL_MODEL_UNCHANGED',digest(service.models()['items'][0])==model_hash)
                current=digest(final);global_spent=service.status()['acquisition_spent']
                for _ in range(3):service.episode(eid);service.status();service.models();service.experiments()
                check('READ_ONLY_REFRESH',digest(service.episode(eid))==current and service.status()['acquisition_spent']==global_spent)
                analysis=service.analyze(eid,'counterfactual')
                check('BOUNDED_ANALYTICAL_INTERVENTIONS',analysis['original_unchanged'] and len(analysis['counterfactuals'])==5)
                zero=service.create_episode(seed=400043,days=10,budget=0)['episode_id'];z=service.episode(zero)
                nothing=service.decide(zero,acquisition='learned',request_id='virtual-no-information-valid',expected_revision=z['snapshot']['revision'])
                check('NO_ACQUISITION_VALID_WITH_ZERO_BUDGET',not nothing['acquisitions'] and any(a['action']=='DO_NOTHING' for a in nothing['actions']))
                bo=service.create_episode(seed=400044,days=10,demand_mode='backorder')['episode_id'];b=service.episode(bo);b=service.advance(bo,5,b['snapshot']['revision'])
                check('BACKORDER_MODE_OPERATES',b['snapshot']['demand_mode']=='backorder' and b['snapshot']['inventory']['global']['valid'])
                write(out/'JOURNEY.json',{'initial':initial,'initial_estimate_before_reveal':predicted,'decision':decision,'final':final,'analysis':analysis,'zero_budget_decision':nothing,'backorder_result':b})
                service.close()
            # Deterministic replay, with no changes to historical stored forecasts.
            first=World('stable',400073,days=10);second=World('stable',400073,days=10)
            first.run(10);second.run(5);second=World.from_dict(second.to_dict());second.run(5)
            check('RESTART_REPLAY_NUMERICAL_EQUIVALENCE',first.inventory.to_dict()==second.inventory.to_dict() and first.outcomes==second.outcomes and first.costs.summary()==second.costs.summary())
            study=evaluate(model,args.seed,args.evaluation_cases or args.cases,args.days)
            check('ALL_NINE_STRONG_ARMS',len(study['policy_comparison'])==9 and any(r['acquisition_policy']=='none' for r in study['policy_comparison']))
            check('FAMILIAR_AND_UNSEEN_RULE_FAMILIES',len(study['unseen_rule_families'])==3 and not set(study['unseen_rule_families'])&set(summary['train_families']+summary['validation_families']))
            check('ALL_EVALUATED_PHYSICAL_AND_BUDGET_INVARIANTS',all(r['physical_conservation_all_pass'] and r['budget_violations']==0 for r in study['policy_comparison']))
            check('PENDING_RELEVANCE_MEASURED_BEFORE_REVEAL',study['future_value_prediction']['all_predictions_before_observation'])
            check('FROZEN_MODEL_AFTER_HELD_OUT',digest(model)==model_hash)
            write(out/'STUDY.json',{'model':model,'training_summary':summary,'report':study})
            report.update(model_id=model['model_id'],study_sha256=digest(study),study_first_root_sha256=digest(study['evaluation_records'][:45]),study_independent_groups=study['final_test_root_groups'])
            if pins()!=before:raise ValueError('GENESIS62_MATHEMATICAL_SOURCE_CHANGED_DURING_ACCEPTANCE')
        report['status']='PASS'
    except BaseException as error:
        report.update(status='FAILED',failure=f'{type(error).__name__}: {error}');raise
    finally:
        report['elapsed_seconds']=time.perf_counter()-started;write(out/'ACCEPTANCE.json',report)
    print(canonical({'status':report['status'],'checks':len(checks),'model_id':report['model_id'],'output':str(out),'elapsed_seconds':report['elapsed_seconds']}))
if __name__=='__main__':main()
