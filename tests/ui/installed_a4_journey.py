"""Exercise retained-data controls on the already installed A4 workstation.

No provider fetch, imports, service restart, configuration changes, or mocked
model replies. Only explanation/export jobs write new application records.
This is a browser check, not native WebView or clean-machine evidence.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys
import traceback
from urllib.parse import urlsplit
import zipfile

from openpyxl import load_workbook
from playwright.sync_api import expect, sync_playwright


ROOT = Path(__file__).resolve().parents[2]
API = '/dragon/api/v1'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    state, output = args.state.resolve(), args.output.resolve()
    expected_state = ROOT / 'build/workstation/test-install/provider-a2/state data'
    if state != expected_state or not output.is_relative_to(ROOT / 'build/connections/evidence'):
        raise ValueError('Only the isolated A4 test installation and project evidence are allowed.')
    if sys.flags.optimize or output.exists():
        raise ValueError('Assertions required; preserve prior output by selecting a new directory.')
    output.mkdir(parents=True)
    origin = 'http://127.0.0.1:18746'
    token = json.loads((state / 'client/local-session.json').read_text(encoding='utf-8-sig'))['token']
    groups, errors, external, update_streams = [], [], [], []
    report = dict(started_at=datetime.now(timezone.utc).isoformat(), passed=False,
                  scope='Installed A4 web dashboard in installed Edge; not native desktop interaction',
                  source_identity='8b3e7e0e440b9f4d090517237724999bcd824d86f460663e65d940c9c1d20fd5',
                  origin=origin, groups=groups, page_errors=errors, blocked_external_requests=external,
                  provider_sync_run=False, settings_changed=False, service_restart_run=False)

    def safe(value):
        return str(value).replace(token, '[REDACTED]')

    def passed(name, **detail):
        groups.append(dict(name=name, passed=True, **detail))
        print(json.dumps(groups[-1]), flush=True)

    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel='msedge', headless=True)
        context = browser.new_context(viewport={'width': 1440, 'height': 1050}, accept_downloads=True)
        page = context.new_page()
        page.on('pageerror', lambda error: errors.append(safe(error)))
        page.on('response', lambda response: update_streams.append({
            'status': response.status, 'content_type': response.header_value('content-type')})
            if urlsplit(response.url).path == API + '/updates' else None)

        def no_external(route):
            parsed = urlsplit(route.request.url)
            if parsed.scheme in ('data', 'blob') or f'{parsed.scheme}://{parsed.netloc}' == origin:
                route.continue_()
            else:
                external.append({'origin': f'{parsed.scheme}://{parsed.netloc}'})
                route.abort('blockedbyclient')

        context.route('**/*', no_external)

        def api(path):
            response = context.request.get(origin + API + path, timeout=15000)
            assert response.status == 200, response.status
            return response.json()

        try:
            page.goto(origin + '/#token=' + token, wait_until='domcontentloaded')
            expect(page.get_by_role('heading', name='Today’s football', exact=True)).to_be_visible(timeout=30000)
            assert '#token=' not in page.url
            baseline = api('/connections')
            before = {c['id']: c['record_count'] for c in baseline['items']}
            assert before['football-data-couk'] == 380 and before['statsbomb'] == 64 and before['cricsheet'] == 17
            health = api('/health/ready')
            assert health['status'] == 'ready'
            passed('Installed server authenticates and reports the retained source counts', counts=before)

            page.get_by_role('link', name='Connections', exact=True).click()
            expect(page.get_by_role('heading', name='Connections', exact=True)).to_be_visible()
            for source in ('football-data-couk', 'statsbomb', 'cricsheet'):
                card = page.locator(f'[data-provider="{source}"]')
                expect(card).to_contain_text(f'{before[source]} stored records')
                expect(card.get_by_role('button', name='Test connection', exact=True)).to_be_enabled()
                expect(card.get_by_role('button', name='Sync now', exact=True)).to_be_enabled()
                expect(card).to_contain_text('Last successful retrieval:')
            page.screenshot(path=str(output / 'connections.png'), full_page=True)
            passed('Connections shows persisted counts, retrieval times and real enabled adapter actions')

            page.locator('[data-provider="football-data-couk"]').get_by_role('button', name='Open imported data', exact=True).click()
            expect(page.get_by_role('table')).to_be_visible()
            page.get_by_role('combobox', name='Record type').select_option('historical_result')
            expect(page.get_by_role('table')).to_be_visible()
            page.get_by_role('table').get_by_role('button').first.click()
            expect(page.get_by_role('heading', name='Match overview', exact=True)).to_be_visible()
            match_url = page.url
            match_id = match_url.rsplit('/', 1)[-1]
            match = api('/matches/' + match_id)
            assert match['source_id'] == 'football-data-couk' and match['status'] == 'finished'
            report['match'] = {k: match[k] for k in ('id', 'source_id', 'home', 'away', 'event_date', 'status', 'score')}
            page.screenshot(path=str(output / 'match.png'), full_page=True)
            passed('Imported historical source row opens its own finished canonical football match', match_id=match_id)

            team_name = page.locator('.team-button').first.get_attribute('aria-label').removeprefix('View team ')
            page.locator('.team-button').first.click()
            expect(page.get_by_role('heading', name=team_name, exact=True)).to_be_visible()
            expect(page.get_by_role('heading', name='Recent form', exact=True)).to_be_visible()
            page.get_by_role('button', name='← Return to selected match', exact=True).click()
            expect(page.get_by_role('heading', name='Match overview', exact=True)).to_be_visible()
            assert page.url == match_url
            page.get_by_role('button', name='Open standings', exact=True).click()
            expect(page.get_by_role('table')).to_be_visible()
            expect(page.get_by_text('RECONSTRUCTED', exact=True)).to_be_visible()
            page.screenshot(path=str(output / 'standings.png'), full_page=True)
            page.get_by_role('button', name='← Return to selected match', exact=True).click()
            expect(page.get_by_role('heading', name='Match overview', exact=True)).to_be_visible()
            assert page.url == match_url
            passed('Team form and reconstructed standings return to the same selected match')

            page.get_by_role('tab', name='Odds & chart', exact=True).click()
            expect(page.get_by_role('heading', name='Compatible odds & history', exact=True)).to_be_visible()
            expect(page.get_by_role('heading', name='Odds history', exact=True)).to_be_visible()
            odds = api('/matches/' + match_id + '/odds')
            assert odds['items'] and odds['axis'] == 'archive_phase'
            assert all(q['match_id'] == match_id and q['quote_at'] is None
                       and q['period'] == 'full_time_regulation'
                       and q['provenance_status'] == 'bound' for q in odds['items'])
            expect(page.get_by_text(odds['reason'], exact=True)).to_be_visible()
            (output / 'odds-response.json').write_text(json.dumps(odds, indent=2), encoding='utf-8')
            report['odds'] = dict(count=len(odds['items']), axis=odds['axis'], reason=odds['reason'],
                                  all_same_match=True, source_quote_time_supplied=False,
                                  response_sha256=hashlib.sha256((output / 'odds-response.json').read_bytes()).hexdigest())
            page.screenshot(path=str(output / 'odds.png'), full_page=True)
            passed('Same-match odds control displays retained history and its stated observation axis')

            page.get_by_role('tab', name='Analysis', exact=True).click()
            expect(page.get_by_role('heading', name='Model probabilities', exact=True)).to_be_visible(timeout=30000)
            page.get_by_role('button', name='Explain this match', exact=True).click()
            expect(page.get_by_text('DETERMINISTIC EVIDENCE SUMMARY', exact=True)).to_be_visible(timeout=60000)
            with context.expect_page() as citation:
                page.locator('.explanation-citation').first.click()
            cited = citation.value
            cited.wait_for_load_state('domcontentloaded')
            evidence = json.loads(cited.locator('body').inner_text())
            assert evidence['evidence_id'] and evidence['source_id']
            report['cited_evidence_id'] = evidence['evidence_id']
            cited.close()
            page.screenshot(path=str(output / 'analysis.png'), full_page=True)
            passed('Available analysis produces a labelled deterministic explanation and opens a real citation')

            page.get_by_role('tab', name='Overview', exact=True).click()
            page.get_by_role('button', name='Export to Excel', exact=True).click()
            expect(page.get_by_text('Report ready', exact=True)).to_be_visible(timeout=60000)
            with page.expect_download() as download_info:
                page.get_by_role('link', name='Download Excel report', exact=True).click()
            workbook_path = output / 'selected-match.xlsx'
            download_info.value.save_as(str(workbook_path))
            assert zipfile.is_zipfile(workbook_path)
            book = load_workbook(workbook_path, read_only=True, data_only=True)
            cells = [str(value) for sheet in book for row in sheet.iter_rows(values_only=True) for value in row if value is not None]
            assert match_id in cells and match['home']['name'] in cells and match['away']['name'] in cells
            book.close()
            report['workbook'] = dict(bytes=workbook_path.stat().st_size,
                                      sha256=hashlib.sha256(workbook_path.read_bytes()).hexdigest())
            passed('Visible Excel export downloads a real workbook containing the selected match identity and teams')

            after = {c['id']: c['record_count'] for c in api('/connections')['items']}
            assert before == after
            assert not errors and not external
            passed('Retained source counts unchanged, no page exceptions or external browser requests')
            expect(page.locator('#footer-status')).to_have_text(re.compile(
                r'(Update stream connected\.|New committed data available\.)'), timeout=15000)
            assert update_streams and all(s['status'] == 200 and
                                         s['content_type'].startswith('text/event-stream') for s in update_streams)
            passed('Authenticated event stream returns HTTP200 text/event-stream and UI is connected',
                   responses=update_streams, footer=page.locator('#footer-status').inner_text())
            report['passed'] = True
        except Exception as exc:
            report['error'] = safe(f'{type(exc).__name__}: {exc}')
            report['traceback'] = safe(traceback.format_exc())
            page.screenshot(path=str(output / 'failure.png'), full_page=True)
        finally:
            report['finished_at'] = datetime.now(timezone.utc).isoformat()
            report['harness_sha256'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
            context.close()
            browser.close()
            (output / 'verification.json').write_text(safe(json.dumps(report, indent=2)), encoding='utf-8')
    print(json.dumps({'passed': report['passed'], 'groups': len(groups), 'error': report.get('error')}))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    sys.exit(main())
