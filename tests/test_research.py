import hashlib
from copy import deepcopy
from decimal import Decimal
import unittest

from dragonhydra import research as r


class ResearchTests(unittest.TestCase):
    def setUp(self):
        self.cutoff = '2026-01-02T12:00:00Z'
        self.pre = '2026-01-02T11:58:00Z'
        self.scope = dict(event_id='event-1', competition='Synthetic League', home='North', away='South',
                          market_type='1x2', period='full_time', outcome='home', line=None,
                          status='pregame', settlement='regulation')
        self.quote = dict(self.scope, **self.evidence('quote'), odds_original='2.00', odds_format='decimal')
        self.estimate = dict(self.scope, **self.evidence('model'), probability='0.55', model_version='test/1',
                             input_evidence=[self.evidence('model-input')])

    def evidence(self, name, when=None):
        time = when or self.pre
        raw = 'synthetic ' + name
        return dict(evidence_id=name, source_id='source-' + name, source_hash=hashlib.sha256(raw.encode()).hexdigest(),
                    source_raw=raw, data_origin='synthetic', source_published_at=time, received_at=time,
                    persisted_at=time, usable_at=time)

    def assess(self, **kwargs):
        return r.assess(self.quote, self.estimate, self.cutoff, trials=30, steps=12, seed=42, **kwargs)

    def test_expected_value_kelly_and_seeded_simulation(self):
        one = self.assess(fraction='0.5', cap='0.03')
        two = self.assess(fraction='0.5', cap='0.03')
        self.assertEqual(Decimal(one['expected_net_return_per_unit']['value']), Decimal('0.10'))
        self.assertEqual(Decimal(one['raw_kelly']['value']), Decimal('0.10'))
        self.assertEqual(Decimal(one['fractional_capped_kelly']['value']), Decimal('0.03'))
        self.assertEqual(one['simulation'], two['simulation'])
        self.assertEqual(set(one['expected_net_return_per_unit']['evidence_ids']), {'model','model-input','quote'})
        self.assertEqual(len(one['evidence_manifest']), 3)

    def test_negative_probability_candidate_has_zero_stake(self):
        self.estimate['probability'] = '0.4'
        result = self.assess()
        self.assertEqual(Decimal(result['expected_net_return_per_unit']['value']), Decimal('-0.2'))
        self.assertEqual(Decimal(result['fractional_capped_kelly']['value']), 0)

    def test_exact_boundary_and_late_evidence(self):
        self.quote.update(self.evidence('quote', self.cutoff))
        self.assess()
        future = '2026-01-02T12:00:00.000001Z'
        self.quote.update(self.evidence('quote', future))
        with self.assertRaisesRegex(ValueError, 'EVIDENCE_AFTER_CUTOFF'):
            self.assess()

    def test_model_cannot_depend_on_future_evidence(self):
        self.estimate['input_evidence'] = [self.evidence('future-input', self.cutoff)]
        with self.assertRaisesRegex(ValueError, 'MODEL_INPUT_AFTER_MODEL'):
            self.assess()

    def test_publication_after_receipt_is_rejected(self):
        self.quote['source_published_at'] = self.cutoff
        with self.assertRaisesRegex(ValueError, 'PUBLICATION_AFTER_RECEIPT'):
            self.assess()

    def test_invalid_and_mismatched_are_rejected(self):
        for value in ('NaN', 'Infinity', '-0.1', '1.1'):
            self.estimate['probability'] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.assess()
        self.estimate['probability'] = '0.5'
        self.estimate['settlement'] = 'includes-extra-time'
        with self.assertRaisesRegex(ValueError, 'INCOMPATIBLE_MARKET_SCOPE'):
            self.assess()

    def test_stale_quoted_price_and_corrupted_hash(self):
        self.assertIn('STALE_CAPTURE', self.assess(max_quote_age_seconds=30)['quality_flags'])
        self.quote['source_raw'] = 'tampered'
        with self.assertRaisesRegex(ValueError, 'SOURCE_HASH_MISMATCH'):
            self.assess()

    def test_historical_import_does_not_imply_fresh_quote(self):
        self.quote['data_origin'] = 'imported_historical'
        result = self.assess()
        self.assertIn('SOURCE_QUOTE_TIME_UNKNOWN', result['quality_flags'])
        self.assertIsNone(result['quote_age_seconds']['value'])

    def test_real_capture_age_is_not_source_quote_age(self):
        self.quote['data_origin'] = 'captured_real'
        result = self.assess()
        self.assertIn('SOURCE_QUOTE_TIME_UNKNOWN', result['quality_flags'])
        self.assertIsNone(result['quote_age_seconds']['value'])
        self.assertEqual(Decimal(result['capture_age_seconds']['value']), Decimal('120'))

    def test_live_requires_compatible_game_state(self):
        self.quote['status'] = self.estimate['status'] = 'live'
        with self.assertRaisesRegex(ValueError, 'LIVE_GAME_STATE_REQUIRED'):
            self.assess()
        self.quote['game_state_id'] = self.estimate['game_state_id'] = 'state-1'
        self.assess()

    def test_frequency_model_withholds_future_result(self):
        target = dict(self.scope, **self.evidence('fixture'), event_at='2026-01-02T14:00:00Z')
        prior = dict(self.scope, **self.evidence('prior','2026-01-01T14:00:00Z'), event_id='event-old',
                     event_at='2026-01-01T12:00:00Z', outcome='home')
        first = r.frequency_prediction([prior], target, self.cutoff)
        self.assertEqual(Decimal(first['probabilities']['home']['value']), Decimal('0.5'))
        future = dict(prior, event_id='future', outcome='not-a-valid-outcome',
                      usable_at='2026-01-03T12:00:00Z', source_hash='not-a-hash')
        second = r.frequency_prediction([prior, future], target, self.cutoff)
        self.assertEqual(first, second)
        forged=deepcopy(prior)
        forged.update(event_id='forged-future',outcome='invalid',source_hash='bad',
                      received_at='2026-01-03T12:00:00Z',persisted_at='2026-01-03T12:00:00Z',
                      usable_at=self.cutoff)
        self.assertEqual(first,r.frequency_prediction([prior,forged],target,self.cutoff))
        self.assertTrue(r.frequency_prediction([], target, self.cutoff)['abstained'])

    def test_chronological_scoring_and_future_isolation(self):
        pred = dict(self.estimate, decision_cutoff=self.cutoff, event_at='2026-01-02T13:00:00Z',
                    probabilities={'home':'0.5', 'draw':'0.25', 'away':'0.25'})
        outcome = dict(self.scope, **self.evidence('outcome','2026-01-02T15:00:00Z'), outcome='home')
        after = '2026-01-02T16:00:00Z'
        before = r.evaluate_chronological([dict(prediction=pred,outcome=outcome)], self.cutoff)
        self.assertEqual(before['metrics']['brier']['sample_size'], 0)
        scored = r.evaluate_chronological([dict(prediction=pred,outcome=outcome)], after)
        self.assertAlmostEqual(float(scored['cases'][0]['brier']['value']), 0.375)
        self.assertAlmostEqual(float(scored['cases'][0]['log_loss']['value']), 0.6931471805599453)
        forged_outcome=deepcopy(outcome)
        forged_outcome.update(received_at='2026-01-03T00:00:00Z',persisted_at='2026-01-03T00:00:00Z',
                              usable_at=after,source_hash='bad',outcome='invalid')
        forged_pred=deepcopy(pred)
        forged_pred.update(received_at='2026-01-03T00:00:00Z',persisted_at='2026-01-03T00:00:00Z',
                           usable_at=self.cutoff,source_hash='bad',probabilities={})
        self.assertEqual(scored,r.evaluate_chronological([dict(prediction=pred,outcome=outcome),
                         dict(prediction=pred,outcome=forged_outcome),dict(prediction=forged_pred,outcome=outcome)],after))

        later = deepcopy(outcome)
        later.update(usable_at='2026-01-03T00:00:00Z', outcome='INVALID', source_hash='bad')
        self.assertEqual(before, r.evaluate_chronological([dict(prediction=pred,outcome=outcome),
                                                           dict(prediction=pred,outcome=later)], self.cutoff))


if __name__ == '__main__':
    unittest.main()




