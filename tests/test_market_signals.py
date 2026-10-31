import sys
import unittest
from copy import deepcopy
from decimal import Decimal, localcontext
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from dragonhydra.market_signals import compute_signals, convert_odds, implied_probability


def q(eid='a', provider='a', source='a', feed='a', outcome='home',
      price='2.00', at='2026-01-01T12:00:00Z', **changes):
    item = dict(data_origin='synthetic', evidence_id=eid, source_id=source, provider_id=provider, feed_id=feed,
                snapshot_id='snap-'+eid, outcome=outcome, odds_original=price,
                odds_format='decimal', received_at=at, persisted_at=at, usable_at=at,
                event_id='event-1', competition='league', home='Home', away='Away',
                market_type='1x2', period='full_time', status='pregame',
                settlement='regulation', line=None)
    item.update(changes)
    return item


class OddsConversionTests(unittest.TestCase):
    def test_conversions(self):
        self.assertEqual(convert_odds('2.50', 'decimal'), Decimal('2.50'))
        self.assertEqual(convert_odds('+150', 'american'), Decimal('2.5'))
        self.assertEqual(convert_odds('5/2', 'fractional'), Decimal('3.5'))
        with localcontext() as ctx:
            ctx.prec = 34
            self.assertEqual(convert_odds('-110', 'american'), Decimal(1)+Decimal(100)/Decimal(110))
        self.assertEqual(implied_probability('2.0'), Decimal('0.5'))

    def test_invalid_numbers(self):
        for v, f in [('NaN','decimal'),('Infinity','decimal'),('1','decimal'),
                     ('-99','american'),('0','american'),('1/0','fractional'),
                     ('-1/2','fractional'),('bad','decimal')]:
            with self.subTest(v=v), self.assertRaises(ValueError):
                convert_odds(v, f)


class SignalTests(unittest.TestCase):
    cutoff = '2026-01-01T12:05:00Z'

    def test_movement_and_comparable_provider(self):
        data = [q('a0', at='2026-01-01T12:00:00Z'),
                q('a1', price='2.10', at='2026-01-01T12:04:00Z'),
                q('b1', provider='b', source='b', feed='b', price='2.20', at='2026-01-01T12:04:30Z')]
        s = compute_signals(data, self.cutoff)
        movement = next(x for x in s['movements'] if x['provider_id']=='a')
        self.assertEqual(Decimal(movement['decimal_odds_change']['value']), Decimal('.10'))
        self.assertEqual(Decimal(movement['odds_change_per_hour']['value']), Decimal('1.5'))
        self.assertEqual(set(movement['decimal_odds_change']['evidence_ids']), {'a0','a1'})
        self.assertEqual(Decimal(s['provider_divergences'][0]['decimal_odds_difference']['value']), Decimal('.10'))
        self.assertEqual(s['best_price_discrepancies'][0]['higher_price_provider'], 'b')

    def test_future_data_and_malformed_future_do_not_change_output(self):
        original = [q()]
        before = compute_signals(original, self.cutoff)
        future = q('future', at='2026-01-01T12:06:00Z', persisted_at='broken')
        self.assertEqual(before, compute_signals(original+[future], self.cutoff))

    def test_margin_complete_only_same_snapshot(self):
        complete = [q('h', outcome='home', snapshot_id='s', price='2.0'),
                    q('d', outcome='draw', snapshot_id='s', price='4.0'),
                    q('w', outcome='away', snapshot_id='s', price='4.0')]
        out = compute_signals(complete, self.cutoff)['overrounds'][0]
        self.assertEqual(Decimal(out['overround']['value']), 0)
        self.assertEqual(set(out['overround']['evidence_ids']), {'h','d','w'})
        bad = deepcopy(complete)
        bad[2]['snapshot_id'] = 'different'
        self.assertIsNone(compute_signals(bad, self.cutoff)['overrounds'][0]['overround']['value'])

    def test_disjoint_feeds_never_make_up_a_movement(self):
        a=q('a', source='s1', feed='f1')
        b=q('b', source='s2', feed='f2', price='2.5', at='2026-01-01T12:01:00Z')
        s=compute_signals([a,b], self.cutoff)
        self.assertFalse(any(m['available'] for m in s['movements']))
        self.assertTrue(any(x['code']=='AMBIGUOUS_PROVIDER_SOURCES' for x in s['quality_flags']))

    def test_simultaneous_conflict_is_unavailable(self):
        a=q('a')
        b=q('b', price='2.50')
        s=compute_signals([a,b], self.cutoff)
        self.assertTrue(any(x['code']=='CONFLICTING_SOURCE_QUOTES' for x in s['quality_flags']))
        self.assertIsNone(s['quote_metrics'][0]['decimal_odds']['value'])

    def test_stale_and_misaligned_are_reasoned_unavailable(self):
        a=q('a', at='2026-01-01T12:00:00Z')
        b=q('b', provider='b',source='b',feed='b',at='2026-01-01T12:04:00Z')
        s=compute_signals([a,b], self.cutoff)
        self.assertEqual(s['provider_divergences'][0]['decimal_odds_difference']['reason'], 'EXCESSIVE_TIME_SEPARATION')
        s=compute_signals([a,b], '2026-01-01T12:20:00Z')
        self.assertEqual(s['provider_divergences'][0]['decimal_odds_difference']['reason'], 'STALE_QUOTE')

    def test_correction_uses_original_market_time(self):
        corrected = q('corrected', price='2.50', at='2026-01-01T12:02:00Z',
                      effective_market_received_at='2026-01-01T12:00:00Z', supersedes_acquisition_id='old')
        newer = q('newer', price='2.20', at='2026-01-01T12:01:00Z')
        s=compute_signals([corrected,newer], self.cutoff)
        self.assertEqual(s['quote_metrics'][0]['decimal_odds']['value'], '2.20')
        self.assertEqual(Decimal(s['movements'][0]['decimal_odds_change']['value']), Decimal('-.30'))

    def test_conflicted_latest_quote_cannot_produce_margin(self):
        group = [q('h',outcome='home',snapshot_id='s'),
                 q('d',outcome='draw',snapshot_id='s',price='3.0'),
                 q('w',outcome='away',snapshot_id='s',price='4.0'),
                 q('h2',outcome='home',snapshot_id='other',price='2.50')]
        output = compute_signals(group, self.cutoff)
        self.assertEqual(output['overrounds'][0]['overround']['reason'], 'CONFLICTING_SOURCE_QUOTES')

    def test_mismatched_scope_has_explicit_reason(self):
        a=q('a', settlement='regulation')
        b=q('b', provider='b',source='b',feed='b',settlement='extra_time')
        s=compute_signals([a,b], self.cutoff)
        self.assertEqual(s['provider_divergences'][0]['decimal_odds_difference']['reason'], 'INCOMPATIBLE_MARKET_DEFINITIONS')
        self.assertFalse(s['best_price_discrepancies'])

    def test_snapshot_with_different_receipt_clocks_is_not_complete(self):
        group = [q('a',outcome='home',snapshot_id='s'),
                 q('b',outcome='draw',snapshot_id='s'),
                 q('c',outcome='away',snapshot_id='s',at='2026-01-01T12:01:00Z')]
        self.assertEqual(compute_signals(group, self.cutoff)['overrounds'][0]['overround']['reason'], 'SNAPSHOT_TIME_MISMATCH')

    def test_archival_import_time_is_not_quote_time(self):
        rows = [q('h0',outcome='home',snapshot_id='s', data_origin='imported_historical'),
                q('d0',outcome='draw',snapshot_id='s', data_origin='imported_historical'),
                q('a0',outcome='away',snapshot_id='s', data_origin='imported_historical'),
                q('h1',outcome='home',snapshot_id='next', price='2.5', data_origin='imported_historical',
                  at='2026-01-01T12:01:00Z'),
                q('b',source='b',provider='b',feed='b',outcome='home',data_origin='imported_historical')]
        out = compute_signals(rows, self.cutoff)
        self.assertTrue(all(item['quote_age']['reason']=='HISTORICAL_QUOTE_TIME_UNAVAILABLE'
                            for item in out['quote_metrics']))
        self.assertFalse(any(item['available'] for item in out['movements']))
        self.assertTrue(all(item['overround']['reason']=='HISTORICAL_SNAPSHOT_SYNCHRONIZATION_UNPROVED'
                            for item in out['overrounds']))
        self.assertEqual(out['provider_divergences'][0]['decimal_odds_difference']['reason'],
                         'HISTORICAL_QUOTE_TIME_UNAVAILABLE')
        self.assertFalse(out['best_price_discrepancies'])

    def test_unknown_archival_scope_keeps_quotes_but_blocks_comparison(self):
        a=q('a', data_origin='imported_historical', status='unknown', period='unknown',
            settlement='unknown', quote_phase='source_open')
        b=q('b', provider='b', source='b', feed='b', data_origin='imported_historical',
            status='unknown', period='unknown', settlement='unknown')
        out=compute_signals([a,b], self.cutoff)
        self.assertEqual(out['quote_metrics'][0]['decimal_odds']['value'], '2.00')
        self.assertEqual(out['quote_metrics'][0]['quote_phase'], 'source_open')
        self.assertEqual(out['provider_divergences'][0]['decimal_odds_difference']['reason'], 'MARKET_SCOPE_UNVERIFIED')
        self.assertTrue(any(flag['code']=='MARKET_SCOPE_UNVERIFIED' for flag in out['quality_flags']))
        self.assertFalse(out['best_price_discrepancies'])

    def test_real_capture_age_is_not_asserted_actual_quote_age(self):
        out = compute_signals([q('a',data_origin='captured_real')], self.cutoff)
        age = out['quote_metrics'][0]['quote_age']
        self.assertEqual(age['units'], 'seconds since system capture')
        self.assertIn('may be older', age['interpretation'])

    def test_complete_half_unit_total_overround_and_estimates(self):
        rows = [q('over', market_type='totals', line='2.5', snapshot_id='same', outcome='over', price='1.90'),
                q('under', market_type='totals', line='2.50', snapshot_id='same', outcome='under', price='1.90')]
        result = compute_signals(rows, self.cutoff)['overrounds'][0]
        with localcontext() as ctx:
            ctx.prec = 34
            expected = Decimal(1) / Decimal(19)
        self.assertEqual(Decimal(result['overround']['value']), expected)
        self.assertEqual(set(result['overround']['evidence_ids']), {'over', 'under'})
        self.assertEqual(Decimal(result['proportional_margin_removed_estimates']['over']['value']), Decimal('0.5'))
        self.assertIn('not true probability', result['proportional_margin_removed_estimates']['under']['interpretation'])

    def test_incomplete_totals_are_unavailable(self):
        rows = [q('over', market_type='totals', line='2.5', snapshot_id='same', outcome='over', price='1.90')]
        result = compute_signals(rows, self.cutoff)
        self.assertEqual(result['overrounds'][0]['overround']['reason'], 'INCOMPLETE_OR_DUPLICATE_TOTAL_SET')
        self.assertTrue(any(f['code']=='INCOMPLETE_MARKET' for f in result['quality_flags']))

    def test_integer_or_quarter_totals_refuse_false_complete_margin(self):
        for line in ('2.0', '2.25', '2.75', '-0.5'):
            with self.subTest(line=line):
                rows=[q('over',market_type='totals',line=line,snapshot_id='s',outcome='over'),
                      q('under',market_type='totals',line=line,snapshot_id='s',outcome='under')]
                margin=compute_signals(rows, self.cutoff)['overrounds'][0]['overround']
                self.assertEqual(margin['reason'], 'TOTAL_LINE_REQUIRES_PUSH_OR_SPLIT_HANDLING')

    def test_totals_with_mismatched_lines_are_not_compared(self):
        rows=[q('a',market_type='totals',line='2.5',outcome='over'),
              q('b',market_type='totals',line='3.5',outcome='over',provider='b',source='b',feed='b')]
        result=compute_signals(rows, self.cutoff)
        self.assertEqual(result['provider_divergences'][0]['decimal_odds_difference']['reason'], 'INCOMPATIBLE_MARKET_DEFINITIONS')
        self.assertFalse(result['best_price_discrepancies'])

    def test_total_line_is_required(self):
        result=compute_signals([q('a',market_type='totals',line=None,outcome='over')], self.cutoff)
        self.assertEqual(result['quality_flags'][0]['code'], 'MISSING_LINE')
        self.assertFalse(result['quote_metrics'])

    def test_historical_open_close_labels_do_not_create_conflict(self):
        rows = [q('open',source='history',feed='history-open',data_origin='imported_historical',
                  status='unknown',period='unknown',settlement='unknown',quote_phase='source_open',price='1.80'),
                q('close',source='history',feed='history-close',data_origin='imported_historical',
                  status='unknown',period='unknown',settlement='unknown',quote_phase='source_close',price='2.20')]
        result=compute_signals(rows, self.cutoff)
        self.assertEqual({x['quote_phase'] for x in result['quote_metrics']},{'source_open','source_close'})
        self.assertFalse(any(f['code']=='CONFLICTING_SOURCE_QUOTES' for f in result['quality_flags']))
        self.assertFalse(any(m['available'] for m in result['movements']))

    def test_historical_labels_same_feed_stay_distinct(self):
        rows = [q('open',source='history',feed='history',data_origin='imported_historical',quote_phase='source_open',price='1.80'),
                q('close',source='history',feed='history',data_origin='imported_historical',quote_phase='source_close',price='2.20')]
        result=compute_signals(rows, self.cutoff)
        self.assertEqual(len(result['quote_metrics']), 2)
        self.assertFalse(any(f['code']=='CONFLICTING_SOURCE_QUOTES' for f in result['quality_flags']))

    def test_live_comparison_requires_game_state(self):
        a=q('a', status='live')
        b=q('b', provider='b',source='b',feed='b',status='live')
        s=compute_signals([a,b], self.cutoff)
        self.assertEqual(s['provider_divergences'][0]['decimal_odds_difference']['reason'], 'LIVE_GAME_STATE_UNAVAILABLE')


if __name__ == '__main__':
    unittest.main()







