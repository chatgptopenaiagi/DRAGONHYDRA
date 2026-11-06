"""Offline future-relevance acceptance. All state, observations and outcomes are fictional."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import tempfile
import time
from unittest.mock import patch

from dragonhydra.future_relevance.service import FutureService, execute_policy
from dragonhydra.future_relevance.environment import VirtualEpisode
from dragonhydra.future_relevance.experiments import train_and_evaluate
from dragonhydra.future_relevance.learning import validate_model


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--study-seed',type=int,default=7331)
    parser.add_argument('--study-cases',type=int,default=200)
    args=parser.parse_args(argv)
    output=args.output.absolute()
    if output.exists():raise ValueError('NEW_ACCEPTANCE_OUTPUT_REQUIRED')
    output.mkdir(parents=True)
    report={'schema_version':'dragonhydra.genesis61-acceptance/1','synthetic':True,'status':'RUNNING','checks':[],
            'predeclared_study':{'seed':args.study_seed,'cases_per_family':args.study_cases,'cost_weight':1.,
                'selection':'TRAIN_AND_VALIDATION_ONLY','final_test_used_for_tuning':False}}
    def check(name,condition):
        report['checks'].append({'name':name,'status':'PASS' if condition else 'FAIL'})
        if not condition:raise AssertionError(name)
    def write(name,value):
        with (output/name).open('x',encoding='utf-8') as f:json.dump(value,f,indent=2,sort_keys=True,allow_nan=False)
    started=time.perf_counter()
    try:
        with patch('socket.socket',side_effect=AssertionError('OFFLINE_ACCEPTANCE_FORBIDS_NETWORK')):
            with tempfile.TemporaryDirectory(prefix='genesis61-accept-') as directory:
                service=FutureService(Path(directory))
                episode_id=service.create_episode(universe='noisy_signal',seed=400042)['episode_id']
                episode=service.episode(episode_id)
                check('PUBLIC_BOUNDARY',not any(k in episode['snapshot'] for k in ('seed','family','outcome','hidden_tempo')))
                check('FUTURE_INFORMATION_PENDING',not episode['snapshot']['acquired'] and next(c for c in episode['snapshot']['candidates'] if c['category']=='fatigue')['availability']=='PENDING')
                trained=service.train(seed=42,cases_per_family=10)
                model=validate_model(trained['model']);model_hash=digest(model)
                first=service.decide(episode_id,'learned','virtual-accept-defer',episode['snapshot']['revision'])
                check('LEARNED_DECISION_BEFORE_REVEAL',first['actions'][-1]['action']=='DEFER' and not first['acquisitions'])
                first_hash=digest(first)
                check('DUPLICATE_IDEMPOTENT',digest(service.decide(episode_id,'learned','virtual-accept-defer',episode['snapshot']['revision']))==first_hash)
                before_restart=digest(service.episode(episode_id))
                service.close();service=FutureService(Path(directory))
                check('RESTART_RETAINS_PUBLIC_AND_IMMUTABLE_STATE',digest(service.episode(episode_id))==before_restart)
                current=service.episode(episode_id)
                advanced=service.advance(episode_id,2,current['snapshot']['revision'])
                resumed=advanced['decisions'][-1]
                check('DEFERRED_POLICY_AUTONOMOUSLY_RESUMES',resumed.get('resumes_decision_id')==first['decision_id'] and any(a['category']=='fatigue' for a in resumed['acquisitions']))
                check('FROZEN_MODEL_AND_SAME_CUTOFF',resumed['model_id']==model['model_id'] and resumed['before']['cutoff']==resumed['after']['cutoff'] and first['decision_at']<resumed['decision_at'])
                check('EXPLICIT_COST_ACCOUNTING',resumed['acquisition_cost']>0 and resumed['kernel_calls']==1+len(resumed['acquisitions']) and abs(resumed['computation_cost']-.001*resumed['kernel_calls'])<1e-12)
                replay=VirtualEpisode('noisy_signal',400042)
                replay_first=execute_policy(replay,'learned',model)
                replay.advance(2)
                replay_resumed=execute_policy(replay,'learned',model)
                check('DETERMINISTIC_POLICY_AND_NUMERICAL_REPLAY',replay_first['actions']==first['actions'] and replay_resumed['actions']==resumed['actions'] and replay_resumed['after']['probabilities']==resumed['after']['probabilities'])
                check('OUTCOME_NOT_REVEALED_EARLY',not advanced['evaluations'])
                evaluated=service.advance(episode_id,9,advanced['snapshot']['revision'])
                check('LATER_MEASURED_FUTURE_RELEVANCE',len(evaluated['evaluations'])==2 and any(e['deferred_future_relevance'] for e in evaluated['evaluations']))
                check('HISTORICAL_DECISION_UNCHANGED',digest(evaluated['decisions'][0])==first_hash)
                check('MODEL_NOT_UPDATED_BY_OUTCOMES',digest(service.model(model['model_id']))==model_hash)
                spent=service.status()['acquisition_budget_spent']
                for _ in range(4):service.episode(episode_id);service.status()
                check('PASSIVE_READS_DO_NOT_ACQUIRE',service.status()['acquisition_budget_spent']==spent)
                nothing=service.episode(service.create_episode(universe='constant',seed=400099,budget=0)['episode_id'])
                no=service.decide(nothing['episode_id'],'acquire_none','virtual-accept-nothing',nothing['snapshot']['revision'])
                check('NO_ACQUISITION_VALID',not no['acquisitions'] and no['acquisition_cost']==0)
                check('ORIGINAL_SIMULATION_RECORDS_ABSENT',service.status()['real_sporting_records']==service.status()['real_api_calls']==0)
                write('JOURNEY.json',{'initial':episode,'decision':first,'resumed':resumed,'final':evaluated,'model_id':model['model_id']})
                service.close()
            # The final independent experiment is run once from a recorded seed.
            # No result from this call is used to tune or retrain its frozen model.
            study=train_and_evaluate(seed=args.study_seed,cases=args.study_cases,cost_weight=1.)
            check('ALL_FIVE_COMPARISON_POLICIES',len(study['report']['policy_comparison'])==5)
            check('FROZEN_TRAINED_MODEL_VALID',validate_model(study['model']) is not None)
            write('STUDY.json',study)
            report['study_sha256']=digest(study)
            report['model_id']=study['model']['model_id']
        report['status']='PASS'
    except BaseException as error:
        report.update(status='FAILED',failure=f'{type(error).__name__}: {error}')
        raise
    finally:
        report['elapsed_seconds']=time.perf_counter()-started
        write('ACCEPTANCE.json',report)
    print(json.dumps({'status':report['status'],'checks':len(report['checks']),'model_id':report['model_id'],'output':str(output)}))


if __name__=='__main__':main()
