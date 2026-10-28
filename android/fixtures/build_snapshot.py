"""Export an inspectable, non-live mobile view from the GENESIS-2 SQLite backup.

The input backup and source receipts must already exist. The generator is read-only
with respect to SQLite; original evidence clocks and numerical strings are retained.
"""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3

ROOT = Path(__file__).resolve().parents[2]
DB = ROOT / 'release/genesis2/database/dragonhydra.sqlite3'
OUTPUT = ROOT / 'android/dragonhydra_mobile/assets/football-snapshot.json'
RUN_ID = '1758b1a7cfa442cab49f2f5410b865db'


def sha(content):
    return hashlib.sha256(content).hexdigest()


def main():
    conn = sqlite3.connect(f'file:{DB.as_posix()}?mode=ro', uri=True)
    rows = conn.execute('''SELECT r.kind,r.record_id,r.payload,c.received_at,c.persisted_at,c.usable_at
        FROM cognitive_records r JOIN cognitive_receipts c USING(record_id)
        WHERE r.kind IN ('model','prediction')''').fetchall()
    records = []
    for kind, record_id, payload, received, persisted, usable in rows:
        data = json.loads(payload)
        if data.get('run_id') == RUN_ID:
            records.append({'kind': kind, 'record_id': record_id, 'payload': data,
                            'receipt': {'received_at': received, 'persisted_at': persisted, 'usable_at': usable}})
    predictions = {r['payload']['model_name']: r for r in records if r['kind'] == 'prediction'}
    models = {r['payload']['model_name']: r for r in records if r['kind'] == 'model'}
    if set(predictions) != {'frequency','poisson_goals','elo','recency','ensemble'}:
        raise ValueError('Expected five original prediction records')
    ensemble, poisson = predictions['ensemble'], models['poisson_goals']['payload']['parameters']['result']
    target = ensemble['payload']['target_evidence']
    training = models['ensemble']['payload']['training_manifest']
    fixtures = sorted(training, key=lambda r: (r['event_date'],r['fixture_key']), reverse=True)[:12]
    fixtures.insert(0, target)
    market_rows = conn.execute('''SELECT a.payload,r.received_at,r.persisted_at,r.usable_at
        FROM acquisitions a JOIN receipts r USING(source_id,acquisition_id)
        WHERE a.source_id='football-data-e0-2025-26' ORDER BY a.acquisition_id''').fetchall()
    odds=[]
    for payload,received,persisted,usable in market_rows:
        source=json.loads(payload)
        for quote in source['quotes']:
            identity=[source['source_id'],source['acquisition_id'],quote['outcome']]
            evidence_id=sha(json.dumps(identity,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode())
            odds.append({'provider_label':source['source_provider_label'], 'outcome':quote['outcome'],
                'phase':source['quote_phase'],'odds_decimal':quote['odds_original'],
                'source_column':source['source_column'],'evidence_id':evidence_id,
                'received_at':received,'persisted_at':persisted,'usable_at':usable,
                'source_hash':source['source_hash'],'source_id':source['source_id'],
                'source_url':source['source_url'],'event_id':source['event_id'],
                'home':source['home'],'away':source['away'],'source_match_date':source['source_match_date'],
                'source_published_at':source['source_published_at'],'quote_time_known':False,
                'settlement':source['settlement'],'period':source['period'],
                'shared_feed':source['feed_id'],'transformation':source['transformation']})
    conn.close()
    report = ROOT/'release/genesis2/metadata/intelligence-output.txt'
    data={'metadata':{'schema':'dragonhydra-mobile-snapshot/1',
          'generated_at_utc':datetime.now(timezone.utc).isoformat(),
          'source_checkpoint':'5f49cfdfa7c67245d381078edfad7414bdba5a65',
          'database_backup_sha256':sha(DB.read_bytes()),
          'origin':'retained imported historical results, archived forecast, retrospective source-labelled odds',
          'limitations':['Not live; quote times and provider independence are unknown.',
                         'Archived odds describe a different fixture and cannot be compared to this forecast.',
                         'Historical file capture does not establish past operational availability.',
                         'Model estimates are uncalibrated; kickoff timezone is unknown.'],
          'source_receipts':[json.loads((ROOT/'data/raw'/name).read_text(encoding='utf-8')) for name in (
              'openfootball-2026-27-en1.json.receipt.json','openfootball-2025-26-en1.json.receipt.json',
              'football-data-2025-26-E0.csv.receipt.json')]},
          'forecast':{'home':target['home'],'away':target['away'],'competition':target['competition'],
              'event_date':target['event_date'],'origin':'archived_model_estimate',
              'model_version':ensemble['payload']['model_version'],
              'probabilities':{k:float(v) for k,v in ensemble['payload']['probabilities'].items()},
              'original_probability_strings':ensemble['payload']['probabilities'],
              'expected_goals':{'home':poisson['goal_rate_home']['value'],'away':poisson['goal_rate_away']['value']},
              'scorelines':[{'home':s['home_goals'],'away':s['away_goals'],'probability':s['probability']['value']} for s in poisson['scorelines']],
              'prediction_record_id':ensemble['record_id'],'model_run_id':ensemble['payload']['model_run_id'],
              'decision_cutoff':None,'decision_cutoff_note':'Not present in this retained prediction payload; receipt is not the decision cutoff.',
              'prediction_received_at':ensemble['receipt']['received_at'],
              'data_cutoff':models['ensemble']['payload']['data_cutoff'],
              'training_count':len(training),'weight_mode':models['ensemble']['payload']['parameters']['result']['weight_mode']},
          'fixtures':fixtures,'training_manifest':training,'archived_odds':odds,
          'prediction_records':list(predictions.values()),
          'model_records':list(models.values()),
          'evaluation':{'mode':'present_knowledge_chronological_holdout_not_operational_replay',
              'model_version':'chronological-frequency/1','sample_size':76,'brier':0.6470057659868708,
              'brier_sample_variance':0.018331170927197042,'log_loss':1.0706730837607508,
              'log_loss_sample_variance':0.03850355477407646,'accuracy':0.4605263157894737,
              'data_source_id':'openfootball-2025-26-en1.json',
              'recorded_report_path':'GENESIS-2 recovery archive metadata/intelligence-output.txt',
              'recorded_report_sha256':sha(report.read_bytes()),
              'recorded_report_cutoff':None,
              'recorded_report_cutoff_note':'The report text does not expose the holdout cutoff.'},
          'research_alerts':['ELIGIBLE_MODEL_EVALUATION_UNAVAILABLE','STALE_RESULTS_COVERAGE',
                             'MATCHING_MARKET_QUOTES_UNAVAILABLE','NO_SCORED_OPERATIONAL_PREDICTIONS']}
    OUTPUT.parent.mkdir(parents=True,exist_ok=True)
    OUTPUT.write_text(json.dumps(data,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    print(f'{OUTPUT}: {OUTPUT.stat().st_size} bytes; sha256={sha(OUTPUT.read_bytes())}; '
          f'{len(fixtures)} fixtures, {len(odds)} archival quotes, {len(predictions)} predictions')


if __name__=='__main__':
    main()
