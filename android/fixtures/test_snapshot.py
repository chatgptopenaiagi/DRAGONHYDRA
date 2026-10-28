"""Check the checked-in mobile snapshot against its preserved source evidence."""
import hashlib
import json
from pathlib import Path
import sqlite3
import unittest

ROOT = Path(__file__).resolve().parents[2]
SNAPSHOT = ROOT / 'android/dragonhydra_mobile/assets/football-snapshot.json'
BACKUP = ROOT / 'release/genesis2/database/dragonhydra.sqlite3'


class SnapshotEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = json.loads(SNAPSHOT.read_text(encoding='utf-8'))
        cls.db = sqlite3.connect(f'file:{BACKUP.as_posix()}?mode=ro', uri=True)

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    def test_receipts_match_exact_source_bytes(self):
        for receipt in self.data['metadata']['source_receipts']:
            path = ROOT / 'data/raw' / receipt['source_id']
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), receipt['sha256'])
        self.assertEqual(hashlib.sha256(BACKUP.read_bytes()).hexdigest(), self.data['metadata']['database_backup_sha256'])

    def test_prediction_and_training_evidence_are_unmodified(self):
        forecast = self.data['forecast']
        row = self.db.execute('SELECT payload FROM cognitive_records WHERE record_id=?',
                              (forecast['prediction_record_id'],)).fetchone()
        original = json.loads(row[0])
        self.assertEqual(original['probabilities'], forecast['original_probability_strings'])
        self.assertEqual(original['target_evidence_id'], self.data['fixtures'][0]['evidence_id'])
        model = next(r for r in self.data['model_records'] if r['payload']['model_name']=='ensemble')
        self.assertEqual(model['payload']['training_manifest'],self.data['training_manifest'])
        self.assertAlmostEqual(sum(forecast['probabilities'].values()), 1.0)
        self.assertIsNone(forecast['decision_cutoff'])

    def test_market_claims_resolve_to_source_columns_and_receipts(self):
        self.assertEqual(len(self.data['archived_odds']),12)
        for quote in self.data['archived_odds']:
            row=self.db.execute('''SELECT a.payload,r.received_at,r.persisted_at,r.usable_at
                FROM acquisitions a JOIN receipts r USING(source_id,acquisition_id)
                WHERE a.source_id=? AND a.payload LIKE ?''',
                (quote['source_id'], '%"source_column":"'+quote['source_column']+'"%')).fetchone()
            self.assertIsNotNone(row)
            source=json.loads(row[0])
            self.assertEqual(quote['odds_decimal'],source['quotes'][0]['odds_original'])
            self.assertEqual((quote['received_at'],quote['persisted_at'],quote['usable_at']),row[1:])
            self.assertFalse(quote['quote_time_known'])
            self.assertNotEqual(quote['event_id'],self.data['fixtures'][0]['fixture_key'])

    def test_evaluation_values_resolve_to_saved_report(self):
        report=(ROOT/'release/genesis2/metadata/intelligence-output.txt').read_bytes()
        evaluation=self.data['evaluation']
        self.assertEqual(hashlib.sha256(report).hexdigest(),evaluation['recorded_report_sha256'])
        for key in ['brier','log_loss','accuracy']:
            self.assertIn(str(evaluation[key]), report.decode('utf-8-sig'))
        self.assertIn('not_operational_replay',evaluation['mode'])


if __name__=='__main__':
    unittest.main()
