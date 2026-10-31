"""Exercise actual controls against a running DRAGONHYDRA API and Edge.

No invented matches or backend mocks. A single intentional intercepted 503 tests
the visible error/retry path. Screenshots and assertions remain project-local.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import zipfile

from playwright.sync_api import sync_playwright, expect


def run():
    parser = argparse.ArgumentParser()
    parser.add_argument('--url', required=True)
    parser.add_argument('--state', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=Path('runtime/evidence/dashboard'))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    token_doc = json.loads((args.state / 'local-session.json').read_text(encoding='utf-8-sig'))
    token = token_doc.get('token') or token_doc.get('admin_token')
    if not token:
        raise ValueError('Expected token in local-session.json; no token contents are logged.')
    assertions = []
    errors = []
    console_errors = []
    started = datetime.now(timezone.utc).isoformat()
    with sync_playwright() as p:
        browser = p.chromium.launch(channel='msedge', headless=True)
        context = browser.new_context(viewport={'width': 1440, 'height': 1050}, accept_downloads=True)
        page = context.new_page()
        page.on('pageerror', lambda exc: errors.append(str(exc)))
        page.on('console', lambda msg: console_errors.append(msg.text) if msg.type == 'error' else None)
        page.goto(args.url + '/#token=' + token, wait_until='domcontentloaded')
        expect(page.get_by_role('heading', name='Today’s football')).to_be_visible(timeout=30000)
        assert '#token=' not in page.url
        assertions.append('Launcher token exchanged for cookie and removed from address bar')
        context.clear_cookies()
        page.goto(args.url + '/#token=deliberately-invalid-pairing-token', wait_until='domcontentloaded')
        expect(page.get_by_role('heading', name='Connect to your server')).to_be_visible(timeout=15000)
        page.locator('#server-address').fill(args.url + '/')
        page.locator('#pairing-token').fill(token)
        page.get_by_role('button', name='Connect', exact=True).click()
        expect(page.get_by_role('heading', name='Today’s football')).to_be_visible(timeout=30000)
        expect(page.locator('#login-dialog')).not_to_be_visible()
        assertions.append('Rejected token recovers through same-origin server-address and corrected-token controls')
        page.get_by_role('button', name='Import retained public results').first.click()
        expect(page.get_by_role('heading', name='Retained matches', exact=True)).to_be_visible(timeout=120000)
        expect(page.locator('.match-card').first).to_be_visible()
        assertions.append('Public onboarding import completed and real retained matches displayed')
        page.locator('.match-card').first.click()
        expect(page.get_by_role('heading', name='Match overview')).to_be_visible()
        match_url = page.url
        match_id = match_url.rsplit('/', 1)[-1]
        team_name = page.locator('.team-button').first.get_attribute('aria-label').replace('View team ', '')
        page.screenshot(path=str(args.output / 'match-overview.png'), full_page=True)
        page.locator('.team-button').first.click()
        expect(page.get_by_role('heading', name=team_name, exact=True)).to_be_visible()
        expect(page.get_by_role('heading', name='Recent form', exact=True)).to_be_visible()
        page.get_by_role('button', name='← Return to selected match').click()
        expect(page.get_by_role('heading', name='Match overview')).to_be_visible()
        assert page.url == match_url
        page.get_by_role('button', name='Open standings').click()
        expect(page.get_by_role('table')).to_be_visible()
        expect(page.get_by_text('RECONSTRUCTED', exact=True)).to_be_visible()
        page.screenshot(path=str(args.output / 'standings.png'), full_page=True)
        page.get_by_role('button', name='← Return to selected match').click()
        expect(page.get_by_role('heading', name='Match overview')).to_be_visible()
        assert page.url == match_url
        assertions.append('Match → team → return → reconstructed standings → return retains canonical event')
        page.get_by_role('tab', name='Lineups', exact=True).click()
        expect(page.get_by_text('This source does not provide this match context. Missing data does not mean zero.')).to_be_visible()
        page.get_by_role('tab', name='Statistics', exact=True).click()
        expect(page.get_by_role('heading', name='Match statistics', exact=True)).to_be_visible()
        assertions.append('Lineups and statistics tabs display explicit source availability')
        page.get_by_role('tab', name='Odds & chart').click()
        expect(page.get_by_role('heading', name='Compatible odds & history')).to_be_visible()
        expect(page.get_by_role('heading', name='Odds history', exact=True)).to_be_visible()
        assertions.append('Odds control opens same-event compatibility and truthful history availability')
        page.get_by_role('tab', name='Analysis', exact=True).click()
        expect(page.get_by_role('heading', name='Model probabilities')).to_be_visible(timeout=30000)
        page.get_by_role('button', name='Explain this match').click()
        expect(page.get_by_text('DETERMINISTIC EVIDENCE SUMMARY', exact=True)).to_be_visible(timeout=120000)
        expect(page.get_by_role('heading', name='Cited evidence')).to_be_visible()
        expect(page.locator('.explanation-citation').first).to_be_visible()
        with context.expect_page() as cited:
            page.locator('.explanation-citation').first.click()
        cited_page = cited.value
        cited_page.wait_for_load_state('domcontentloaded')
        cited_evidence = json.loads(cited_page.locator('body').inner_text())
        assert cited_evidence['evidence_id']
        assert cited_evidence['source_id']
        cited_page.close()
        page.screenshot(path=str(args.output / 'analysis.png'), full_page=True)
        assertions.append('Analysis action produced a labelled deterministic summary; cited source record opened and checked')
        page.get_by_role('tab', name='Overview', exact=True).click()
        page.get_by_role('button', name='Export to Excel', exact=True).click()
        expect(page.get_by_text('Report ready', exact=True)).to_be_visible(timeout=120000)
        with page.expect_download() as captured:
            page.get_by_role('link', name='Download Excel report').click()
        download = captured.value
        output = args.output / download.suggested_filename
        download.save_as(str(output))
        assert zipfile.is_zipfile(output), 'Export must be an actual XLSX ZIP container'
        with zipfile.ZipFile(output) as workbook:
            assert '[Content_Types].xml' in workbook.namelist()
            assert 'xl/workbook.xml' in workbook.namelist()
        assertions.append('Export control downloaded a real Excel workbook')
        page.get_by_role('link', name='Live', exact=True).click()
        expect(page.get_by_role('heading', name='No live matches available')).to_be_visible()
        assertions.append('Live view presents an honest empty schedule and useful browsing actions')
        page.get_by_role('button', name='Browse retained matches', exact=True).first.click()
        expect(page.locator('.match-card').first).to_be_visible()
        page.get_by_role('searchbox', name='Search matches').fill(team_name)
        page.get_by_role('button', name='Apply filters', exact=True).click()
        expect(page.locator('.match-card').first).to_be_visible()
        assert all(team_name in text for text in page.locator('.match-card').all_text_contents())
        page.get_by_role('searchbox', name='Search matches').fill('')
        page.get_by_role('button', name='Apply filters', exact=True).click()
        expect(page.get_by_role('button', name='Next', exact=True)).to_be_visible()
        page.get_by_role('button', name='Next', exact=True).click()
        expect(page.get_by_role('button', name='Previous', exact=True)).to_be_visible()
        page.get_by_role('button', name='Previous', exact=True).click()
        expect(page.locator('.match-card').first).to_be_visible()
        assertions.append('Search, Apply filters and pagination controls operate against actual API records')
        fail_pattern = '**/dragon/api/v1/matches?*'
        page.route(fail_pattern, lambda route: route.fulfill(status=503, content_type='application/json', body=json.dumps({'error': {'code': 'SIMULATED_OUTAGE', 'message': 'Injected service unavailable; retry is available.'}})))
        page.get_by_role('button', name='Refresh current view').click()
        expect(page.get_by_text('Injected service unavailable; retry is available.')).to_be_visible()
        page.unroute(fail_pattern)
        page.get_by_role('button', name='Retry', exact=True).click()
        expect(page.locator('.match-card').first).to_be_visible()
        assertions.append('Intentional 503 shows specific visible error and Retry restores retained browsing')
        page.get_by_role('link', name='Teams', exact=True).click()
        expect(page.get_by_role('heading', name='Team directory', exact=True)).to_be_visible()
        page.get_by_role('link', name='Competitions', exact=True).click()
        expect(page.get_by_role('heading', name='Your competitions', exact=True)).to_be_visible()
        page.get_by_role('link', name='Odds', exact=True).click()
        expect(page.get_by_role('heading', name='Compatible odds & history', exact=True)).to_be_visible()
        page.get_by_role('link', name='Analysis', exact=True).click()
        expect(page.get_by_role('heading', name='Model probabilities', exact=True)).to_be_visible()
        assertions.append('Teams, Competitions, Odds and Analysis primary navigation resolve visibly')
        page.get_by_role('link', name='Connections', exact=True).click()
        expect(page.get_by_role('heading', name='Connections', exact=True)).to_be_visible()
        system = page.request.get(args.url + '/dragon/api/v1/system').json()
        if system.get('administration_url'):
            with context.expect_page() as admin_opened:
                page.get_by_role('button', name='Administration', exact=True).first.click()
            admin_page = admin_opened.value
            admin_page.wait_for_load_state('domcontentloaded')
            assert admin_page.url.startswith(system['administration_url'])
            admin_page.close()
            assertions.append('Administration control opened the configured Joomla URL')
        else:
            page.get_by_role('button', name='Administration', exact=True).first.click()
            expect(page.locator('#notification')).to_be_visible()
            assertions.append('Administration control explains the specific unconfigured Joomla requirement')
        page.set_viewport_size({'width': 420, 'height': 900})
        page.get_by_role('link', name='Today', exact=True).click()
        expect(page.get_by_role('heading', name='Today’s football')).to_be_visible()
        assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth + 2'), 'Narrow window must not horizontally overflow'
        expect(page.locator('#notification')).to_be_hidden(timeout=10000)
        page.screenshot(path=str(args.output / 'narrow-today.png'), full_page=True)
        page.keyboard.press('Tab')
        assert page.evaluate('document.activeElement !== document.body')
        assertions.append('Narrow window has no horizontal overflow and keyboard focus reaches controls')
        context.close()
        browser.close()
    result = {'started_at': started, 'finished_at': datetime.now(timezone.utc).isoformat(), 'browser': 'Installed Microsoft Edge / Playwright', 'url': args.url, 'canonical_match_id': match_id, 'assertions': assertions, 'page_errors': errors, 'console_errors': console_errors, 'workbook': {'path': str(output), 'bytes': output.stat().st_size, 'sha256': hashlib.sha256(output.read_bytes()).hexdigest()}, 'status': 'passed' if not errors else 'failed', 'not_run': ['Native packaged-client automation', 'Clean-machine installation', 'Local LLM inference', 'Live account import']}
    (args.output / 'journey.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps({'status': result['status'], 'assertions': len(assertions), 'page_errors': errors, 'evidence': str(args.output / 'journey.json')}, indent=2))
    return 1 if errors else 0


if __name__ == '__main__':
    sys.exit(run())
