"""Command orchestration for local cognitive forecasting and feedback."""
from datetime import datetime, timezone
from decimal import Decimal, localcontext
from uuid import uuid4

from .. import football_data, market_signals, market_store, scenario
from . import evaluation, memory, models, runtime

VERSION = 'cognitive-commands/1'


def _archive_prices(rows):
    grouped={}
    for row in rows:
        key=(row['source_hash'],row['event_id'],row['provider_id'],row['outcome'])
        phase=row.get('quote_phase')
        if phase in ('source_recorded','source_close'):
            bucket=grouped.setdefault(key,{})
            if phase in bucket:
                raise ValueError('AMBIGUOUS_ARCHIVAL_PRICE')
            bucket[phase]=row
    results=[]
    with localcontext() as ctx:
        ctx.prec=34
        for (source_hash,event_id,provider,outcome), phases in sorted(grouped.items()):
            old=phases.get('source_recorded'); new=phases.get('source_close')
            if not old or not new:
                continue
            a=market_signals.convert_odds(old['odds_original'],old['odds_format'])
            b=market_signals.convert_odds(new['odds_original'],new['odds_format'])
            results.append({'source_hash':source_hash,'event_id':event_id,'provider_label':provider,'outcome':outcome,
                'source_recorded_odds':str(a),'source_closing_odds':str(b),'difference':str(b-a),
                'recorded_raw_implied_probability':str(Decimal(1)/a),
                'closing_raw_implied_probability':str(Decimal(1)/b),
                'evidence_ids':[old['evidence_id'],new['evidence_id']],
                'transformation':{'version':VERSION,'formula':'closing-labelled odds minus recorded odds; raw implied probability = 1 / decimal odds'},
                'limitations':['Quote times, synchronization and provider mappings are unverified.']})
    return results


def run(command, db_path, *, event_date=None, cutoff=None, outcome_evidence_id=None):
    if command in ('train','predict'):
        return (runtime.train_current(db_path,event_date=event_date) if command=='train'
                else runtime.predict_current(db_path,event_date=event_date))
    if command=='memory':
        if outcome_evidence_id and cutoff is not None:
            raise ValueError('OUTCOME_ATTACHMENT_REQUIRES_CURRENT_VIEW')
        attached = memory.record_outcome(db_path,outcome_evidence_id) if outcome_evidence_id else None
        decision=cutoff or runtime.now()
        view=memory.as_of(db_path,decision)
        return {'cutoff':decision,'attached_outcome':attached,'records':view,
                'counts':{name:len(rows) for name,rows in view.items()},
                'availability_mode':'OPERATIONAL_AS_OF_RECEIPT',
                'limitations':['Receipt transaction visibility at the exact commit boundary is unverified.']}
    if command in ('evaluate','calibrate'):
        if cutoff is None:
            runtime.prepare(db_path)
        feedback=runtime.attach_later_outcomes(db_path) if command=='evaluate' and cutoff is None else None
        at=cutoff or runtime.now()
        holdout=runtime.holdout(db_path,cutoff=at)
        operational=evaluation.evaluate_observed(memory.as_of(db_path,at),at)
        persisted=[]
        if command=='evaluate':
            run_id=uuid4().hex
            for group in operational['groups']:
                if group['model_name'] not in models.NAMES or not group['metrics']['brier']['sample_size']:
                    continue
                draft={'run_id':run_id,'model_name':group['model_name'],'model_version':group['model_version'],
                       'metric':'brier','evaluation_cutoff':at,**group['evaluation_scope']}
                persisted.append(memory.record_evaluation(db_path,draft))
        return {'actual_run_time':runtime.now(),'evaluation_cutoff':at,'present_knowledge_holdout':holdout,'operational':operational,
                'persisted_evaluations':persisted,'outcome_feedback':feedback}
    if command=='research':
        trained=runtime.train_current(db_path,event_date=event_date)
        return runtime.current_research(db_path,trained['forecast'],
                        model_run_id=trained['model_runs'][-1]['record_id'] if trained['model_runs'] else None)
    if command=='intelligence':
        prediction=runtime.predict_current(db_path,event_date=event_date)
        archive_path=runtime.ROOT/'data'/'raw'/'football-data-2025-26-E0.csv'
        if archive_path.exists():
            first=football_data.list_events(archive_path,limit=1)['events'][0]
            football_data.import_event(db_path,archive_path,first['source_event_id'])
        feedback=runtime.attach_later_outcomes(db_path)
        at=runtime.now()
        view=memory.as_of(db_path,at)
        operational=evaluation.evaluate_observed(view,at)
        holdout=runtime.holdout(db_path)
        task_report=runtime.current_research(db_path,prediction['forecast'],
                       model_run_id=prediction['model_runs'][-1]['record_id'] if prediction['model_runs'] else None)
        memory_cutoff=runtime.now()
        final_view=memory.as_of(db_path,memory_cutoff)
        market=[r for r in market_store.get_as_of(db_path,at) if r.get('source_id')==football_data.SOURCE_ID]
        raw_market_sources={}
        for row in market:
            digest=row['source_hash']
            if digest not in raw_market_sources:
                raw_market_sources[digest]=market_store.raw_source(db_path,digest)
            scenario.verify_archived_quote(row,at,raw_source=raw_market_sources[digest])
        market_signals_report=market_signals.compute_signals(market,at)
        return {'report_version':VERSION,'run_id':prediction['run_id'],
                'report_mode':'CURRENT_COMPOSITE_WITH_SEPARATE_CUTOFFS',
                'data_origin':['imported_historical','model_state'], 'actual_run_time':runtime.now(),
                'data_coverage':{'eligible_training_results':prediction['forecast']['training_count'],
                    'training_evidence_ids':[r['evidence_id'] for r in prediction['forecast']['training_manifest']],
                    'eligible_market_observations':len(market),
                    'market_evidence_ids':[r['evidence_id'] for r in market],
                    'sources':sorted({r['source_id'] for r in prediction['forecast']['training_manifest']}),
                    'training_cutoff':prediction['forecast']['data_cutoff'],'market_cutoff':at,
                    'transformation':{'version':VERSION,'formula':'count retained records eligible at the stated cutoff'}},
                'prediction':prediction,'operational_evaluation':operational,'outcome_feedback':feedback,
                'market_analysis':{'scope':'archived observations; not mapped to forecast fixture',
                    'evidence_manifest':market,'signals':market_signals_report,'source_label_differences':_archive_prices(market),
                    'model_vs_market':{'value':None,'reason':'VERIFIED_FIXTURE_AND_SETTLEMENT_MAPPING_UNAVAILABLE'},
                    'conditional_expected_return':{'value':None,'reason':'VERIFIED_FIXTURE_AND_SETTLEMENT_MAPPING_UNAVAILABLE'}},
                'present_knowledge_holdout':holdout,'research':task_report,
                'memory_counts':{key:len(value) for key,value in final_view.items()},
                'memory_evidence_ids':{key:[row['record_id'] for row in value] for key,value in final_view.items()},
                'memory_cutoff':memory_cutoff,
                'storage':{'backend':'SQLite','receipt_visibility':'exact receipt transaction visibility unverified'},
                'limitations':['Present-knowledge holdout is not a historical point-in-time backtest.',
                    'No model-versus-market comparison is made without verified fixture and settlement mapping.']}
    raise ValueError('UNKNOWN_COGNITIVE_COMMAND')


def render(command, result):
    if command in ('train','predict','intelligence'):
        wrapper=result['prediction'] if command=='intelligence' else result
        forecast=wrapper['forecast']; target=forecast['target']
        print('DRAGONHYDRA MULTIMODEL COGNITIVE FORECAST')
        print(target['event_date'],target['home'],'vs',target['away'],'| source:',target['source_id'])
        print('Data cutoff:',forecast['data_cutoff'],'| forecast computed:',forecast['decision_cutoff'],
              '| training results:',forecast['training_count'])
        if forecast['training_manifest']:
            days=[row['event_date'] for row in forecast['training_manifest']]
            print('Training period:',min(days),'to',max(days))
        for name,model in forecast['models'].items():
            if model.get('available'):
                p=model['probabilities']
                print(name,': home',round(p['home']['value'],4),'draw',round(p['draw']['value'],4),'away',round(p['away']['value'],4))
            else:
                print(name,': unavailable —',model.get('reason'))
        if forecast.get('ensemble'):
            e=forecast['ensemble']; p=e['probabilities']
            print('ensemble : home',round(p['home']['value'],4),'draw',round(p['draw']['value'],4),'away',round(p['away']['value'],4))
            print('weights:',e['weight_mode'],e['weights'])
            if forecast.get('adaptation'):
                print('Adaptive evidence:',forecast['adaptation']['reason'] or 'eligible comparable operational scores')
        goal=forecast['models'].get('poisson_goals',{})
        if goal.get('available'):
            print('Poisson expected goals:',round(goal['goal_rate_home']['value'],4),'-',round(goal['goal_rate_away']['value'],4))
            print('Over 2.5:',round(goal['totals_2_5']['over']['value'],4),'| both teams score:',round(goal['both_teams_to_score']['yes']['value'],4))
            print('Most likely scorelines:',', '.join(f"{s['home_goals']}-{s['away_goals']} ({s['probability']['value']:.4f})" for s in goal['scorelines']))
        print('Persisted model runs:',len(wrapper.get('model_runs',[])),'| predictions:',len(wrapper.get('predictions',[])))
        if wrapper.get('predictions'):
            print('Prediction record:',wrapper['predictions'][-1]['record_id'])
        if command=='intelligence':
            _render_holdout(result['present_knowledge_holdout'])
            for item in result['present_knowledge_holdout']['calibration_bins']:
                if item['sample_size']:
                    print('Calibration',item['outcome'],'| n',item['sample_size'],
                          '| mean forecast',round(item['mean_forecast'],4),
                          '| observed',round(item['observed_frequency'],4))
            print('Operational scored predictions:',sum(g['metrics']['brier']['sample_size'] for g in result['operational_evaluation']['groups']))
            print('Matching market quotes:',len(result['research']['matched_quote_evidence_ids']))
            market=result['market_analysis']
            print('Archived market claims:',len(market['evidence_manifest']),'| model/market comparison:',market['model_vs_market']['reason'])
            for item in market['source_label_differences']:
                if item['outcome']=='home':
                    print('Archived',item['provider_label'],'home:',item['source_recorded_odds'],'→',item['source_closing_odds'],
                          '| raw implied:',item['recorded_raw_implied_probability'],'→',item['closing_raw_implied_probability'])
            print('Model disagreement:',{k:round(v['value'],4) if v['value'] is not None else None for k,v in result['research']['model_disagreement'].items()})
            freshness=result['research']['latest_result_age']
            print('Days since latest eligible match:',freshness.get('value'),'| date:',freshness.get('latest_event_date'))
            print('Memory:',result['memory_counts'])
            print('Research gaps:',', '.join(t['gap'] for t in result['research']['research_tasks']))
            print('Competing hypotheses:',len(result['research'].get('hypotheses',[])))
        print('Model estimates are uncalibrated; the source supplies no verified UTC kickoff time.')
        return
    if command in ('evaluate','calibrate'):
        _render_holdout(result['present_knowledge_holdout'])
        operational=result['operational']
        print('Operational predictions:',operational['eligible_prediction_count'],'| scored:',sum(g['metrics']['brier']['sample_size'] for g in operational['groups']))
        if command=='calibrate':
            for item in result['present_knowledge_holdout']['calibration_bins']:
                if item['sample_size']:
                    print(item['outcome'],'bin',item['lower_inclusive'],'to',item['upper'],
                          '| n',item['sample_size'],'| predicted',round(item['mean_forecast'],4),
                          '| observed',round(item['observed_frequency'],4),'|',item['quality'])
        return
    if command=='memory':
        print('COGNITIVE MEMORY —',result['availability_mode'])
        print('Cutoff:',result['cutoff'],'| counts:',result['counts'])
        for kind,rows in result['records'].items():
            if rows:
                last=rows[-1]
                print(kind,'latest:',last['record_id'],'| usable:',last['usable_at'])
        return
    if command=='research':
        print('COGNITIVE RESEARCH TASKS — assessment cutoff',result['assessment_cutoff'])
        for task in result['research_tasks']:
            print(task['gap'],':',task['question'])
        for hypothesis in result.get('hypotheses',[]):
            print('Hypothesis revision',hypothesis['revision'],':',hypothesis['claim'])
        print('Persisted task receipts:',len(result['persisted_tasks']))


def _render_holdout(result):
    b=result['metrics']['brier']; l=result['metrics']['log_loss']
    print('PRESENT-KNOWLEDGE CHRONOLOGICAL HOLDOUT (not historical replay)')
    print('Evaluated model:',result['model_version'],'| source:',result.get('source_id'),
          '| competition:',result.get('competition'),'| dataset:',result.get('dataset_count'))
    print('Scored:',b['sample_size'],'| coverage:',result['coverage']['fraction'])
    print('Brier mean:',b['value'],'| sample variance:',b['sample_variance'])
    print('Log loss mean:',l['value'],'| sample variance:',l['sample_variance'])
    if 'accuracy' in result['metrics']:
        accuracy=result['metrics']['accuracy']
        print('Classification accuracy:',accuracy['value'],'| sample variance:',accuracy['sample_variance'],'| n:',accuracy['sample_size'])
    trend=result.get('performance_change',{})
    if 'mean_brier_change' in trend:
        print('Later-minus-earlier holdout Brier:',trend['mean_brier_change'],
              '| sample sizes:',trend['first']['sample_size'],trend['second']['sample_size'])
