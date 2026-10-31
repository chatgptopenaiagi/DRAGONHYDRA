"""Exercise real connection jobs and source-scoped browsing against one server.

No server lifecycle operations or provider-response mocks. Missing credentials
provide the natural failure case. EventSource error/open dispatch, when enabled,
tests display handlers only and never claims a real network reconnection.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import re
import sys
import time
import traceback
from urllib.parse import urlsplit
from zipfile import ZipFile

from playwright.sync_api import sync_playwright, expect


ROOT = Path(__file__).resolve().parents[2]
API = '/dragon/api/v1'
EXPECTED = {'openfootball': 760, 'football-data-couk': 380, 'statsbomb': 64,
            'nflverse': 285, 'moneypuck': 1394, 'cricsheet': 17}
SPORTS = {'nflverse': 'american_football', 'moneypuck': 'ice_hockey', 'cricsheet': 'cricket'}


def run():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', required=True)
    parser.add_argument('--state', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if sys.flags.optimize:
        raise RuntimeError('Run this verification with assertions enabled.')
    origin = args.url.rstrip('/')
    parsed = urlsplit(origin)
    assert parsed.scheme == 'http' and parsed.hostname == '127.0.0.1' and not parsed.username and not parsed.password
    assert parsed.path in ('', '/') and not parsed.query and not parsed.fragment
    state, output = args.state.resolve(), args.output.resolve()
    assert state.is_relative_to(ROOT) and output.is_relative_to(ROOT)
    assert output.is_relative_to(ROOT / 'build/connections/evidence') or output.is_relative_to(ROOT / 'runtime/evidence')
    assert not (output / 'journey.json').exists(), 'Use a new evidence directory to preserve earlier results.'
    output.mkdir(parents=True, exist_ok=True)
    session = state / 'client/local-session.json'
    if not session.exists():
        session = state / 'local-session.json'
    token = json.loads(session.read_text(encoding='utf-8-sig'))['token']
    assert isinstance(token, str) and len(token) >= 20

    def safe(value):
        return str(value).replace(token, '[REDACTED]')

    groups, page_errors, console_errors, response_errors = [], [], [], []
    record = {'schema_version': 1, 'started_at': datetime.now(timezone.utc).isoformat(),
              'passed': False, 'url': origin, 'groups': groups, 'expected_import_counts': EXPECTED,
              'browser': 'Installed Microsoft Edge / Playwright',
              'environment': {'os': platform.platform(), 'architecture': platform.machine(), 'python': platform.python_version()},
              'scope': 'Browser interactions against real source server and persisted provider data; no packaged/native or clean-machine claim',
              'page_errors': page_errors, 'console_errors': console_errors, 'http_errors': response_errors,
              'not_run': ['Native packaged-client interaction', 'Real network outage/reconnection', 'Live account import', 'LLM inference']}

    def passed(name, **details):
        groups.append({'name': name, 'passed': True, **details})
        print(json.dumps({'passed': name}), flush=True)

    def monitor(target):
        target.on('pageerror', lambda exc: page_errors.append(safe(exc)))
        target.on('console', lambda message: console_errors.append({'text': safe(message.text), 'location': message.location}) if message.type == 'error' else None)
        target.on('response', lambda response: response_errors.append({'url': safe(response.url), 'status': response.status}) if response.status >= 400 else None)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel='msedge', headless=True)
        context = browser.new_context(viewport={'width': 1500, 'height': 1100}, reduced_motion='reduce', accept_downloads=True)
        context.on('page', monitor)
        page = context.new_page()

        def api(path):
            response = context.request.get(origin + API + path, timeout=15000)
            assert response.status == 200, f'API GET returned {response.status}'
            return response.json()

        def card(provider):
            return page.locator('[data-provider="' + provider + '"]')

        def open_connections():
            page.get_by_role('link', name='Connections', exact=True).click()
            expect(page.get_by_role('heading', name='Connections', exact=True)).to_be_visible()
            expect(card('statsbomb')).to_be_visible()

        def wait_job(identifier, terminal='succeeded'):
            deadline = time.monotonic() + 150
            while time.monotonic() < deadline:
                row = api('/jobs/' + identifier)
                if row['status'] in ('succeeded', 'failed', 'cancelled', 'interrupted'):
                    assert row['status'] == terminal, safe(row.get('error'))
                    return row
                time.sleep(.25)
            raise AssertionError('The real provider job did not reach its expected terminal state before deadline.')

        def connection_action(provider, action, button, terminal='succeeded'):
            path = origin + API + '/connections/' + provider + '/' + action
            with page.expect_response(lambda response: response.url == path and response.request.method == 'POST', timeout=30000) as created:
                card(provider).get_by_role('button', name=button, exact=True).click()
            response = created.value
            assert response.status == 202
            identifier = response.json()['id']
            row = wait_job(identifier, terminal)
            if terminal == 'succeeded':
                expect(card(provider).locator('.badge').first).to_have_text('Working', timeout=30000)
                expect(page.locator('.job-progress')).to_have_count(0, timeout=30000)
                expect(card(provider)).to_contain_text(str(EXPECTED[provider]) + ' stored records')
            else:
                expect(card(provider).locator('.connection-proof')).to_contain_text('NEEDS_KEY', timeout=30000)
                expect(card(provider).locator('.badge').first).to_have_text('Needs key')
                expect(page.get_by_text('Job needs attention', exact=True)).to_be_visible()
            return row

        try:
            page.goto(origin + '/#token=' + token, wait_until='domcontentloaded')
            expect(page.get_by_role('heading', name='Today’s football')).to_be_visible(timeout=30000)
            assert '#token=' not in page.url
            page.wait_for_function('typeof state !== "undefined" && state.stream && state.stream.readyState === EventSource.OPEN', timeout=30000)
            expect(page.locator('#footer-status')).to_contain_text(re.compile('Update stream connected|New committed data available'), timeout=15000)
            passed('Authenticated pairing removes token fragment and actual EventSource connection opens')

            open_connections()
            connections = {row['id']: row for row in api('/connections')['items']}
            summaries = []
            for provider, count in EXPECTED.items():
                current = connections[provider]
                assert current['implemented'] and current['record_count'] == count
                if provider != 'openfootball':
                    assert current['status'] == 'working' and current['quarantined_count'] == 0
                    expect(card(provider).locator('.badge').first).to_have_text('Working')
                    assert current['last_import'] and current['last_successful_retrieval']
                expect(card(provider)).to_contain_text(str(count) + ' stored records')
                summaries.append({'provider': provider, 'record_count': count, 'status': current['status']})
            page.screenshot(path=str(output / 'connections-working.png'), full_page=True)
            passed('All public cards show actual configured imports and five new sources Working', sources=summaries)

            checked = connection_action('statsbomb', 'test', 'Test connection')
            assert checked['result']['operation'] == 'test'
            assert checked['result']['retrieved_rows'] == 64 and checked['result']['normalized_rows'] == 64
            assert checked['result']['record_count'] == 64
            assert api('/connections/statsbomb/attempts')['items'][0]['job_id'] == checked['id']
            passed('StatsBomb Test connection runs a real queued retrieval with 64 normalized rows', job_id=checked['id'])

            synchronized = connection_action('football-data-couk', 'sync', 'Sync now')
            assert synchronized['result']['operation'] == 'sync'
            assert synchronized['result']['record_count'] == 380 and synchronized['result']['retrieved_rows'] == 380
            assert synchronized['result']['inserted'] == 0 and synchronized['result']['unchanged'] == 380
            passed('FootballData Sync now performs real retrieval while retaining 380 stable records', job_id=synchronized['id'], inserted=0, unchanged=380)

            source = api('/connections/statsbomb/records?limit=100&offset=0')
            assert source['total'] == 64
            first = source['items'][0]
            selected = first['record']
            assert selected['sport'] == 'football' and first['match_id']
            card('statsbomb').get_by_role('button', name='Open imported data', exact=True).click()
            expect(page.get_by_role('heading', name=connections['statsbomb']['name'], exact=True)).to_be_visible()
            expect(page.get_by_role('table')).to_be_visible()
            expect(page.get_by_text('64 retained source records.', exact=False)).to_be_visible()
            participants = selected['home'] + ' vs ' + selected['away']
            page.get_by_role('button', name=participants, exact=True).click()
            expect(page.get_by_role('heading', name='Match overview', exact=True)).to_be_visible()
            match_id = first['match_id']
            match_url = page.url
            assert match_url.endswith('/#match/' + match_id)
            match = api('/matches/' + match_id)
            assert match['source_id'] == 'statsbomb'
            page.locator('.team-button').first.click()
            expect(page.get_by_role('heading', name=selected['home'], exact=True)).to_be_visible()
            expect(page.get_by_role('heading', name='Recent form', exact=True)).to_be_visible()
            page.get_by_role('button', name='← Return to selected match').click()
            expect(page.get_by_role('heading', name='Match overview', exact=True)).to_be_visible()
            assert page.url == match_url
            page.get_by_role('button', name='Open standings', exact=True).click()
            tournament = api('/competitions/' + match['competition_id'] + '/standings')
            assert tournament['available'] is False and tournament['items'] == [] and tournament['stages']
            expect(page.get_by_text('UNAVAILABLE', exact=True)).to_be_visible()
            expect(page.locator('#main')).to_contain_text('Tournament stages; a single league table is not applicable')
            expect(page.get_by_role('table')).to_have_count(0)
            for stage in tournament['stages']:
                expect(page.locator('#main')).to_contain_text(stage)
            page.get_by_role('button', name='← Return to selected match').click()
            expect(page.get_by_role('heading', name='Match overview', exact=True)).to_be_visible()
            assert page.url == match_url
            passed('StatsBomb match and team retain context; tournament standings explicitly abstain from an invented combined table',
                   canonical_match_id=match_id, participants=participants, available_stages=tournament['stages'])

            page.get_by_role('tab', name='Analysis', exact=True).click()
            expect(page.get_by_role('heading', name='Model probabilities', exact=True)).to_be_visible()
            forecast = api('/matches/' + match_id + '/predictions')
            if match['status'] == 'finished':
                assert forecast['available'] is False
                expect(page.get_by_text(forecast['reason'], exact=False)).to_be_visible()
            page.get_by_role('button', name='Explain this match', exact=True).click()
            expect(page.get_by_text('DETERMINISTIC EVIDENCE SUMMARY', exact=True)).to_be_visible(timeout=120000)
            with context.expect_page() as opened:
                page.locator('.explanation-citation').first.click()
            evidence_page = opened.value
            evidence_page.wait_for_url(re.compile(re.escape(origin) + API + r'/evidence/.+'), wait_until='domcontentloaded')
            evidence = json.loads(evidence_page.locator('body').inner_text())
            evidence_id = evidence.get('evidence_id') or evidence.get('id')
            assert evidence_id and (evidence.get('source_id') or evidence.get('provider')) == 'statsbomb'
            assert evidence['record']['source_record_id'] == selected['source_record_id']
            evidence_page.close()
            page.screenshot(path=str(output / 'statsbomb-analysis.png'), full_page=True)
            passed('Evidence-linked analysis is explicitly deterministic and opens the exact StatsBomb source record', evidence_id=evidence_id, llm_generated=False)

            page.get_by_role('tab', name='Overview', exact=True).click()
            page.get_by_role('button', name='Export to Excel', exact=True).click()
            expect(page.get_by_text('Report ready', exact=True)).to_be_visible(timeout=120000)
            with page.expect_download() as captured:
                page.get_by_role('link', name='Download Excel report', exact=True).click()
            workbook = output / 'statsbomb-match.xlsx'
            captured.value.save_as(str(workbook))
            with ZipFile(workbook) as archive:
                assert '[Content_Types].xml' in archive.namelist()
                assert b'name="Match"' in archive.read('xl/workbook.xml')
                assert b'name="Metadata"' in archive.read('xl/workbook.xml')
                assert match_id.encode() in archive.read('xl/worksheets/sheet1.xml')
            passed('StatsBomb Export to Excel downloads an actual same-match workbook', filename=workbook.name,
                   bytes=workbook.stat().st_size, sha256=hashlib.sha256(workbook.read_bytes()).hexdigest())

            # A tournament's unsupported combined table must not hide the real
            # league-table path. Exercise the separate, source-scoped EPL cohort.
            open_connections()
            league_source = api('/connections/football-data-couk/records?limit=100&offset=0')
            league_item = league_source['items'][0]
            league_record = league_item['record']
            card('football-data-couk').get_by_role('button', name='Open imported data', exact=True).click()
            expect(page.get_by_role('heading', name=connections['football-data-couk']['name'], exact=True)).to_be_visible()
            page.get_by_role('button', name=league_record['home'] + ' vs ' + league_record['away'], exact=True).click()
            expect(page.get_by_role('heading', name='Match overview', exact=True)).to_be_visible()
            league_url = page.url
            league_match = api('/matches/' + league_item['match_id'])
            page.get_by_role('button', name='Open standings', exact=True).click()
            league = api('/competitions/' + league_match['competition_id'] + '/standings')
            assert league.get('available', True) and league['official'] is False
            assert league['source_id'] == 'football-data-couk' and len(league['items']) == 20
            expect(page.get_by_text('RECONSTRUCTED', exact=True)).to_be_visible()
            expect(page.get_by_role('table').locator('tbody tr')).to_have_count(20)
            expect(page.get_by_role('columnheader', name='Pts', exact=True)).to_be_visible()
            page.screenshot(path=str(output / 'league-standings.png'), full_page=True)
            page.get_by_role('button', name='← Return to selected match').click()
            expect(page.get_by_role('heading', name='Match overview', exact=True)).to_be_visible()
            assert page.url == league_url
            passed('FootballData league opens an actual 20-team reconstructed table and returns to the same event',
                   canonical_match_id=league_item['match_id'], teams=20, official=False)

            for provider, sport in SPORTS.items():
                open_connections()
                source = api('/connections/' + provider + '/records?limit=100&offset=0')
                assert source['total'] == EXPECTED[provider]
                item = source['items'][0]
                native = item['record']
                assert native['sport'] == sport and 'match_id' not in item
                card(provider).get_by_role('button', name='Open imported data', exact=True).click()
                expect(page.get_by_role('heading', name=connections[provider]['name'], exact=True)).to_be_visible()
                first_row = page.get_by_role('table').locator('tbody tr').first
                expect(first_row).to_contain_text(sport)
                expect(first_row).to_contain_text(native['home'] + ' vs ' + native['away'])
                expect(first_row.get_by_role('button')).to_have_count(0)
                with context.expect_page() as opened:
                    first_row.get_by_role('link', name='Source record', exact=True).click()
                cited = opened.value
                cited.wait_for_url(re.compile(re.escape(origin) + API + r'/evidence/.+'), wait_until='domcontentloaded')
                factual = json.loads(cited.locator('body').inner_text())
                assert factual['record']['sport'] == sport and (factual.get('source_id') or factual.get('provider')) == provider
                assert factual['record']['source_record_id'] == native['source_record_id']
                cited.close()
                page.screenshot(path=str(output / (provider + '-participants.png')), full_page=True)
                passed('Source participants and evidence preserve ' + provider + ' sport without football navigation',
                       provider=provider, sport=sport, record_count=source['total'], source_record_id=native['source_record_id'])

            open_connections()
            missing = connection_action('api-football', 'test', 'Test connection', terminal='failed')
            assert missing['error']['code'] == 'NEEDS_KEY'
            latest = {row['id']: row for row in api('/connections')['items']}
            assert latest['api-football']['status'] == 'needs_key' and not latest['api-football']['credential_configured']
            assert latest['api-football']['record_count'] == 0
            page.screenshot(path=str(output / 'connections-needs-key.png'), full_page=True)
            passed('Missing-key Test connection shows actionable NEEDS_KEY and never claims Working', job_id=missing['id'])

            page.wait_for_function('state.stream.readyState === EventSource.OPEN', timeout=15000)
            expect(page.locator('#footer-status')).to_contain_text(re.compile('Update stream connected|New committed data available'))
            # Explicitly scoped handler tests. The browser's real SSE transport
            # stays OPEN; this does not establish recovery from a network outage.
            page.evaluate('state.stream.dispatchEvent(new Event("error"))')
            expect(page.locator('#footer-status')).to_have_text('Update stream reconnecting. Manual refresh remains available.')
            page.evaluate('state.stream.dispatchEvent(new Event("open"))')
            expect(page.locator('#footer-status')).to_have_text('Update stream connected. Committed changes are available on refresh.')
            assert page.evaluate('state.stream.readyState === EventSource.OPEN')
            passed('Connected update stream and explicit error/open display handlers recover footer',
                   actual_sse_open=True, synthetic_handler_dispatch=True, network_reconnection_verified=False)
            assert not page_errors, safe(page_errors)
            assert not console_errors, safe(console_errors)
            assert not response_errors, safe(response_errors)
            record['passed'] = True
        except Exception as exc:
            record['error'] = safe(f'{type(exc).__name__}: {exc}')
            record['traceback'] = safe(traceback.format_exc())
            try:
                page.locator('input[type=password]').evaluate_all("nodes => nodes.forEach(node => node.value = '')")
                page.screenshot(path=str(output / 'failure.png'), full_page=True)
            except Exception as capture:
                record['capture_error'] = safe(capture)
        finally:
            record['finished_at'] = datetime.now(timezone.utc).isoformat()
            record['unique_group_count'] = len(groups)
            record['server_lifecycle_operations'] = False
            context.close()
            browser.close()
            (output / 'journey.json').write_text(safe(json.dumps(record, indent=2, ensure_ascii=False)), encoding='utf-8')
    print(json.dumps({'passed': record['passed'], 'groups': len(groups), 'error': record.get('error'),
                      'evidence': str(output / 'journey.json')}, indent=2))
    return 0 if record['passed'] else 1


if __name__ == '__main__':
    sys.exit(run())
