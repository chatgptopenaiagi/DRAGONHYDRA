"""Synthetic, network-free fixtures exercise published StatsBomb/NFL schemas.

Real service retrieval is recorded separately under project scratch; these
fixtures intentionally include malformed input and never imply a live feed.
"""
from __future__ import annotations

from copy import deepcopy
import csv
import hashlib
import io
import json
import unittest

from dragonhydra.connectors.core import ConnectorError, Document
from dragonhydra.connectors import research


CATALOG = [{'competition_id': 43, 'season_id': 106, 'competition_name': 'FIFA World Cup', 'season_name': '2022'}]
MATCH = {'match_id': 3857276, 'match_date': '2022-12-01', 'kick_off': '15:00:00.000',
         'competition': {'competition_id': 43, 'competition_name': 'FIFA World Cup'},
         'season': {'season_id': 106, 'season_name': '2022'},
         'home_team': {'home_team_id': 1833, 'home_team_name': 'Canada'},
         'away_team': {'away_team_id': 788, 'away_team_name': 'Morocco'},
         'home_score': 1, 'away_score': 2, 'match_status': 'available',
         'competition_stage': {'id': 10, 'name': 'Group Stage'},
         'stadium': {'name': 'Synthetic fixture stadium'}, 'last_updated': '2026-05-04T01:46:04.664252'}
NFL_FIELDS = ['game_id', 'season', 'game_type', 'week', 'gameday', 'gametime', 'away_team',
              'away_score', 'home_team', 'home_score', 'home_rest', 'away_rest', 'result',
              'total', 'overtime', 'temp', 'wind', 'home_moneyline', 'away_moneyline', 'stadium']
NFL_ROW = dict.fromkeys(NFL_FIELDS, '') | {'game_id': '2025_01_DAL_PHI', 'season': '2025',
          'game_type': 'REG', 'week': '1', 'gameday': '2025-09-04', 'gametime': '20:20',
          'away_team': 'DAL', 'home_team': 'PHI', 'away_score': '20', 'home_score': '24',
          'home_rest': '7', 'away_rest': '7', 'result': '4', 'total': '44', 'overtime': '0',
          'temp': '0', 'wind': '0', 'home_moneyline': '-110', 'away_moneyline': '+100'}


def csv_bytes(rows, fields=NFL_FIELDS):
    output = io.StringIO(newline='')
    writer = csv.DictWriter(output, fieldnames=fields)
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue().encode()


class RetainingFixtureTransport:
    def __init__(self, payloads):
        self.payloads = list(payloads)
        self.documents = []
        self.calls = []

    def get(self, url, headers=None):
        self.calls.append((url, headers))
        payload = self.payloads.pop(0)
        if isinstance(payload, Exception):
            raise payload
        body = payload if isinstance(payload, bytes) else json.dumps(payload, ensure_ascii=False).encode()
        resolved = url.replace('https://github.com/statsbomb/open-data/raw/refs/heads/master/',
                               'https://raw.githubusercontent.com/hudl/open-data/refs/heads/master/')
        document = Document(url, resolved, body, '2026-10-31T12:00:00Z', hashlib.sha256(body).hexdigest())
        self.documents.append(document)  # Retention precedes Document.json()/text().
        return document


class ResearchConnectorTests(unittest.TestCase):
    def fetch_stats(self, rows=None, catalog=None, check=lambda: None, config=None):
        transport = RetainingFixtureTransport([CATALOG if catalog is None else catalog, [deepcopy(MATCH)] if rows is None else rows])
        return research.fetch('statsbomb', config or {}, 'never-send-this-secret', transport, check), transport

    def fetch_nfl(self, rows=None, check=lambda: None, config=None, body=None):
        transport = RetainingFixtureTransport([body if body is not None else csv_bytes([NFL_ROW] if rows is None else rows)])
        return research.fetch('nflverse', config or {}, 'never-send-this-secret', transport, check), transport

    def test_configuration_defaults_and_bounded_range(self):
        self.assertEqual(research.validate_config('statsbomb', {}), {'competition_id': 43, 'season_id': 106})
        self.assertEqual(research.validate_config('nflverse', {}), {'seasons': [2025]})
        self.assertEqual(research.validate_config('nflverse', {'start_season': 2023, 'end_season': 2025}), {'seasons': [2023, 2024, 2025]})
        self.assertEqual(research.validate_config('nflverse', {'seasons': [2025, 2024, 2025]}), {'seasons': [2024, 2025]})

    def test_untrusted_configuration_never_becomes_a_request(self):
        for provider, config in [('statsbomb', {'competition_id': '../secrets'}), ('statsbomb', {'url': 'https://evil.example/'}),
                                 ('statsbomb', {'season_id': True}), ('nflverse', {'seasons': []}),
                                 ('nflverse', {'seasons': [2025] * 6}), ('nflverse', {'start_season': 2020, 'end_season': 2025}),
                                 ('nflverse', {'season': 2025, 'seasons': [2025]}), ('nflverse', {'start_season': 2025})]:
            with self.subTest(provider=provider, config=config):
                transport = RetainingFixtureTransport([])
                with self.assertRaises(ConnectorError) as error:
                    research.fetch(provider, config, None, transport, lambda: None)
                self.assertEqual(error.exception.code, 'INVALID_CONFIG')
                self.assertEqual(transport.calls, [])

    def test_statsbomb_redirect_provenance_native_row_and_no_assumed_utc(self):
        records, transport = self.fetch_stats()
        record = records[0]
        self.assertEqual(record['original'], MATCH)
        self.assertEqual(record['source_record_id'], '3857276')
        self.assertEqual(record['source_document_sha256'], transport.documents[1].sha256)
        self.assertEqual(record['attributes']['catalog_sha256'], transport.documents[0].sha256)
        self.assertIn('github.com/statsbomb/', record['attributes']['source_url'])
        self.assertIn('raw.githubusercontent.com/hudl/', record['attributes']['resolved_source_url'])
        self.assertEqual(record['source_local_time'], '15:00:00.000')
        self.assertIsNone(record['kickoff_utc'])
        self.assertEqual(record['status'], 'historical_result')
        self.assertEqual(record['odds'], [])
        self.assertTrue(all(headers is None and 'never-send' not in url for url, headers in transport.calls))

    def test_statsbomb_complete_selection_and_zero_score(self):
        rows = [deepcopy(MATCH) | {'match_id': 10000 + i, 'home_score': 0} for i in range(70)]
        records, transport = self.fetch_stats(rows)
        self.assertEqual(len(records), 70)
        self.assertEqual(records[-1]['source_record_id'], '10069')
        self.assertEqual(records[0]['score_home'], 0)
        self.assertEqual(len(transport.calls), 2)

    def test_statsbomb_only_source_supplied_offsets_become_utc(self):
        records, _ = self.fetch_stats([deepcopy(MATCH) | {'kick_off': '15:00:00+03:00'}])
        self.assertEqual(records[0]['kickoff_utc'], '2022-12-01T12:00:00Z')
        records, _ = self.fetch_stats([deepcopy(MATCH) | {'kick_off': None, 'home_score': None, 'away_score': None}])
        self.assertIsNone(records[0]['kickoff_utc'])
        self.assertIsNone(records[0]['score_home'])
        self.assertEqual(records[0]['status'], 'scheduled')

    def test_statsbomb_missing_coverage_does_not_fetch_guessed_path(self):
        transport = RetainingFixtureTransport([CATALOG])
        with self.assertRaises(ConnectorError) as error:
            research.fetch('statsbomb', {'competition_id': 99}, None, transport, lambda: None)
        self.assertEqual(error.exception.code, 'COVERAGE_UNAVAILABLE')
        self.assertEqual(len(transport.calls), 1)

    def test_statsbomb_rejects_mixed_identity_and_partial_scores(self):
        for patch, expected in [({'competition': {'competition_id': 99}}, 'IDENTITY_MISMATCH'),
                                ({'home_score': None}, 'INCOMPLETE_SCORE'),
                                ({'home_score': True}, 'SCHEMA_MISMATCH'),
                                ({'match_date': '2022-02-30'}, 'SCHEMA_MISMATCH')]:
            with self.subTest(patch=patch):
                with self.assertRaises(ConnectorError) as error:
                    self.fetch_stats([deepcopy(MATCH) | patch])
                self.assertEqual(error.exception.code, expected)

    def test_statsbomb_duplicate_and_conflicting_records(self):
        records, _ = self.fetch_stats([deepcopy(MATCH), deepcopy(MATCH)])
        self.assertEqual(len(records), 1)
        with self.assertRaises(ConnectorError) as error:
            self.fetch_stats([deepcopy(MATCH), deepcopy(MATCH) | {'home_score': 9}])
        self.assertEqual(error.exception.code, 'DUPLICATE_CONFLICT')

    def test_malformed_statsbomb_is_rejected_after_retention(self):
        for payload, code in [(b'not json', 'INVALID_JSON'), ({'unexpected': []}, 'SCHEMA_MISMATCH'), ([7], 'SCHEMA_MISMATCH')]:
            transport = RetainingFixtureTransport([payload])
            with self.assertRaises(ConnectorError) as error:
                research.fetch('statsbomb', {}, None, transport, lambda: None)
            self.assertEqual(error.exception.code, code)
            self.assertEqual(len(transport.documents), 1)

    def test_cancellation_between_catalog_and_match_fetch(self):
        calls = []
        def check():
            calls.append(1)
            if len(calls) == 2:
                raise ConnectorError('JOB_CANCELLED', 'The operation was cancelled.')
        transport = RetainingFixtureTransport([CATALOG, [MATCH]])
        with self.assertRaises(ConnectorError) as error:
            research.fetch('statsbomb', {}, None, transport, check)
        self.assertEqual(error.exception.code, 'JOB_CANCELLED')
        self.assertEqual(len(transport.calls), 1)

    def test_transport_quota_error_is_not_misrepresented(self):
        transport = RetainingFixtureTransport([ConnectorError('RATE_LIMITED', 'Provider quota exhausted.', retry_after=120, http_status=429)])
        with self.assertRaises(ConnectorError) as error:
            research.fetch('nflverse', {}, None, transport, lambda: None)
        self.assertEqual(error.exception.retry_after, 120)
        self.assertEqual(error.exception.http_status, 429)

    def test_nfl_complete_season_is_not_truncated(self):
        rows = [NFL_ROW | {'game_id': f'2025_01_A{i:03}_H{i:03}', 'away_team': f'A{i:03}', 'home_team': f'H{i:03}'} for i in range(300)]
        records, transport = self.fetch_nfl(rows)
        self.assertEqual(len(records), 300)
        self.assertEqual(records[-1]['source_record_id'], '2025_01_A299_H299')
        self.assertEqual(len(transport.calls), 1)
        self.assertEqual(records[0]['sport'], 'american_football')
        self.assertEqual(records[0]['attributes']['score_units'], 'points')
        self.assertEqual(records[0]['source_document_sha256'], transport.documents[0].sha256)

    def test_nfl_documented_eastern_dst_and_january_season(self):
        rows = [NFL_ROW,
                NFL_ROW | {'game_id': '2025_19_DAL_PHI', 'gameday': '2026-01-04', 'game_type': 'WC', 'week': '19'},
                NFL_ROW | {'game_id': '2024_01_DAL_PHI', 'season': '2024', 'gameday': '2024-09-04'}]
        records, _ = self.fetch_nfl(rows)
        self.assertEqual(len(records), 2)
        self.assertEqual(records[0]['kickoff_utc'], '2025-09-05T00:20:00Z')
        self.assertEqual(records[1]['kickoff_utc'], '2026-01-05T01:20:00Z')
        self.assertEqual(records[1]['season'], '2025')
        self.assertEqual(records[1]['event_date'], '2026-01-04')

    def test_nfl_ambiguous_nonexistent_and_missing_times_remain_unknown(self):
        for day, clock, precision in [('2025-11-02', '01:30', 'ambiguous_eastern_time'),
                                      ('2025-03-09', '02:30', 'nonexistent_eastern_time'),
                                      ('2025-09-04', '', 'date_only')]:
            with self.subTest(day=day):
                records, _ = self.fetch_nfl([NFL_ROW | {'gameday': day, 'gametime': clock}])
                self.assertIsNone(records[0]['kickoff_utc'])
                self.assertEqual(records[0]['attributes']['time_precision'], precision)

    def test_nfl_missing_points_not_zero_and_archival_odds_not_tradable(self):
        records, _ = self.fetch_nfl([NFL_ROW | {'away_score': '', 'home_score': ''}])
        self.assertEqual(records[0]['status'], 'scheduled')
        self.assertIsNone(records[0]['score_home'])
        self.assertEqual(records[0]['statistics']['temp'], 0)
        self.assertEqual(records[0]['statistics']['wind'], 0)
        self.assertEqual(records[0]['attributes']['archival_betting_columns']['home_moneyline'], '-110')
        self.assertEqual(records[0]['odds'], [])

    def test_nfl_partial_score_identity_and_date_errors_are_typed(self):
        for patch, expected in [({'away_score': ''}, 'INCOMPLETE_SCORE'), ({'home_team': 'KC'}, 'IDENTITY_MISMATCH'),
                                ({'gameday': 'tomorrow'}, 'SCHEMA_MISMATCH'), ({'home_score': '-3'}, 'SCHEMA_MISMATCH')]:
            with self.subTest(patch=patch):
                with self.assertRaises(ConnectorError) as error:
                    self.fetch_nfl([NFL_ROW | patch])
                self.assertEqual(error.exception.code, expected)

    def test_nfl_duplicate_and_conflict_rows(self):
        records, _ = self.fetch_nfl([NFL_ROW, NFL_ROW])
        self.assertEqual(len(records), 1)
        with self.assertRaises(ConnectorError) as error:
            self.fetch_nfl([NFL_ROW, NFL_ROW | {'home_score': '25'}])
        self.assertEqual(error.exception.code, 'DUPLICATE_CONFLICT')

    def test_nfl_csv_header_and_truncated_rows(self):
        for body in [b'<html>failure</html>', b'game_id,season,season\n1,2025,2025\n',
                     (','.join(NFL_FIELDS) + '\n2025_01_DAL_PHI,2025,REG,1,2025-09-04,20:20,DAL,20,PHI,24\n').encode()]:
            with self.subTest(body=body[:40]):
                with self.assertRaises(ConnectorError) as error:
                    self.fetch_nfl(body=body)
                self.assertEqual(error.exception.code, 'SCHEMA_MISMATCH')

    def test_nfl_no_selected_coverage_is_distinct_from_success(self):
        with self.assertRaises(ConnectorError) as error:
            self.fetch_nfl(config={'season': 2000})
        self.assertEqual(error.exception.code, 'COVERAGE_UNAVAILABLE')

    def test_response_bound_and_no_live_claim(self):
        transport = RetainingFixtureTransport([b'x' * (research.MAX_DOCUMENT_BYTES + 1)])
        with self.assertRaises(ConnectorError) as error:
            research.fetch('statsbomb', {}, None, transport, lambda: None)
        self.assertEqual(error.exception.code, 'DATA_LIMIT')
        self.assertTrue(all(not spec['live'] for spec in research.SPECS.values()))
        self.assertNotIn('lineups', research.SPECS['statsbomb']['capabilities'])


if __name__ == '__main__':
    unittest.main()
