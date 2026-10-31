"""Command line entry point for the local DRAGONHYDRA research laboratory."""
import argparse
import base64
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import sys
import uuid

from . import estimate_store, football_data, market_signals, market_store, public_results, research, watch

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB = ROOT / 'runtime' / 'dragonhydra.sqlite3'
SCOPE = research.SCOPE


def _resource(*parts):
    local = ROOT.joinpath(*parts)
    return local if local.is_file() else Path(__file__).parent.joinpath('resources', *parts)


def _cutoff(value):
    return market_store.utc(datetime.now(timezone.utc) if value == 'now' else value)


def _report(db, event, cutoff, estimate=None, *, replay_mode='STRICT_PIT', scenario=None):
    clock_mode = 'synthetic_simulated' if replay_mode == 'STRICT_PIT_SIMULATED' else 'operational'
    rows = [r for r in market_store.get_as_of(db, cutoff, clock_mode=clock_mode) if r['event_id'] == event]
    quarantine = market_store.get_quarantine(db, cutoff, clock_mode=clock_mode)
    signals = market_signals.compute_signals(rows, cutoff)
    flags = list(signals['quality_flags'])
    if clock_mode == 'operational':
        flags.append({'code':'RECEIPT_VISIBILITY_BOUNDARY_UNVERIFIED','evidence_ids':[]})
    evidence = {r['evidence_id']: r for r in rows}
    hypotheses = []
    for divergence in signals['provider_divergences']:
        metric = divergence['decimal_odds_difference']
        if metric.get('value') is not None and Decimal(metric['value']) > 0:
            ids = metric['evidence_ids']
            hypotheses.append({'claim':'Comparable providers quote different prices.',
                 'supporting_evidence_ids':ids, 'contradicting_evidence_ids':[],
                 'assumptions':['Recorded scope and timing are accurate.'],
                 'missing_information':['Provider pricing rationale and feed independence.'],
                 'next_question':'Does a subsequent aligned observation retain the difference?', 'revision':1})
            break
    if any(not set(h['supporting_evidence_ids'] + h['contradicting_evidence_ids']).issubset(evidence) for h in hypotheses):
        raise ValueError('unknown hypothesis evidence')
    tasks = []
    for item in quarantine:
        tasks.append({'gap':'QUARANTINED_INPUT','question':'Can the source record be corrected or its identity resolved?',
          'permitted_source':'user-supplied file or approved provider','priority_rationale':'Quarantined records are excluded from evidence.',
          'expected_evidence':'a validated source record','budget':'one bounded check',
          'stopping_condition':'corrected record accepted or source unavailable','source_hash':item['source_hash'],'evidence_ids':[]})
    for flag in flags:
        tasks.append({'gap':flag.get('code','DATA_QUALITY'), 'question':'Can this evidence gap be resolved with another validated observation?',
          'permitted_source':'user-supplied file or approved provider', 'priority_rationale':'The gap limits comparison.',
          'expected_evidence':'timestamped source record and identity', 'budget':'one bounded check',
          'stopping_condition':'valid evidence obtained or source unavailable', 'evidence_ids':flag.get('evidence_ids',[])})
    assessment = None
    if estimate is not None:
        eligible = []
        for metric in signals['quote_metrics']:
            price = metric.get('decimal_odds', {})
            if price.get('value') is None:
                continue
            for eid in price.get('evidence_ids', []):
                row = evidence.get(eid)
                if row and all(row.get(key) == estimate.get(key) for key in SCOPE):
                    eligible.append((Decimal(price['value']), eid, row))
        if eligible:
            chosen = max(eligible, key=lambda x:(x[0], x[1]))[2]
            assessment = research.assess(chosen, estimate, cutoff, **(scenario or {}))
            for code in assessment.get('quality_flags', []):
                flags.append({'code':code,'evidence_ids':[chosen['evidence_id']]})
                tasks.append({'gap':code,'question':'Can the original quote timestamp or a fresher price be obtained?',
                  'permitted_source':'user-supplied file or approved provider','priority_rationale':'Price timing affects the scenario.',
                  'expected_evidence':'timestamped provider quote','budget':'one bounded check',
                  'stopping_condition':'timing established or source unavailable','evidence_ids':[chosen['evidence_id']]})
        else:
            flags.append({'code':'MATCHING_QUOTE_UNAVAILABLE','evidence_ids':[]})
    else:
        tasks.append({'gap':'MODEL_PROBABILITY_UNAVAILABLE','question':'Can an independently supported probability estimate be supplied?',
          'permitted_source':'user-supplied evidence or validated model', 'priority_rationale':'Expected value requires a probability assumption.',
          'expected_evidence':'probability estimate with provenance', 'budget':'one bounded model review',
          'stopping_condition':'eligible estimate is available or source remains unavailable', 'evidence_ids':[]})
    raw_sources = {}
    for source_hash in sorted({r['source_hash'] for r in rows}):
        raw = market_store.raw_source(db,source_hash)
        if hashlib.sha256(raw).hexdigest() != source_hash:
            raise ValueError('SOURCE_HASH_MISMATCH')
        raw_sources[source_hash] = {'encoding':'base64', 'bytes':base64.b64encode(raw).decode('ascii')}
    return {'run_id':str(uuid.uuid4()), 'decision_cutoff':cutoff, 'actual_run_time':datetime.now(timezone.utc).isoformat(),
        'replay_mode':replay_mode, 'data_origin':sorted({r['data_origin'] for r in rows}),
        'evidence_manifest':rows, 'raw_source_manifest':raw_sources, 'quarantine_manifest':quarantine, 'signals':signals,
        'quality_flags':flags, 'hypotheses':hypotheses,
        'contradictions':[f for f in flags if f.get('code') in ('CONFLICTING_SOURCE_QUOTES','INCOMPATIBLE_MARKET_DEFINITIONS','STALE_QUOTE')],
        'uncertainty_summary':{'abstained':assessment is None, 'items':['Price-derived probabilities do not establish true event probabilities.'] +
            (['The exact visibility time of the second receipt transaction is not established.'] if clock_mode=='operational' else [])},
        'research_tasks':tasks, 'assessment':assessment,
        'stop_reason':'REPORT_COMPLETE' if rows else 'NO_ELIGIBLE_EVIDENCE',
        'versions':{'adapter':market_store.ADAPTER_VERSION, 'signals':market_signals.VERSION, 'research':research.VERSION,
                    'python':sys.version.split()[0]}}


def _text(report):
    print('DRAGONHYDRA AS-OF MARKET RESEARCH')
    print('Cutoff:', report['decision_cutoff'], '| origin:', ', '.join(report['data_origin']) or 'none', '| quotes:',len(report['evidence_manifest']))
    for item in report['signals']['quote_metrics']:
        price=item['decimal_odds']; prob=item['raw_implied_probability']; age=item['quote_age']
        print(f"{item['provider_id']} {item['outcome']}: decimal={price.get('value') or price.get('reason')} raw_probability={prob.get('value') or prob.get('reason')} age_seconds={age.get('value') or age.get('reason')}")
    for item in report['signals']['movements']:
        if item.get('available'):
            print(f"Movement {item['provider_id']} {item['outcome']}: {item['decimal_odds_change']['value']} odds, {item['odds_change_per_hour'].get('value') or item['odds_change_per_hour'].get('reason')} odds/hour")
    for item in report['signals']['provider_divergences']:
        metric=item['decimal_odds_difference']
        print(f"Divergence {item['outcome']}: {metric.get('value') or metric.get('reason')}")
    for item in report['signals']['overrounds']:
        metric=item['overround']
        print(f"Overround {item['provider_id']}: {metric.get('value') or metric.get('reason')}")
    if report['assessment']:
        a=report['assessment']
        print('Conditional expected return per unit:',a['expected_net_return_per_unit']['value'])
        print('Fractional capped Kelly:',a['fractional_capped_kelly']['value'])
        print('Simulation mean final bankroll:',a['simulation']['mean_final_bankroll']['value'])
    else:
        print('Probability assessment unavailable; see research tasks.')


def main(argv=None):
    p=argparse.ArgumentParser(prog='dragon',description='Point-in-time market research')
    from .build_meta import VERSION
    p.add_argument('--version', action='version', version=VERSION)
    sub=p.add_subparsers(dest='command',required=True)
    demo=sub.add_parser('demo',help='run the reproducible synthetic market example')
    demo.add_argument('--db',type=Path,default=ROOT/'runtime'/'market-demo.sqlite3')
    demo.add_argument('--format',choices=('text','json','both'),default='text')
    imp=sub.add_parser('import',help='import a local JSON/CSV snapshot')
    imp.add_argument('--file',type=Path,required=True); imp.add_argument('--db',type=Path,default=DEFAULT_DB)
    imp.add_argument('--synthetic-clock',action='store_true')
    report=sub.add_parser('report',help='report a market at a cutoff')
    report.add_argument('--db',type=Path,default=DEFAULT_DB); report.add_argument('--event',required=True)
    report.add_argument('--cutoff',default='now'); report.add_argument('--estimate',type=Path)
    report.add_argument('--synthetic-clock',action='store_true'); report.add_argument('--format',choices=('text','json','both'),default='text')
    report.add_argument('--fraction',default='0.25'); report.add_argument('--cap',default='0.02'); report.add_argument('--bankroll',default='1000')
    report.add_argument('--trials',type=int,default=1000); report.add_argument('--steps',type=int,default=20); report.add_argument('--seed',type=int,default=42)
    results=sub.add_parser('results',help='import and inspect public OpenFootball fixtures/results')
    results.add_argument('--db',type=Path,default=DEFAULT_DB)
    results.add_argument('--file',type=Path,default=_resource('data','raw','openfootball-2025-26-en1.json'))
    results.add_argument('--receipt',type=Path,default=_resource('data','raw','openfootball-2025-26-en1.json.receipt.json'))
    results.add_argument('--cutoff',default='now'); results.add_argument('--limit',type=int,default=5)
    results.add_argument('--format',choices=('text','json'),default='text')
    archive=sub.add_parser('archive',help='inspect real archived Football-Data price claims')
    archive.add_argument('--db',type=Path,default=DEFAULT_DB)
    archive.add_argument('--file',type=Path,default=_resource('data','raw','football-data-2025-26-E0.csv'))
    archive.add_argument('--event'); archive.add_argument('--cutoff',default='now')
    archive.add_argument('--probability',help='present-time hypothetical probability, between 0 and 1')
    archive.add_argument('--fraction',default='0.25'); archive.add_argument('--cap',default='0.02')
    archive.add_argument('--bankroll',default='1000'); archive.add_argument('--stake-fraction',default='0.02')
    archive.add_argument('--trials',type=int,default=1000); archive.add_argument('--steps',type=int,default=20)
    archive.add_argument('--seed',type=int,default=42)
    archive.add_argument('--format',choices=('text','json'),default='text')
    score=sub.add_parser('score',help='evaluate retained synthetic forecasts chronologically')
    score.add_argument('--file',type=Path,default=_resource('examples','synthetic-scores.json'))
    score.add_argument('--cutoff',default='2026-01-10T00:00:00Z')
    score.add_argument('--format',choices=('text','json'),default='text')
    forecast=sub.add_parser('forecast',help='current descriptive prior for an eligible future OpenFootball fixture')
    forecast.add_argument('--db',type=Path,default=DEFAULT_DB)
    forecast.add_argument('--file',type=Path,default=_resource('data','raw','openfootball-2026-27-en1.json'))
    forecast.add_argument('--receipt',type=Path,default=_resource('data','raw','openfootball-2026-27-en1.json.receipt.json'))
    forecast.add_argument('--event-date'); forecast.add_argument('--format',choices=('text','json'),default='text')
    watcher=sub.add_parser('watch',help='bounded polling of a local snapshot file')
    watcher.add_argument('--file',type=Path,required=True); watcher.add_argument('--db',type=Path,default=DEFAULT_DB)
    watcher.add_argument('--iterations',type=int,default=1); watcher.add_argument('--interval',type=float,default=1)
    watcher.add_argument('--format',choices=('text','json'),default='text')
    for name in ('train','predict','evaluate','calibrate','memory','intelligence','research'):
        cognitive=sub.add_parser(name,help='cognitive '+name+' using retained local evidence')
        cognitive.add_argument('--db',type=Path,default=DEFAULT_DB)
        cognitive.add_argument('--format',choices=('text','json'),default='text')
        if name in ('train','predict','intelligence','research'):
            cognitive.add_argument('--event-date')
        if name in ('evaluate','calibrate','memory'):
            cognitive.add_argument('--cutoff',default=None)
        if name=='memory':
            cognitive.add_argument('--outcome-evidence-id')
    args=p.parse_args(argv)
    if args.command=='score':
        records=json.loads(args.file.read_text(encoding='utf-8-sig'))['records']
        result=research.evaluate_chronological(records,_cutoff(args.cutoff))
        for case in result['cases']:
            pred, outcome = case['prediction'], case['outcome']
            if pred['data_origin']!='synthetic' or outcome['data_origin']!='synthetic':
                raise ValueError('score command requires explicitly synthetic replay evidence')
            pred_raw=json.loads(pred['source_raw']); outcome_raw=json.loads(outcome['source_raw'])
            if pred_raw.get('scope')!={k:pred[k] for k in SCOPE} or pred_raw.get('probabilities')!=pred['probabilities']:
                raise ValueError('PREDICTION_SOURCE_VALUE_MISMATCH')
            if outcome_raw.get('scope')!={k:outcome[k] for k in SCOPE} or outcome_raw.get('outcome')!=outcome['outcome']:
                raise ValueError('OUTCOME_SOURCE_VALUE_MISMATCH')
        result['replay_mode']='SYNTHETIC_HYPOTHETICAL_REPLAY'
        if args.format=='json':
            print(json.dumps(result,indent=2,ensure_ascii=False,sort_keys=True))
        else:
            print('SYNTHETIC CHRONOLOGICAL SCORING —',len(result['cases']),'eligible predictions')
            for key in ('brier','log_loss'):
                item=result['metrics'][key]
                print(key,': mean',item['value'],'| sample variance',item['sample_variance'],'| n',item['sample_size'])
        return 0
    if args.command=='watch':
        def on_poll(event):
            print('poll',event['poll_number'],event['status'],'| observed',event['observed_at'],flush=True)
        if args.format=='text':
            print('LOCAL SNAPSHOT WATCH —',args.iterations,'polls requested',flush=True)
        result=watch.watch_file(args.db,args.file,iterations=args.iterations,interval_seconds=args.interval,
                                on_poll=on_poll if args.format=='text' else None)
        if args.format=='json':
            print(json.dumps(result,indent=2,ensure_ascii=False,sort_keys=True))
        else:
            print('Stop:',result['stop_reason'])
        return 0
    if args.command in ('train','predict','evaluate','calibrate','memory','intelligence','research'):
        from .cognition import commands
        args.db.parent.mkdir(parents=True,exist_ok=True)
        cutoff=getattr(args,'cutoff',None)
        if cutoff is not None:
            cutoff=_cutoff(cutoff)
        result=commands.run(args.command,args.db,event_date=getattr(args,'event_date',None),cutoff=cutoff,
                            outcome_evidence_id=getattr(args,'outcome_evidence_id',None))
        if args.format=='json':
            print(json.dumps(result,indent=2,ensure_ascii=False,sort_keys=True))
        else:
            commands.render(args.command,result)
        return 0
    args.db.parent.mkdir(parents=True,exist_ok=True)
    if args.command=='import':
        print(json.dumps(market_store.import_file(args.db,args.file,simulated=args.synthetic_clock),indent=2))
        return 0
    if args.command=='results':
        if args.limit < 0 or args.limit > 100:
            raise ValueError('limit must be between 0 and 100')
        capture=json.loads(args.receipt.read_text(encoding='utf-8-sig'))
        url=capture['source_url']
        imported=public_results.import_file(args.db,args.file,source_id=capture['source_id'],source_url=url,
                                            acquisition_id=capture['sha256'],receipt_path=args.receipt)
        cutoff=_cutoff(args.cutoff)
        records=[row for row in public_results.latest_as_of(args.db,cutoff) if row['source_id']==capture['source_id']]
        summary=public_results.summarize_as_of(args.db,cutoff,source_id=capture['source_id'])
        result={'decision_cutoff':cutoff,'data_origin':'imported_historical','source':'OpenFootball, CC0-1.0',
                'import':imported,'eligible_count':len(records),'results':records[:args.limit], 'summary':summary,
                'note':'Match dates are source facts; first local availability is the import receipt.'}
        if args.format=='json':
            print(json.dumps(result,indent=2,ensure_ascii=False,sort_keys=True))
        else:
            print('OPENFOOTBALL REAL FIXTURES AND RESULTS —',len(records),'available source observations')
            print('Source SHA-256:',imported['source_hash'],'| cutoff:',cutoff)
            print('Unambiguous results:',summary['eligible_result_count']['value'])
            print('Outcomes:', ', '.join(f"{k}={v['value']}" for k,v in summary['counts'].items()))
            if summary.get('quality_flags'):
                print('Data quality flags:',len(summary['quality_flags']))
            for row in records[:args.limit]:
                print(row['event_date'],row['home'],'vs',row['away'],'| result:',row['outcome'] or 'unavailable')
        return 0
    if args.command=='forecast':
        capture=json.loads(args.receipt.read_text(encoding='utf-8-sig'))
        public_results.import_file(args.db,args.file,source_id=capture['source_id'],source_url=capture['source_url'],
                                   acquisition_id=capture['sha256'],receipt_path=args.receipt)
        cutoff=_cutoff('now')
        rows=public_results.latest_as_of(args.db,cutoff)
        candidates=sorted((r for r in rows if r['source_id']==capture['source_id'] and r.get('result_state')=='unavailable'
                           and (not args.event_date or r['event_date']==args.event_date)),
                          key=lambda r:(r['event_date'],r['fixture_key']))
        result=None
        for target in candidates:
            try:
                result=research.current_frequency_prior(rows,target,cutoff,lambda digest:market_store.raw_source(args.db,digest))
                break
            except ValueError as exc:
                if str(exc)!='FUTURE_FIXTURE_TIME_UNCERTAIN':
                    raise
        if result is None:
            raise ValueError('NO_ELIGIBLE_FUTURE_FIXTURE')
        if args.format=='json':
            print(json.dumps(result,indent=2,ensure_ascii=False,sort_keys=True))
        else:
            target=result['target']
            print('OPENFOOTBALL CURRENT DESCRIPTIVE FREQUENCY PRIOR')
            print(target['event_date'],target['home'],'vs',target['away'],'| training results:',result['training_count'])
            if result['abstained']:
                print('Unavailable:',result['reason'])
            else:
                for outcome,metric in result['probabilities'].items(): print(outcome,':',metric['value'])
            print('Model calculated now from eligible same-source results; calibration not established.')
        return 0
    if args.command=='archive':
        source_event=args.event or football_data.list_events(args.file,limit=1)['events'][0]['source_event_id']
        imported=football_data.import_event(args.db,args.file,source_event)
        cutoff=_cutoff(args.cutoff)
        rows=[r for r in market_store.get_as_of(args.db,cutoff)
              if r['event_id']==imported['event_id'] and r['source_hash']==imported['source_hash']]
        by_outcome={}
        for row in rows:
            phases=by_outcome.setdefault((row['provider_id'],row['outcome']),{})
            if row['quote_phase'] in phases:
                raise ValueError('AMBIGUOUS_ARCHIVE_SOURCE_PHASE')
            phases[row['quote_phase']]=row
        differences=[]
        for (provider,outcome),phases in sorted(by_outcome.items()):
            before=phases.get('source_recorded'); after=phases.get('source_close')
            if before and after:
                older=market_signals.convert_odds(before['odds_original'],before['odds_format'])
                later=market_signals.convert_odds(after['odds_original'],after['odds_format'])
                differences.append({'provider':provider,'outcome':outcome,'initial_recorded_odds':str(older),'closing_label_odds':str(later),
                    'difference':str(later-older),'units':'decimal odds',
                    'evidence_ids':[before['evidence_id'],after['evidence_id']],
                    'transformation':{'version':'archived-price-difference/1','formula':'source closing-labelled quote - source initial-recorded quote'},
                    'initial_raw_implied_probability':{'value':str(Decimal(1)/older),'units':'probability fraction',
                        'evidence_ids':[before['evidence_id']],'transformation':{'version':'archived-price-difference/1','formula':'1 / initial-recorded decimal odds'}},
                    'closing_raw_implied_probability':{'value':str(Decimal(1)/later),'units':'probability fraction',
                        'evidence_ids':[after['evidence_id']],'transformation':{'version':'archived-price-difference/1','formula':'1 / closing-labelled decimal odds'}},
                    'elapsed_time':'unavailable: source quote times unverified'})
        result={'decision_cutoff':cutoff,'actual_run_time':datetime.now(timezone.utc).isoformat(),
        'replay_mode':'OPERATIONAL_AS_OF_RECEIPT','data_origin':'imported_historical','source':football_data.ATTRIBUTION,
            'source_hash':imported['source_hash'],'source_reference':str(args.file),'import':imported,'evidence_manifest':rows,'labelled_price_differences':differences,
            'quality_flags':['SOURCE_QUOTE_TIME_UNKNOWN','SNAPSHOT_SYNCHRONIZATION_UNPROVEN',
                             'PROVIDER_MAPPING_UNVERIFIED','RECEIPT_VISIBILITY_BOUNDARY_UNVERIFIED'],
            'uncertainty_summary':'Quote times and synchronization are unknown; receipt transaction visibility requires further verification.',
            'research_tasks':[{'gap':'SOURCE_QUOTE_TIME_UNKNOWN','question':'Can time-stamped quotes with matching settlement rules be captured?',
                 'permitted_source':'documented public or user-supplied provider','priority_rationale':'Timing is required for line velocity and as-of alignment.',
                 'expected_evidence':'original quote timestamps and source identifiers','budget':'one bounded source check',
                 'stopping_condition':'aligned observations obtained or source unavailable','evidence_ids':[r['evidence_id'] for r in rows]}]}
        chosen=next((r for r in rows if r['provider_id']=='football-data-label:B365'
                     and r['outcome']=='home' and r['quote_phase']=='source_recorded'),None)
        if chosen:
            from .scenario import price_scenario
            result['scenario']=price_scenario(chosen,args.probability or '0.55',cutoff,
                raw_source=market_store.raw_source(args.db,chosen['source_hash']),
                fraction=args.fraction,cap=args.cap,bankroll=args.bankroll,stake_fraction=args.stake_fraction,
                trials=args.trials,steps=args.steps,seed=args.seed,
                scenario_source='user_supplied' if args.probability is not None else 'cli_default')
        else:
            result['scenario']=None
        if args.format=='json':
            print(json.dumps(result,indent=2,ensure_ascii=False,sort_keys=True))
        else:
            print('FOOTBALL-DATA HISTORICAL SOURCE CLAIMS —',football_data.ATTRIBUTION)
            if rows: print(rows[0]['home'],'vs',rows[0]['away'],'|',rows[0]['competition'],'| score',rows[0].get('source_score_home'),'-',rows[0].get('source_score_away'))
            for item in differences:
                print(item['provider'],item['outcome'],': recorded',item['initial_recorded_odds'],'closing-labelled',item['closing_label_odds'],'difference',item['difference'])
                print('  raw implied probabilities:',item['initial_raw_implied_probability']['value'],'→',item['closing_raw_implied_probability']['value'])
            print('Source quote timestamps and elapsed-time velocity: unavailable')
            if result['scenario']:
                m=result['scenario']['metrics']
                print('Present-time hypothetical probability:',args.probability or '0.55','| archived B365 home odds:',m['decimal_odds']['value'])
                print('Conditional expected return per unit:',m['expected_net_return_per_unit']['value'])
                print('Fractional capped Kelly:',m['fractional_capped_kelly']['value'])
                print('IID simulation:',args.trials,'trials,',args.steps,'steps, seed',args.seed)
                print('Simulation starting bankroll:',args.bankroll,'| fixed fractional stake:',args.stake_fraction)
                print('Mean final bankroll:',m['mean_final_bankroll']['value'])
                variance=m['sample_variance_final_bankroll']
                print('Final bankroll sample variance:',variance.get('value') or variance.get('reason'))
        return 0
    if args.command=='demo':
        market_store.import_file(args.db,_resource('examples','synthetic-market.json'),simulated=True)
        imported=estimate_store.import_estimate(args.db,_resource('examples','synthetic-estimate.json'),simulated=True)
        cutoff=_cutoff('2026-01-01T12:10:00Z')
        estimate=estimate_store.get_estimate(args.db,imported['source_hash'],cutoff,simulated=True)
        result=_report(args.db,'synthetic-match-001',cutoff,estimate,replay_mode='STRICT_PIT_SIMULATED')
    else:
        imported=estimate_store.import_estimate(args.db,args.estimate,simulated=args.synthetic_clock) if args.estimate else None
        cutoff=_cutoff(args.cutoff)
        estimate=estimate_store.get_estimate(args.db,imported['source_hash'],cutoff,simulated=args.synthetic_clock) if imported else None
        scenario={key:getattr(args,key) for key in ('fraction','cap','bankroll','trials','steps','seed')}
        result=_report(args.db,args.event,cutoff,estimate,replay_mode='STRICT_PIT_SIMULATED' if args.synthetic_clock else 'OPERATIONAL_AS_OF_RECEIPT',scenario=scenario)
        if imported and estimate is None:
            result['quality_flags'].append({'code':'ESTIMATE_NOT_AVAILABLE_AT_CUTOFF','evidence_ids':[]})
    if args.format in ('text','both'): _text(result)
    if args.format in ('json','both'): print(json.dumps(result,indent=2,ensure_ascii=False,sort_keys=True))
    return 0

