"""Captured-schema-shaped synthetic fixtures; no network or product-state writes."""
import copy
import csv
import gzip
import hashlib
import io
import json
from pathlib import Path
import stat
import struct
import unittest
from unittest.mock import patch
import warnings
import zipfile

from dragonhydra.connectors import multisport
from dragonhydra.connectors.core import ConnectorError, Document

FIXTURES = Path(__file__).parent / 'fixtures/connectors/multisport'


def document(body, url='https://cricsheet.org/downloads/blz_json.zip'):
    return Document(url, url, body, '2026-10-31T12:00:00Z', hashlib.sha256(body).hexdigest())


def source_rows():
    return list(csv.DictReader(io.StringIO((FIXTURES / 'moneypuck.csv').read_text())))


def hockey(rows=None, compressed=False):
    rows = source_rows() if rows is None else rows
    output = io.StringIO(newline='')
    writer = csv.DictWriter(output, fieldnames=list(source_rows()[0]))
    writer.writeheader(); writer.writerows(rows)
    raw = output.getvalue().encode()
    return document(gzip.compress(raw, mtime=0) if compressed else raw, multisport.MONEYPUCK_URL)


def cricket_native():
    return json.loads((FIXTURES / 'cricsheet.json').read_text())


def cricket(entries=None):
    entries = [('wi_synthetic_001.json', json.dumps(cricket_native()).encode()), ('README.txt', b'Synthetic test only')]
    return zip_document(entries)


def zip_document(entries):
    buffer = io.BytesIO()
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', UserWarning)
        with zipfile.ZipFile(buffer, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
            for name, raw in entries:
                archive.writestr(name, raw)
    return document(buffer.getvalue())


class MultisportConnectorTests(unittest.TestCase):
    def assert_code(self, code, function, *args):
        with self.assertRaises(ConnectorError) as failure:
            function(*args)
        self.assertEqual(failure.exception.code, code)

    def test_historical_capabilities_and_strict_configuration(self):
        self.assertFalse(multisport.SPECS['cricsheet']['live'])
        self.assertFalse(multisport.SPECS['moneypuck']['live'])
        self.assertEqual(multisport.validate_config('moneypuck', {'season': '2025'})['season'], 2025)
        for config in ({'url': 'https://example.test/private'}, {'season': True}, {'season_type': 'live'}):
            self.assert_code('INVALID_CONFIG', multisport.validate_config, 'moneypuck', config)
        self.assert_code('INVALID_CONFIG', multisport.validate_config, 'cricsheet', {'dataset': '../../all'})
        self.assert_code('INVALID_CONFIG', multisport.validate_config, 'cricsheet', {'dataset': ['blz']})
        self.assert_code('UNSUPPORTED_PROVIDER', multisport.validate_config, 'other', {})

    def test_hockey_pairs_same_game_and_keeps_original_provenance(self):
        doc = hockey(compressed=True)
        rows = multisport.parse_moneypuck(doc, {})
        self.assertEqual(len(rows), 2)
        game = rows[0]
        self.assertEqual((game['home'], game['away'], game['score_home'], game['score_away']), ('HOM', 'AWY', 3, 2))
        self.assertEqual(game['source_record_id'], '2025020001')
        self.assertEqual(game['source_document_sha256'], hashlib.sha256(doc.body).hexdigest())
        self.assertTrue(game['attributes']['transport_gzip'])
        self.assertTrue(game['attributes']['paired_team_rows'])
        self.assertEqual(game['original']['team_rows']['HOME']['goalsFor'], '3.0')
        self.assertIsNone(game['kickoff_utc'])
        self.assertIsNone(game['source_local_time'])
        self.assertIn('shootout', game['attributes']['score_scope'])
        self.assertEqual(game['odds'], [])

    def test_hockey_full_selection_and_playoffs_filter(self):
        self.assertEqual(len(multisport.parse_moneypuck(hockey(), {'season_type': 'regular'})), 1)
        playoff = multisport.parse_moneypuck(hockey(), {'season_type': 'playoffs'})
        self.assertEqual(len(playoff), 1)
        self.assertEqual(playoff[0]['score_home'], 0)
        self.assertEqual(multisport.parse_moneypuck(hockey(), {'season': 2024}), [])

    def test_hockey_single_native_row_resolves_explicit_opponent(self):
        item = multisport.parse_moneypuck(hockey([source_rows()[1]]), {})[0]
        self.assertEqual((item['home'], item['away'], item['score_home'], item['score_away']), ('HOM', 'AWY', 3, 2))
        self.assertFalse(item['attributes']['paired_team_rows'])

    def test_hockey_duplicate_rows_are_idempotent_but_conflicts_quarantined(self):
        rows = source_rows()[:2]
        self.assertEqual(len(multisport.parse_moneypuck(hockey(rows + [rows[0]]), {})), 1)
        conflicting = dict(rows[0], goalsFor='9.0')
        self.assert_code('AMBIGUOUS_IDENTITY', multisport.parse_moneypuck, hockey(rows + [conflicting]), {})

    def test_hockey_identity_and_score_disagreement_are_rejected(self):
        rows = source_rows()[:2]
        for change in ({'opposingTeam': 'OTH'}, {'gameDate': '20251002'}):
            with self.subTest(change=change):
                self.assert_code('AMBIGUOUS_IDENTITY', multisport.parse_moneypuck, hockey([rows[0], dict(rows[1], **change)]), {})
        self.assert_code('INCONSISTENT_SCORE', multisport.parse_moneypuck, hockey([rows[0], dict(rows[1], goalsAgainst='8.0')]), {})

    def test_hockey_missing_goals_are_not_zero(self):
        rows = [dict(row, goalsFor='', goalsAgainst='') for row in source_rows()[:2]]
        item = multisport.parse_moneypuck(hockey(rows), {})[0]
        self.assertIsNone(item['score_home']); self.assertIsNone(item['score_away'])

    def test_hockey_invalid_content_and_expansion_are_bounded(self):
        self.assert_code('UNEXPECTED_HTML', multisport.parse_moneypuck, document(b'<html>Blocked</html>'), {})
        self.assert_code('SCHEMA_MISMATCH', multisport.parse_moneypuck, document(b'name,value\nA,B\n'), {})
        self.assert_code('INVALID_CSV', multisport.parse_moneypuck, document(b'\x1f\x8bbroken'), {})
        with patch.object(multisport, 'MAX_CSV_BYTES', 20):
            self.assert_code('DECOMPRESSION_LIMIT', multisport.parse_moneypuck, hockey(compressed=True), {})

    def test_hockey_invalid_dates_counts_and_roles(self):
        for change, code in [({'gameDate': '20250230'}, 'SCHEMA_MISMATCH'),
                             ({'goalsFor': 'NaN'}, 'SCHEMA_MISMATCH'),
                             ({'goalsFor': '2.5'}, 'SCHEMA_MISMATCH'),
                             ({'home_or_away': 'NEUTRAL'}, 'AMBIGUOUS_IDENTITY'),
                             ({'goalsFor': '1e100000000'}, 'SCHEMA_MISMATCH')]:
            with self.subTest(change=change):
                self.assert_code(code, multisport.parse_moneypuck, hockey([dict(source_rows()[0], **change)]), {})

    def test_cricket_preserves_innings_source_order_and_archive_provenance(self):
        doc = cricket(); items = multisport.parse_cricsheet(doc, {})
        self.assertEqual(len(items), 1)
        item = items[0]
        self.assertEqual(item['source_record_id'], 'wi_synthetic_001')
        self.assertEqual(item['source_document_sha256'], doc.sha256)
        self.assertEqual(item['home'], 'Example Island Red')
        self.assertFalse(item['attributes']['home_away_designation_provided'])
        self.assertEqual(item['attributes']['participant_order'], 'source_order')
        self.assertIsNone(item['score_home']); self.assertIsNone(item['score_away'])
        self.assertEqual(item['statistics']['innings'][0]['runs_total'], 10)
        self.assertEqual(item['statistics']['innings'][0]['wicket_event_kinds']['retired hurt'], 1)
        self.assertNotIn('wickets_lost', item['statistics']['innings'][0])
        self.assertTrue(item['statistics']['innings'][1]['super_over'])
        self.assertIsNone(item['kickoff_utc']); self.assertIsNone(item['source_local_time'])

    def test_cricket_processes_entire_selected_archive_not_first_match(self):
        data = json.dumps(cricket_native()).encode()
        items = multisport.parse_cricsheet(zip_document([('1001.json', data), ('wi_1002.json', data)]), {})
        self.assertEqual([item['source_record_id'] for item in items], ['1001', 'wi_1002'])

    def test_cricket_supported_versions_and_multiday_precision(self):
        for version in ('1.0.0', '1.1.0', '1.2.0', '1.3.0'):
            native = cricket_native(); native['meta']['data_version'] = version
            native['info']['dates'] = ['2025-10-01', '2025-10-02']
            item = multisport.parse_cricsheet(zip_document([('1.json', json.dumps(native).encode())]), {})[0]
            self.assertEqual(item['event_date'], '2025-10-01')
            self.assertEqual(len(item['attributes']['event_dates']), 2)
            self.assertEqual(item['attributes']['format_version'], version)
        native['meta']['data_version'] = '2.0.0'
        self.assert_code('SCHEMA_VERSION_UNSUPPORTED', multisport.parse_cricsheet, zip_document([('1.json', json.dumps(native).encode())]), {})

    def test_cricket_archive_paths_duplicates_and_symlinks_rejected(self):
        raw = json.dumps(cricket_native()).encode()
        for name in ('../1.json', '/1.json', 'folder/1.json', 'C:/1.json', 'C:\\1.json', 'tool.exe'):
            with self.subTest(name=name):
                self.assert_code('ARCHIVE_UNSAFE', multisport.parse_cricsheet, zip_document([(name, raw)]), {})
        self.assert_code('ARCHIVE_UNSAFE', multisport.parse_cricsheet, zip_document([('1.json', raw), ('1.json', raw)]), {})
        link = zipfile.ZipInfo('1.json'); link.create_system = 3; link.external_attr = (stat.S_IFLNK | 0o777) << 16
        self.assert_code('ARCHIVE_UNSAFE', multisport.parse_cricsheet, zip_document([(link, b'target')]), {})

    def test_cricket_archive_size_and_member_limits(self):
        doc = cricket()
        with patch.object(multisport, 'MAX_ZIP_MEMBERS', 1):
            self.assert_code('ARCHIVE_LIMIT', multisport.parse_cricsheet, doc, {})
        with patch.object(multisport, 'MAX_ZIP_BYTES', 20):
            self.assert_code('ARCHIVE_LIMIT', multisport.parse_cricsheet, doc, {})
        with patch.object(multisport, 'MAX_MEMBER_BYTES', 20):
            self.assert_code('ARCHIVE_UNSAFE', multisport.parse_cricsheet, doc, {})

    def test_cricket_archive_encryption_flag_rejected_before_read(self):
        body = bytearray(zip_document([('1.json', b'{}')]).body)
        local = body.index(b'PK\x03\x04'); central = body.index(b'PK\x01\x02')
        struct.pack_into('<H', body, local + 6, 1); struct.pack_into('<H', body, central + 8, 1)
        self.assert_code('ARCHIVE_UNSAFE', multisport.parse_cricsheet, document(bytes(body)), {})

    def test_cricket_invalid_zip_json_and_no_records(self):
        self.assert_code('ARCHIVE_INVALID', multisport.parse_cricsheet, document(b'<html>unavailable</html>'), {})
        self.assert_code('INVALID_JSON', multisport.parse_cricsheet, zip_document([('1.json', b'{bad')]), {})
        self.assert_code('NO_RECORDS', multisport.parse_cricsheet, zip_document([('README.txt', b'No matches')]), {})

    def test_cricket_ambiguous_match_and_invalid_innings_rejected(self):
        for change in ('same_team', 'winner', 'date', 'innings_team', 'missing_runs'):
            native = cricket_native()
            if change == 'same_team': native['info']['teams'][1] = native['info']['teams'][0]
            elif change == 'winner': native['info']['outcome']['winner'] = 'Unrelated XI'
            elif change == 'date': native['info']['dates'] = ['2025-02-30']
            elif change == 'innings_team': native['innings'][0]['team'] = 'Unrelated XI'
            else: del native['innings'][0]['overs'][0]['deliveries'][0]['runs']['total']
            with self.subTest(change=change), self.assertRaises(ConnectorError):
                multisport.parse_cricsheet(zip_document([('1.json', json.dumps(native).encode())]), {})

    def test_fetch_fixed_endpoints_headers_and_no_credentials(self):
        class FakeTransport:
            def __init__(self): self.calls = []
            def get(self, url, headers=None):
                self.calls.append((url, headers))
                return hockey(compressed=True) if 'moneypuck' in url else cricket()
        transport = FakeTransport()
        self.assertEqual(len(multisport.fetch('moneypuck', {}, 'unused-secret', transport, lambda: None)), 2)
        self.assertEqual(transport.calls[0], (multisport.MONEYPUCK_URL, {'Accept-Encoding': 'gzip'}))
        self.assertEqual(len(multisport.fetch('cricsheet', {}, None, transport, lambda: None)), 1)
        self.assertEqual(transport.calls[1][0], 'https://cricsheet.org/downloads/blz_json.zip')

    def test_cancellation_is_not_mislabeled_as_source_error(self):
        class Cancelled(Exception): pass
        def cancel(): raise Cancelled('Owned job cancellation')
        with self.assertRaises(Cancelled): multisport.parse_moneypuck(hockey(), {}, cancel)
        with self.assertRaises(Cancelled): multisport.parse_cricsheet(cricket(), {}, cancel)
        with self.assertRaises(Cancelled): multisport.fetch('cricsheet', {}, None, None, cancel)


if __name__ == '__main__': unittest.main()
