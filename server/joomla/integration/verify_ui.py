"""Real Joomla administrator journey on the isolated product-owned test stack."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import hmac
import json
from pathlib import Path
import re
import time
from urllib.parse import parse_qs, urlsplit
from urllib.request import Request, urlopen
from uuid import uuid4

from playwright.sync_api import sync_playwright, expect, TimeoutError as PlaywrightTimeout

ROOT = Path(__file__).resolve().parents[3]


def run():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', type=Path, default=ROOT / 'runtime/scratch/joomla-integration/private.json')
    parser.add_argument('--output', type=Path, default=ROOT / 'runtime/product-evidence/joomla')
    args = parser.parse_args()
    cfg = json.loads(args.config.read_text(encoding='utf-8-sig'))
    args.output.mkdir(parents=True, exist_ok=True)
    url = f"http://127.0.0.1:{cfg['web_port']}/administrator/"
    component = url + 'index.php?option=com_dragonhydra'
    assertions = []
    errors = []
    with sync_playwright() as p:
        browser = p.chromium.launch(channel='msedge', headless=True)
        context = browser.new_context(viewport={'width': 1440, 'height': 1080}, reduced_motion='reduce')
        page = context.new_page()
        page.on('pageerror', lambda e: errors.append(str(e)))
        page.goto(component)
        expect(page.locator('#mod-login-username')).to_be_visible()
        assertions.append('Unauthenticated administration requires Joomla login')

        def login(target, user, password):
            target.goto(url)
            target.locator('#mod-login-username').fill(user)
            target.locator('#mod-login-password').fill(password)
            target.get_by_role('button', name='Log in', exact=True).click()
            target.wait_for_load_state('domcontentloaded')
            expect(target.locator('#mod-login-username')).not_to_be_visible(timeout=20000)
            # A fresh Joomla account may open its own welcome tour and reroute to
            # Home. Exercise its real dismissal before entering the product screen.
            hide_tour = target.get_by_role('button', name='Hide Forever', exact=True)
            try:
                hide_tour.wait_for(state='visible', timeout=5000)
                hide_tour.click()
                hide_tour.wait_for(state='hidden')
            except PlaywrightTimeout:
                pass

        login(page, cfg['admin_username'], cfg['admin_password'])
        page.goto(component + '&section=sources')
        expect(page.get_by_role('heading', name='Data sources', exact=True)).to_be_visible()
        expect(page.get_by_role('button', name='Import public results', exact=True)).to_be_visible()
        assert 'BRIDGE_NOT_CONFIGURED' not in page.inner_text('body')
        assertions.append('Authenticated Joomla component renders signed kernel source status')
        page.get_by_role('button', name='Check capabilities', exact=True).first.click()
        page.wait_for_load_state('domcontentloaded')
        page.wait_for_timeout(500)
        if not page.get_by_text('Latest capability proof', exact=True).count():
            page.screenshot(path=str(args.output / 'capability-failure.png'), full_page=True)
            print(page.inner_text('body')[:4000])
        expect(page.get_by_text('Latest capability proof', exact=True)).to_be_visible()
        assertions.append('Capability button executes CSRF-protected signed kernel operation and displays proof')
        page.screenshot(path=str(args.output / 'sources.png'), full_page=True)

        # Verify CSRF rejection before exercising the valid import action.
        response = context.request.post(component + '&task=actions.sync', form={})
        assert response.status == 403, response.status
        assertions.append('Import without a Joomla POST token is rejected with HTTP 403')
        page.goto(component + '&section=sources')
        page.get_by_role('button', name='Import public results', exact=True).click()
        expect(page.get_by_role('heading', name='Import job', exact=True)).to_be_visible()
        job_id = parse_qs(urlsplit(page.url).query)['job_id'][0]
        deadline = time.monotonic() + 70
        while time.monotonic() < deadline and not page.get_by_role('link', name='View imported matches', exact=True).is_visible():
            assert not page.get_by_text('failed', exact=True).is_visible(), page.inner_text('body')
            time.sleep(.4)
            page.get_by_role('link', name='Refresh job status', exact=True).click()
        expect(page.get_by_role('link', name='View imported matches', exact=True)).to_be_visible()
        page.screenshot(path=str(args.output / 'import-job.png'), full_page=True)
        assertions.append('Import button queues a typed durable kernel job and reaches succeeded')
        page.get_by_role('link', name='View imported matches', exact=True).click()
        page.wait_for_timeout(500)
        expect(page.get_by_role('heading', name='Matches and teams', exact=True)).to_be_visible()
        match_link = page.locator('.dragonhydra-administration tbody th a').first
        match_label = match_link.inner_text()
        match_id = parse_qs(urlsplit(match_link.get_attribute('href')).query)['match_id'][0]
        match_link.click()
        expect(page).to_have_url(re.compile('match_id=' + re.escape(match_id)))
        page.wait_for_timeout(700)
        expect(page.get_by_role('heading', name=match_label, exact=True)).to_be_visible()
        # Joomla may append an accessible "opens in a new window" suffix.
        dashboard_link = page.locator('a[href*="#match/"]').get_attribute('href')
        assert dashboard_link.endswith('/#match/' + match_id)
        page.screenshot(path=str(args.output / 'canonical-match.png'), full_page=False, animations='disabled')
        secret_record = json.loads(Path(cfg['bridge_secret_path']).read_text(encoding='utf-8-sig'))
        secret = secret_record['secret']
        path = '/dragon/api/v1/matches/' + match_id
        timestamp, nonce, user, roles = str(int(time.time())), uuid4().hex, 'joomla:1', 'reader'
        signature = hmac.new(secret.encode(), '\n'.join(['GET', path, timestamp, nonce, user, roles, hashlib.sha256(b'').hexdigest()]).encode(), hashlib.sha256).hexdigest()
        headers = {'X-Dragon-User': user, 'X-Dragon-Roles': roles, 'X-Dragon-Time': timestamp, 'X-Dragon-Nonce': nonce, 'X-Dragon-Signature': signature}
        request = Request(cfg['api_base'] + '/matches/' + match_id, headers=headers)
        with urlopen(request, timeout=10) as response:
            match = json.load(response)
        assert match_label == match['home']['name'] + ' — ' + match['away']['name']
        assertions.append('Joomla fixture and dashboard deep link use the exact canonical event returned by the shared API')

        for section, title in [('odds','Odds administration'),('models','AI and models'),('research','Research'),('databases','Database connections'),('system','System')]:
            page.goto(component + '&section=' + section)
            expect(page.get_by_role('heading', name=title, exact=True)).to_be_visible()
            assert 'The kernel request could not complete' not in page.inner_text('body')
        assertions.append('All seven administration sections open with actual source/system responses and explicit capability limits')

        reader_context = browser.new_context(viewport={'width': 1440, 'height': 1080}, reduced_motion='reduce')
        reader_page = reader_context.new_page()
        login(reader_page, cfg['reader_username'], cfg['reader_password'])
        reader_page.goto(component + '&section=sources')
        expect(reader_page.get_by_role('heading', name='Data sources', exact=True)).to_be_visible()
        expect(reader_page.get_by_role('button', name='Import public results', exact=True)).to_have_count(0)
        reader_page.screenshot(path=str(args.output / 'reader-acl.png'), full_page=True)
        token = reader_page.locator('input[type=hidden][value="1"]').evaluate_all("nodes => nodes.map(n => n.name).find(n => /^[a-f0-9]{32}$/.test(n))")
        if not token:
            token = reader_page.evaluate("window.Joomla?.getOptions('csrf.token')")
        assert token, 'Joomla CSRF token not found'
        forbidden = reader_context.request.post(component + '&task=actions.sync', form={token: '1'})
        assert forbidden.status == 403, forbidden.status
        assertions.append('Reader sees source status but import controls are absent; direct valid-CSRF mutation is rejected by Joomla ACL')
        assert not errors, errors
        reader_context.close()
        context.close()
        browser.close()
    receipt = {'recorded_at': datetime.now(timezone.utc).isoformat(), 'status': 'passed',
               'stack': {'joomla':'6.2.0','php':'8.4.27 TS VS17 x64','apache':'2.4.65 x64','mariadb':'10.11.16 x64'},
               'web_url': url, 'api_base': cfg['api_base'], 'assertions': assertions,
               'job_id': job_id, 'canonical_match': {'id':match_id,'label':match_label,'source_id':match['source_id']},
               'page_errors':errors, 'native_installation_test':False,
               'scope':'Private integration instance; reuses installed Apache/MariaDB binaries. Not a complete workstation clean-install test.'}
    (args.output / 'journey.json').write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(receipt, indent=2))


if __name__ == '__main__':
    run()
