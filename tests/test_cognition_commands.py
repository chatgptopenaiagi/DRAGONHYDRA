"""Local cognitive orchestration contract tests using fictional fixture bytes."""
from datetime import datetime, timedelta, timezone
from contextlib import closing
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import sqlite3
import unittest
from unittest.mock import patch
from uuid import uuid4

from dragonhydra import public_results
from dragonhydra.cognition import commands, runtime
from dragonhydra import cli

ROOT=Path(__file__).resolve().parents[1]


class CognitiveCommandsTests(unittest.TestCase):
    def setUp(self):
        folder=ROOT/'runtime'
        folder.mkdir(exist_ok=True)
        self.db=folder/('cognition-test-'+uuid4().hex+'.sqlite')
        self.addCleanup(self.db.unlink,missing_ok=True)
        self.addCleanup(Path(str(self.db)+'-journal').unlink,missing_ok=True)
        day=datetime.now(timezone.utc).date()
        matches=[]
        for i in range(8):
            home='Home' if i==0 else f'Other Home {i}'
            away='Away' if i==1 else f'Other Away {i}'
            matches.append({'date':(day-timedelta(days=20-i)).isoformat(),'team1':home,
                            'team2':away,'score':{'ft':[i%3,(i+1)%2]}})
        matches.append({'date':(day+timedelta(days=5)).isoformat(),'team1':'Home','team2':'Away'})
        raw=json.dumps({'name':'Fictional Test League','matches':matches}).encode()
        with closing(sqlite3.connect(str(self.db))) as db:
            public_results.ingest_bytes(db,raw,source_id='fictional-current-source',
                source_url='fictional:test-only',acquisition_id='test-source')
        self.patches=[patch.object(runtime,'FILES',('fictional-past-source','fictional-current-source')),
                      patch.object(runtime,'prepare',return_value=[])]
        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)

    def test_predictions_are_stored_and_gap_tasks_are_evidence_linked(self):
        result=commands.run('predict',self.db)
        self.assertEqual(result['forecast']['training_count'],8)
        self.assertEqual(len(result['model_runs']),5)
        self.assertEqual(len(result['predictions']),5)
        view=commands.run('memory',self.db)
        self.assertEqual(view['counts']['predictions'],5)
        tasks=commands.run('research',self.db)
        self.assertIn('MATCHING_MARKET_QUOTES_UNAVAILABLE',{t['gap'] for t in tasks['research_tasks']})
        self.assertTrue(tasks['persisted_tasks'])
        earlier=commands.run('memory',self.db,cutoff='2000-01-01T00:00:00Z')
        self.assertEqual(earlier['counts']['predictions'],0)

    def test_unscored_forecasts_are_not_evaluation_successes(self):
        commands.run('predict',self.db)
        result=commands.run('evaluate',self.db)
        self.assertEqual(result['operational']['eligible_prediction_count'],5)
        self.assertTrue(all(g['metrics']['brier']['sample_size']==0 for g in result['operational']['groups']))
        self.assertEqual(result['present_knowledge_holdout']['metrics']['brier']['sample_size'],0)

    def test_historical_cutoff_does_not_replace_actual_run_clock(self):
        cutoff='2000-01-01T00:00:00Z'
        result=commands.run('evaluate',self.db,cutoff=cutoff)
        self.assertEqual(result['evaluation_cutoff'],cutoff)
        self.assertGreater(datetime.fromisoformat(result['actual_run_time'].replace('Z','+00:00')),
                           datetime.fromisoformat(cutoff.replace('Z','+00:00')))
        self.assertEqual(result['operational']['eligible_prediction_count'],0)

    def test_predict_cli_emits_json_and_persists_forecasts(self):
        output=io.StringIO()
        with redirect_stdout(output):
            status=cli.main(['predict','--db',str(self.db),'--format','json'])
        self.assertEqual(status,0)
        result=json.loads(output.getvalue())
        self.assertEqual(len(result['predictions']),5)
        self.assertEqual(result['forecast']['training_count'],8)
        self.assertTrue(result['forecast']['ensemble']['probabilities']['home']['evidence_ids'])

    def test_intelligence_report_keeps_unmapped_markets_and_tasks_separate(self):
        result=commands.run('intelligence',self.db)
        self.assertEqual(result['report_mode'],'CURRENT_COMPOSITE_WITH_SEPARATE_CUTOFFS')
        self.assertEqual(result['run_id'],result['prediction']['run_id'])
        self.assertEqual(len(result['prediction']['predictions']),5)
        self.assertEqual(result['market_analysis']['model_vs_market']['reason'],
                         'VERIFIED_FIXTURE_AND_SETTLEMENT_MAPPING_UNAVAILABLE')
        self.assertEqual(result['research']['matched_quote_evidence_ids'],[])
        self.assertIn('MATCHING_MARKET_QUOTES_UNAVAILABLE',
                      {item['gap'] for item in result['research']['research_tasks']})
        self.assertEqual(result['memory_counts']['predictions'],5)

    def test_no_training_data_abstains_and_emits_research_tasks(self):
        db_path=(ROOT/'runtime')/('cognition-empty-'+uuid4().hex+'.sqlite')
        self.addCleanup(db_path.unlink,missing_ok=True)
        day=(datetime.now(timezone.utc).date()+timedelta(days=5)).isoformat()
        raw=json.dumps({'name':'Fictional Test League','matches':[{'date':day,'team1':'Home','team2':'Away'}]}).encode()
        with closing(sqlite3.connect(str(db_path))) as db:
            public_results.ingest_bytes(db,raw,source_id='fictional-current-source',
                source_url='fictional:test-only',acquisition_id='empty-source')
        prediction=commands.run('predict',db_path)
        self.assertTrue(prediction['forecast']['abstained'])
        self.assertEqual(prediction['predictions'],[])
        research=commands.run('research',db_path)
        self.assertTrue(research['research_tasks'])

    def test_ambiguous_rescheduled_target_is_skipped_and_reported(self):
        day=datetime.now(timezone.utc).date()
        raw=json.dumps({'name':'Fictional Test League','matches':[
            {'date':(day+timedelta(days=6)).isoformat(),'team1':'Home','team2':'Away'},
            {'date':(day+timedelta(days=7)).isoformat(),'team1':'Other Team','team2':'Fresh Team'}]}).encode()
        with closing(sqlite3.connect(str(self.db))) as db:
            public_results.ingest_bytes(db,raw,source_id='fictional-current-source',
                source_url='fictional:test-only',acquisition_id='rescheduled-source')
        result=commands.run('research',self.db)
        self.assertIn('AMBIGUOUS_FIXTURE_DATE',{item['gap'] for item in result['research_tasks']})


if __name__=='__main__':
    unittest.main()
