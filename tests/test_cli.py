"""End-to-end CLI checks on isolated workspace-owned data files."""
import base64
import csv
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import unittest
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]


class CliTests(unittest.TestCase):
    def setUp(self):
        self.runtime = ROOT / 'runtime'
        self.runtime.mkdir(exist_ok=True)
        stem = 'test-cli-' + uuid4().hex
        self.db = self.runtime / (stem + '.sqlite')
        self.manifest = self.runtime / (stem + '.json')
        self.estimate = self.runtime / (stem + '.estimate.json')
        self.source = self.runtime / (stem + '.csv')
        self.results_file = self.runtime / (stem + '.results.json')
        self.receipt = self.runtime / (stem + '.receipt.json')
        for path in (self.db,self.manifest,self.estimate,self.source,self.results_file,self.receipt,
                     Path(str(self.db)+'-journal'),Path(str(self.db)+'-wal'),Path(str(self.db)+'-shm')):
            self.addCleanup(path.unlink, missing_ok=True)

    def cli(self, *args):
        result = subprocess.run([sys.executable,'-B',str(ROOT/'dragon.py'),*map(str,args)],
                                cwd=ROOT,text=True,encoding='utf-8',capture_output=True)
        if result.returncode:
            self.fail(f'CLI failed: {result.args}\nstdout: {result.stdout}\nstderr: {result.stderr}')
        return json.loads(result.stdout)

    def report(self, cutoff='2026-01-01T12:10:00Z', *, simulated=True, estimate=None):
        args = ['report','--db',self.db,'--event','synthetic-match-001','--cutoff',cutoff,'--format','json']
        if simulated:
            args.append('--synthetic-clock')
        if estimate:
            args.extend(['--estimate',estimate])
        return self.cli(*args)

    def test_bounded_watch_imports_once_and_uses_operational_clock(self):
        result = self.cli('watch','--file',ROOT/'examples/synthetic-market.json','--db',self.db,
                          '--iterations','2','--interval','0','--format','json')
        self.assertEqual(result['clock_mode'],'operational')
        self.assertEqual([e['status'] for e in result['events']],['IMPORTED','UNCHANGED'])
        report = self.cli('report','--db',self.db,'--event','synthetic-match-001','--cutoff','now','--format','json')
        self.assertEqual(len(report['evidence_manifest']),18)
        self.assertTrue(all(row['clock_mode']=='operational' for row in report['evidence_manifest']))

    def test_demo_provenance_reproducibility_and_idempotence(self):
        a = self.cli('demo','--db',self.db,'--format','json')
        b = self.cli('demo','--db',self.db,'--format','json')
        self.assertEqual(a['replay_mode'], 'STRICT_PIT_SIMULATED')
        self.assertEqual(a['data_origin'], ['synthetic'])
        self.assertEqual(len(a['evidence_manifest']), 18)
        self.assertEqual(a['signals'], b['signals'])
        self.assertEqual(a['evidence_manifest'], b['evidence_manifest'])
        self.assertIsNotNone(a['assessment'])
        evidence_ids = {row['evidence_id'] for row in a['evidence_manifest']}
        for item in a['evidence_manifest']:
            raw = base64.b64decode(a['raw_source_manifest'][item['source_hash']]['bytes'])
            self.assertEqual(hashlib.sha256(raw).hexdigest(), item['source_hash'])
        for group in ('quote_metrics','movements','overrounds','provider_divergences'):
            for item in a['signals'][group]:
                for metric in item.values():
                    if isinstance(metric,dict) and 'evidence_ids' in metric:
                        self.assertTrue(set(metric['evidence_ids']).issubset(evidence_ids))
        assessment_ids = {r['evidence_id'] for r in a['assessment']['evidence_manifest']}
        self.assertTrue(set(a['assessment']['expected_net_return_per_unit']['evidence_ids']).issubset(assessment_ids))
        self.assertTrue(assessment_ids.intersection(evidence_ids))

    def test_replay_clock_isolation_and_absent_estimate(self):
        self.cli('import','--file',ROOT/'examples/synthetic-market.json','--db',self.db,'--synthetic-clock')
        self.assertEqual(len(self.report(simulated=False)['evidence_manifest']), 0)
        self.assertEqual(len(self.report()['evidence_manifest']), 18)
        estimate = json.loads((ROOT/'examples/synthetic-estimate.json').read_text(encoding='utf-8'))
        for field in ('source_published_at','received_at','persisted_at','usable_at'):
            estimate[field] = '2026-01-01T12:20:00Z'
        self.estimate.write_text(json.dumps(estimate),encoding='utf-8')
        result = self.report(estimate=self.estimate)
        self.assertEqual(len(result['evidence_manifest']),18)
        self.assertIsNone(result['assessment'])
        self.assertIn('ESTIMATE_NOT_AVAILABLE_AT_CUTOFF',{q['code'] for q in result['quality_flags']})

    def test_later_correction_preserves_earlier_report(self):
        self.cli('import','--file',ROOT/'examples/synthetic-market.json','--db',self.db,'--synthetic-clock')
        before = self.report()
        snapshots = json.loads((ROOT/'examples/synthetic-market.json').read_text(encoding='utf-8'))['snapshots']
        correction = next(x for x in snapshots if x['acquisition_id']=='provider-a-1')
        correction['acquisition_id']='provider-a-correction'
        correction['supersedes_acquisition_id']='provider-a-1'
        correction['received_at']='2026-01-01T12:15:00Z'
        correction['persisted_at']='2026-01-01T12:15:01Z'
        correction['quotes'][0]['odds_original']='2.45'
        self.manifest.write_text(json.dumps({'snapshots':[correction]}),encoding='utf-8')
        self.assertEqual(self.cli('import','--file',self.manifest,'--db',self.db,'--synthetic-clock')['inserted'],1)
        later = self.report()
        self.assertEqual(before['evidence_manifest'],later['evidence_manifest'])
        self.assertEqual(before['signals'],later['signals'])
        after = self.report('2026-01-01T12:15:01Z')
        self.assertIn('provider-a-correction',{r['acquisition_id'] for r in after['evidence_manifest']})
        self.assertNotIn('provider-a-1',{r['acquisition_id'] for r in after['evidence_manifest']})

    def test_archived_source_claims_respect_actual_local_cutoff(self):
        path = ROOT / 'data/raw/football-data-2025-26-E0.csv'
        if not path.exists():
            self.skipTest('Football-Data local source not available')
        args=['archive','--db',self.db,'--format','json']
        old = self.cli(*args,'--cutoff','2025-08-16T00:00:00Z')
        self.assertEqual(old['evidence_manifest'],[])
        self.assertEqual(old['labelled_price_differences'],[])
        current = self.cli(*args,'--cutoff','now')
        self.assertEqual(len(current['evidence_manifest']),12)
        self.assertTrue(all(r['home']=='Liverpool' and r['away']=='Bournemouth' for r in current['evidence_manifest']))
        self.assertEqual({r['source_provider_label'] for r in current['evidence_manifest']},{'B365','PS'})
        self.assertEqual({r['feed_id'] for r in current['evidence_manifest']},{'football-data-shared-archive'})
        self.assertEqual(len(current['labelled_price_differences']),6)
        self.assertTrue(all(r['quote_time_known'] is False and r['result_time_known'] is False for r in current['evidence_manifest']))
        self.assertEqual(current['scenario']['metrics']['expected_net_return_per_unit']['value'],'-0.285')
        self.assertEqual(current['scenario']['metrics']['fractional_capped_kelly']['value'],'0.00')
        self.assertEqual(current['scenario']['configuration_evidence']['source_id'],'cli-default-scenario')
        scenario_refs={r['evidence_id'] for r in current['evidence_manifest']}
        self.assertIn(current['scenario']['quote_evidence']['evidence_id'],scenario_refs)
        self.assertIsNone(old['scenario'])
        self.assertEqual(current['import']['duplicates'],12)
        self.assertTrue(all(item['elapsed_time'].startswith('unavailable') for item in current['labelled_price_differences']))
        self.assertTrue(all({row['source_hash']} == {current['source_hash']} for row in current['evidence_manifest']))

    def test_public_results_idempotence_and_replay(self):
        raw=json.dumps({'name':'Test league','matches':[{'date':'2025-01-01','team1':'A','team2':'B','score':{'ft':[2,1]}}]}).encode()
        self.results_file.write_bytes(raw)
        receipt={'source_id':'test-source','source_url':'https://raw.githubusercontent.com/openfootball/football.json/master/2025-26/en.1.json',
                 'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw),'captured_at':datetime.now(timezone.utc).isoformat()}
        self.receipt.write_text(json.dumps(receipt),encoding='utf-8')
        args=['results','--file',self.results_file,'--receipt',self.receipt,'--db',self.db,'--format','json']
        old=self.cli(*args,'--cutoff','2025-01-02T00:00:00Z')
        self.assertEqual(old['eligible_count'],0)
        current=self.cli(*args,'--cutoff','now')
        self.assertTrue(current['import']['duplicate'])
        self.assertEqual(current['eligible_count'],1)
        self.assertEqual(current['results'][0]['outcome'],'home')
        self.assertEqual(current['results'][0]['data_origin'],'imported_historical')

    def test_current_fixture_prior_uses_eligible_completed_results(self):
        today=datetime.now(timezone.utc).date()
        past=(today-timedelta(days=10)).isoformat()
        future=(today+timedelta(days=10)).isoformat()
        data={'name':'Test league','matches':[
            {'date':past,'team1':'Older A','team2':'Older B','score':{'ft':[2,1]}},
            {'date':future,'team1':'Future A','team2':'Future B'}]}
        raw=json.dumps(data).encode('utf-8')
        self.results_file.write_bytes(raw)
        receipt={'source_id':'test-source','source_url':'https://example.invalid/fixtures.json',
                 'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw),'captured_at':datetime.now(timezone.utc).isoformat()}
        self.receipt.write_text(json.dumps(receipt),encoding='utf-8')
        result=self.cli('forecast','--db',self.db,'--file',self.results_file,'--receipt',self.receipt,'--format','json')
        self.assertFalse(result['abstained'])
        self.assertEqual(result['target']['home'],'Future A')
        self.assertEqual(result['training_count'],1)
        self.assertEqual(result['probabilities']['home']['value'],'0.5')
        self.assertEqual(result['probabilities']['draw']['value'],'0.25')
        self.assertEqual(result['training_manifest'][0]['outcome'],'home')
        self.assertEqual(result['model_status'],'ephemeral_current_calculation')
        self.assertIsNone(result['model_persisted_at'])

    def test_chronological_scoring_is_reproducible(self):
        one=self.cli('score','--format','json')
        two=self.cli('score','--format','json')
        self.assertEqual(one,two)
        self.assertEqual(one['replay_mode'],'SYNTHETIC_HYPOTHETICAL_REPLAY')
        self.assertGreater(one['metrics']['brier']['sample_size'],0)
        for case in one['cases']:
            self.assertTrue(case['brier']['evidence_ids'])
            self.assertIn('outcome',case)


if __name__=='__main__':
    unittest.main()
