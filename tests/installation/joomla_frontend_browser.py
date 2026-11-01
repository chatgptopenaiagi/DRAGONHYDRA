"""Genuine site-session acceptance of the installed Joomla-native workspace.

Uses owner-bound private acceptance credentials and an independent authenticated
API reader for comparisons. Never inserts backend credentials into the browser.
"""
import argparse
import csv
from datetime import datetime, timezone
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import re
import time
from urllib.parse import parse_qs, urlencode, urlsplit, urljoin
from zipfile import ZipFile

from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / 'build/joomla-frontend-20261101/evidence'
ORIGIN = 'http://127.0.0.1:18740'
HOME = ORIGIN + '/'
ADMIN = ORIGIN + '/administrator/'


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sha(data):
    return hashlib.sha256(data).hexdigest()


def utc():
    return datetime.now(timezone.utc).isoformat()


class Acceptance:
    def __init__(self, output, continued_from=None):
        self.output = output.resolve()
        assert self.output.parent == BASE.resolve() and self.output.name.startswith('browser-') and not self.output.exists()
        self.output.mkdir()
        self.credentials = load('frontend_private_credentials', ROOT / 'tests/installation/joomla_frontend_credentials.py')
        self.login_credentials = self.credentials.load_credentials()
        recovery_module = self.credentials.load_recovery()
        self.api = recovery_module.Recovery()
        assert self.api.cfg['api_port'] == 18744 and self.api.cfg['web_port'] == 18740
        self.private_values = [self.login_credentials['password'], self.api.token]
        self.private_values += [self.api.cfg[key] for key in ('root_password', 'db_password', 'core_db_password', 'admin_password')]
        self.report = {'schema_version': 1, 'passed': False, 'started_at': utc(),
                       'scope': 'Actual installed Joomla website and real Microsoft Edge site/administrator sessions',
                       'origin': ORIGIN, 'backend': self.api.api, 'helper_sha256': sha(Path(__file__).read_bytes()),
                       'checks': [], 'page_errors': [], 'forbidden_requests': [], 'exports': [],
                       'credentials_logged': False, 'backend_credential_inserted_in_browser': False,
                       'provider_sync_or_inference_requested': False, 'screenshots': []}
        self.stage = 'initialization'
        self.continued_from = continued_from.resolve() if continued_from else None
        self.previous = json.loads(self.continued_from.read_text()) if self.continued_from else None
        if self.previous:
            assert self.continued_from.is_relative_to(BASE) and self.previous['origin'] == ORIGIN
            assert all(row['status'] == 'PASS' for row in self.previous['checks'])
            self.report['continued_from'] = {'path': str(self.continued_from), 'sha256': sha(self.continued_from.read_bytes()), 'previous_passed_checks': len(self.previous['checks']), 'scope': 'Earlier successful data/export checks retained separately, not re-executed or counted in this receipt'}
            self.report['exports'] = self.previous['exports']

    def save(self):
        (self.output / 'verification.json').write_text(json.dumps(self.report, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')

    def check(self, name, condition, **evidence):
        self.report['checks'].append({'name': name, 'status': 'PASS' if condition else 'FAIL', 'verified_at': utc(), **evidence})
        self.save()
        assert condition, 'Acceptance gate failed'

    def route(self, page, **parameters):
        query = {'option': 'com_dragonhydra'} | parameters
        page.goto(ORIGIN + '/index.php?' + urlencode(query), wait_until='domcontentloaded')
        expect(page.locator('[data-dragonhydra-workspace]')).to_be_visible()
        self.assert_no_secret_browser_state(page)

    def watch(self, context):
        def guard(route):
            request = route.request
            parsed = urlsplit(request.url)
            query = parse_qs(parsed.query)
            task = query.get('task', [''])[0]
            allowed_post = (task in ('actions.export', 'user.login', 'user.logout', 'login')
                            or query.get('option') == ['com_login'])
            if parsed.hostname == '127.0.0.1' and parsed.port == 18740:
                if request.method not in ('GET', 'HEAD') and not allowed_post:
                    # Joomla login forms may encode the task in the POST body.
                    body = parse_qs(request.post_data or '')
                    allowed_post = body.get('task', [''])[0] in ('user.login', 'user.logout', 'login')
                if (request.method not in ('GET', 'HEAD') and not allowed_post) or parsed.path.startswith('/dragon/'):
                    self.report['forbidden_requests'].append({'method': request.method, 'path': parsed.path,
                                                              'reason': 'Unapproved browser API/mutation route'})
                    route.abort()
                    return
            elif request.method not in ('GET', 'HEAD'):
                route.abort()
                return
            route.continue_()
        context.route('**/*', guard)
        def page_added(page):
            def error_seen(error):
                if urlsplit(page.url).netloc == '127.0.0.1:18740':
                    self.report['page_errors'].append({'class': type(error).__name__, 'sha256': sha(str(error).encode())})
            page.on('pageerror', error_seen)
        context.on('page', page_added)

    def login(self, page, *, administrator=False):
        if administrator:
            page.goto(ADMIN, wait_until='domcontentloaded')
        else:
            page.goto(HOME, wait_until='domcontentloaded')
            page.get_by_role('link', name=re.compile('Sign in to your workspace')).click()
        username = page.locator('input[name="username"]:visible').first
        password = page.locator('input[type="password"]:visible').first
        expect(username).to_be_visible()
        form = username.locator('xpath=ancestor::form[1]')
        hidden_names = form.locator('input[type="hidden"]').evaluate_all('(nodes) => nodes.map(n => n.name)')
        assert any(re.fullmatch('[a-f0-9]{32}', name) for name in hidden_names)
        username.fill(self.login_credentials['username'])
        password.fill(self.login_credentials['password'])
        form.locator('button[type="submit"],input[type="submit"]').first.click()
        page.wait_for_load_state('domcontentloaded')
        if administrator:
            page.goto(ADMIN + 'index.php?option=com_dragonhydra&section=sources', wait_until='domcontentloaded')
            expect(page.locator('.dragonhydra-administration')).to_be_visible()
            expect(page.get_by_role('heading', name='Data sources', exact=True)).to_be_visible()
        else:
            expect(page.locator('[data-total="total_matches"]')).to_be_visible(timeout=20000)
        self.assert_no_secret_browser_state(page)

    def assert_no_secret_browser_state(self, page):
        html = page.content()
        storage = page.evaluate('({local: {...localStorage}, session: {...sessionStorage}})')
        serialized = html + json.dumps(storage)
        assert not any(value and value in serialized for value in self.private_values)
        return storage

    def no_secret_values(self, page):
        storage = self.assert_no_secret_browser_state(page)
        scripts = page.locator('script[src]').evaluate_all('(nodes) => nodes.map(n => n.src)')
        checked = 0
        for url in scripts:
            if urlsplit(url).netloc == '127.0.0.1:18740':
                body = page.context.request.get(url).text()
                assert not any(value and value in body for value in self.private_values)
                checked += 1
        return {'local_script_bundles_checked': checked, 'local_storage_entries': len(storage['local']),
                'session_storage_entries': len(storage['session']), 'private_value_matches': 0}

    def screenshot(self, page, name):
        path = self.output / name
        page.locator('[data-dragonhydra-workspace]').screenshot(path=str(path), animations='disabled')
        self.report['screenshots'].append({'path': str(path), 'sha256': sha(path.read_bytes()),
                                           'scope': 'Component-only; no credential-entry form'})

    def compare_match(self, page, match):
        self.route(page, section='matches', match_id=match['id'])
        expect(page.get_by_role('heading', name='Match details', exact=True)).to_be_visible()
        visible = page.locator('[data-dragonhydra-workspace]').inner_text()
        assert match['home']['name'] in visible and match['away']['name'] in visible and match['source_id'] in visible
        page.locator('.dh-technical summary').click()
        details = page.locator('.dh-technical').inner_text()
        for key in ('id', 'evidence_id', 'version', 'competition_id', 'received_at', 'usable_at'):
            assert str(match[key]) in details
        return {key: match[key] for key in ('id', 'source_id', 'evidence_id', 'version', 'event_date', 'home', 'away', 'status')}

    def export(self, page, match, kind):
        self.route(page, section='reports', match_id=match['id'])
        label = {'json': 'Export JSON', 'csv': 'Export CSV', 'xlsx': 'Export Excel (.xlsx)'}[kind]
        page.get_by_role('button', name=label, exact=True).click()
        page.wait_for_load_state('domcontentloaded')
        query = parse_qs(urlsplit(page.url).query)
        job_id = query.get('job_id', [''])[0]
        assert re.fullmatch('[a-f0-9]{32}', job_id)
        deadline = time.monotonic() + 45
        while not page.get_by_role('link', name=re.compile('Download report')).is_visible():
            assert time.monotonic() < deadline
            assert not page.get_by_text('This export did not complete.', exact=False).is_visible()
            page.get_by_role('link', name='Refresh export status', exact=True).click()
            page.wait_for_load_state('domcontentloaded')
            page.wait_for_timeout(250)
        link = page.get_by_role('link', name=re.compile('Download report'))
        href = link.get_attribute('href')
        with page.expect_download(timeout=30000) as download_event:
            link.click()
        download = download_event.value
        assert download.failure() is None
        filename = download.suggested_filename
        assert re.fullmatch('DRAGONHYDRA-[a-f0-9]{32}\\.' + kind, filename)
        folder = self.output / 'exports'; folder.mkdir(exist_ok=True)
        path = folder / filename
        download.save_as(path)
        body = path.read_bytes()
        assert len(body) > 30
        if kind == 'json':
            record = json.loads(body)
            assert record['match']['id'] == match['id'] and record['match']['evidence_id'] == match['evidence_id']
        elif kind == 'csv':
            rows = list(csv.DictReader(io.StringIO(body.decode('utf-8-sig'))))
            assert len(rows) == 1 and rows[0]['id'] == match['id'] and rows[0]['source_id'] == match['source_id']
        else:
            with ZipFile(io.BytesIO(body)) as workbook:
                assert '[Content_Types].xml' in workbook.namelist()
                assert any(match['id'].encode() in workbook.read(name) for name in workbook.namelist() if name.startswith('xl/worksheets/'))
        job = self.api.api_read('/jobs/' + job_id)
        assert job['kind'] == 'export' and job['status'] == 'succeeded' and job['owner'].startswith('joomla:')
        row = {'format': kind, 'job_id': job_id, 'owner': job['owner'], 'filename': filename,
               'bytes': len(body), 'sha256': sha(body), 'download_href': href}
        self.report['exports'].append(row)
        return row

    def run(self):
        baseline = self.previous['baseline'] if self.previous else self.api.snapshot()
        assert self.api.snapshot() == baseline
        self.report['baseline'] = baseline
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel='msedge', headless=True)
            context = browser.new_context(viewport={'width': 1440, 'height': 1000}, accept_downloads=True)
            self.watch(context)
            page = context.new_page()
            if self.previous:
                self.login(page)
                self.check('fresh_site_login_for_remaining_acceptance', True)
            else:
                self.stage = 'anonymous_homepage'
                page.goto(HOME, wait_until='domcontentloaded')
                expect(page.locator('[data-dragonhydra-workspace]')).to_be_visible()
                text = page.locator('body').inner_text()
                self.check('root_homepage_uses_native_component_and_preserves_anonymous_privacy',
                           'DRAGONHYDRA' in text and 'Your sports.' in text and 'Welcome to Joomla' not in text
                           and 'Popular Tags' not in text and 'Older Posts' not in text and page.locator('[data-total]').count() == 0)
                self.screenshot(page, 'anonymous-homepage.png')
                self.check('anonymous_assets_and_storage_contain_no_private_credentials', True, **self.no_secret_values(page))
                self.stage = 'real_site_login'
                self.login(page)
                self.check('genuine_separate_joomla_site_login', True, username=self.login_credentials['username'], backend_token_injected=False)
                totals = {key: int(page.locator('[data-total="' + key + '"]').inner_text().replace(',', ''))
                          for key in ('total_matches', 'total_teams', 'total_competitions')}
                expected_totals = {'total_matches': baseline['records'], 'total_teams': len(self.api.api_read('/teams')['items']),
                                   'total_competitions': len(self.api.api_read('/competitions')['items'])}
                self.check('dashboard_totals_match_corresponding_backend', totals == expected_totals, totals=totals)
                self.screenshot(page, 'authenticated-overview-desktop.png')
                page.reload(wait_until='domcontentloaded')
                expect(page.locator('[data-total="total_matches"]')).to_have_text(f"{baseline['records']:,}")
                self.check('authenticated_reload_retains_site_session', True)
                self.stage = 'search_filters_pagination'
                self.route(page, section='matches', limit=10)
                first_ids = page.locator('.dh-fixture').evaluate_all('(nodes)=>nodes.map(n=>n.href)')
                page.get_by_role('link', name=re.compile('Next page')).click()
                expect(page.locator('.dh-pagination')).to_contain_text('11–20')
                second_ids = page.locator('.dh-fixture').evaluate_all('(nodes)=>nodes.map(n=>n.href)')
                self.check('match_pagination_is_real_and_changes_records', bool(first_ids and second_ids) and set(first_ids).isdisjoint(second_ids))
                finished = self.api.api_read('/matches?status=finished&limit=1&offset=0')['items'][0]
                self.route(page, section='matches')
                page.get_by_label('Find a match', exact=True).fill(finished['home']['name'])
                page.get_by_label('Competition', exact=True).select_option(finished['competition_id'])
                page.get_by_label('Match status', exact=True).select_option('finished')
                page.get_by_label('Per page', exact=True).select_option('10')
                page.get_by_role('button', name='Apply filters', exact=True).click()
                expect(page.locator('.dh-fixture').first).to_be_visible()
                expected = self.api.api_read('/matches?' + urlencode({'search': finished['home']['name'], 'competition': finished['competition_id'], 'status': 'finished', 'limit': 10, 'offset': 0}))
                shown = page.locator('.dh-fixture').evaluate_all('(nodes)=>nodes.map(n=>n.href)')
                self.check('search_competition_status_and_limit_use_actual_retained_filters',
                           int(page.locator('[data-match-total]').inner_text().replace(',', '')) == expected['total']
                           and len(shown) == len(expected['items']) and all(item['id'] in href for item, href in zip(expected['items'], shown)), total=expected['total'])
                self.stage = 'match_details'
                record = self.compare_match(page, finished)
                self.check('retained_match_source_ids_timestamps_and_identity_match_backend', True, match=record)
                self.screenshot(page, 'retained-match.png')
                self.stage = 'teams_and_competitions'
                self.route(page, section='teams', team_id=finished['home']['id'])
                expect(page.get_by_role('heading', name=finished['home']['name'], exact=True)).to_be_visible()
                expect(page.get_by_role('heading', name='Recent retained form', exact=True)).to_be_visible()
                team = self.api.api_read('/teams/' + finished['home']['id'])
                self.check('source_scoped_team_navigation_and_existing_form', page.locator('.dh-fixture').count() == len(team['matches']), matches=len(team['matches']))
                self.route(page, section='competitions', competition=finished['competition_id'])
                standings = self.api.api_read('/competitions/' + finished['competition_id'] + '/standings')
                self.check('competition_navigation_and_calculated_standings', page.locator('.dh-standings tbody tr').count() == len(standings['items'])
                           and 'Calculated from retained results' in page.locator('[data-dragonhydra-workspace]').inner_text(), rows=len(standings['items']))
                self.stage = 'analysis'
                self.route(page, section='analysis', match_id=finished['id'])
                predicted = self.api.api_read('/matches/' + finished['id'] + '/predictions')
                self.check('finished_match_forecast_unavailability_is_honest', not predicted['available'] and page.get_by_role('heading', name='No supported forecast is available', exact=True).is_visible()
                           and predicted['reason'] in page.locator('[data-dragonhydra-workspace]').inner_text(), reason=predicted['reason'])
                candidate = self.api.api_read('/matches?status=scheduled&limit=1&offset=0')['items'][0]
                predicted = self.api.api_read('/matches/' + candidate['id'] + '/predictions')
                self.route(page, section='analysis', match_id=candidate['id'])
                if predicted.get('available') and predicted.get('ensemble'):
                    values = page.locator('.dh-probabilities dd').all_inner_texts()
                    expected = []
                    for key in ('home', 'draw', 'away'):
                        value = predicted['ensemble'][key]
                        value = value.get('value') if isinstance(value, dict) else value
                        expected.append(f'{value * 100:.1f}%')
                    self.check('existing_scheduled_analysis_matches_backend', values == expected, available=True, probabilities=expected)
                else:
                    self.check('existing_scheduled_analysis_matches_backend', page.get_by_role('heading', name='No supported forecast is available', exact=True).is_visible()
                               and predicted.get('reason', '') in page.locator('[data-dragonhydra-workspace]').inner_text(), available=False, reason=predicted.get('reason'))
                self.stage = 'exports'
                for kind in ('json', 'csv', 'xlsx'):
                    artifact = self.export(page, finished, kind)
                    self.check('actual_frontend_' + kind + '_export_download', True, artifact=artifact)
                forbidden = context.request.post(ORIGIN + '/index.php?option=com_dragonhydra&task=actions.export', form={'match_id': finished['id'], 'format': 'json'})
                self.check('authenticated_export_without_joomla_csrf_is_denied', forbidden.status == 403, http_status=forbidden.status)
            self.stage = 'connections'
            handoff_requests = []
            def controlled_external_document(route):
                request = route.request
                if request.is_navigation_request() and request.resource_type == 'document':
                    handoff_requests.append(request.url)
                    route.fulfill(status=200, content_type='text/html', body='<!doctype html><title>External navigation acceptance</title><p>Controlled transport for destination verification.</p>')
                else:
                    route.continue_()
            context.route('https://**/*', controlled_external_document)
            self.report['external_link_scope'] = 'Real anchor clicks and new browser tabs at exact configured HTTPS addresses; external document transport is controlled to avoid provider/network variability. Remote provider availability is not asserted.'
            self.route(page, section='connections')
            links = page.locator('.dh-provider-action a[target="_blank"]')
            expected_connections = self.api.api_read('/connections')['items']
            self.check('connections_show_actual_provider_status_without_admin_actions', page.locator('.dh-provider').count() == len(expected_connections)
                       and page.get_by_role('button', name=re.compile('Import|Synchronize|Check capabilities', re.I)).count() == 0, providers=len(expected_connections))
            destinations = []
            for index in range(links.count()):
                link = links.nth(index)
                href = link.get_attribute('href')
                parsed = urlsplit(href)
                assert parsed.scheme == 'https' and not parsed.username and not parsed.password and not parsed.query
                before = page.url
                self.report['external_link_progress'] = {'index': index, 'href': href}
                self.save()
                observed = []
                def opened(new_page):
                    new_page.on('request', lambda request: observed.append(request.url) if request.is_navigation_request() else None)
                context.on('page', opened)
                with page.expect_popup(timeout=10000) as popup_event:
                    link.click()
                popup = popup_event.value
                popup.wait_for_timeout(300)
                context.remove_listener('page', opened)
                received = popup.url == href and href in handoff_requests
                destinations.append({'href': href, 'browser_popup_received_target': received, 'workspace_unchanged': page.url == before})
                popup.close()
                assert received and page.url == before
            self.check('provider_registration_documentation_open_new_tabs_and_preserve_workspace', len(destinations) == len(expected_connections), destinations=destinations, external_document_transport='controlled')
            context.unroute('https://**/*', controlled_external_document)
            self.stage = 'administrator_regression'
            admin_context = browser.new_context(viewport={'width': 1440, 'height': 1000})
            self.watch(admin_context)
            admin_page = admin_context.new_page()
            self.login(admin_page, administrator=True)
            self.check('existing_administrator_and_component_still_authenticate_and_render', 'OpenFootball' in admin_page.locator('.dragonhydra-administration').inner_text())
            admin_context.close()
            self.stage = 'responsive_and_secret_safety'
            self.route(page, section='overview')
            self.check('desktop_layout_has_no_document_overflow', page.evaluate('document.documentElement.scrollWidth <= window.innerWidth + 1'))
            page.locator('.dh-brand').focus(); page.keyboard.press('Tab')
            self.check('keyboard_navigation_reaches_visible_control', page.evaluate('document.activeElement !== document.body && document.activeElement.getBoundingClientRect().width > 0'))
            page.set_viewport_size({'width': 390, 'height': 844})
            page.reload(wait_until='domcontentloaded')
            self.check('narrow_390px_layout_has_no_document_overflow', page.evaluate('document.documentElement.scrollWidth <= window.innerWidth + 1'))
            self.screenshot(page, 'authenticated-overview-mobile.png')
            self.check('rendered_html_scripts_and_browser_storage_omit_private_values', True, **self.no_secret_values(page))
            self.stage = 'logout'
            page.get_by_role('button', name='Sign out', exact=True).click()
            expect(page.get_by_role('link', name=re.compile('Sign in to your workspace'))).to_be_visible()
            self.check('actual_site_logout_restores_private_anonymous_shell', page.locator('[data-total]').count() == 0)
            anonymous_download = context.request.get(urljoin(HOME, self.report['exports'][0]['download_href']))
            self.check('logged_out_export_download_is_denied', anonymous_download.status in (401, 403), http_status=anonymous_download.status)
            context.close(); browser.close()
            self.stage = 'fresh_browser_login'
            fresh_browser = playwright.chromium.launch(channel='msedge', headless=True)
            fresh = fresh_browser.new_context(viewport={'width': 1440, 'height': 1000})
            self.watch(fresh)
            fresh_page = fresh.new_page()
            self.login(fresh_page)
            self.check('fresh_browser_login_reopens_real_workspace', fresh_page.locator('[data-total="total_matches"]').inner_text().replace(',', '') == str(baseline['records']), previous_context_closed=True, imported_storage_state=False)
            fresh.close(); fresh_browser.close()
        current = self.api.snapshot()
        self.check('records_provider_settings_pairing_and_config_preserved', current == baseline, snapshot=current)
        self.check('no_blocking_browser_errors_or_unapproved_mutations', not self.report['page_errors'] and not self.report['forbidden_requests'], javascript_errors=len(self.report['page_errors']))
        self.report['passed'] = True
        self.report['stage'] = 'complete'
        self.report['finished_at'] = utc()
        self.save()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=BASE / 'browser-r1')
    parser.add_argument('--continue-from', type=Path)
    args = parser.parse_args()
    run = Acceptance(args.output, args.continue_from)
    try:
        run.run()
    except Exception as error:
        run.report['failure_class'] = type(error).__name__
        run.report['failure_stage'] = run.stage
        run.report['error_sha256'] = sha(str(error).encode())
        run.report['raw_error_or_credentials_logged'] = False
        run.report['finished_at'] = utc()
        run.save()
    print(json.dumps({'passed': run.report['passed'], 'checks': len(run.report['checks']),
                      'stage': run.report.get('failure_stage', 'complete'), 'report': str(run.output / 'verification.json')}))
    raise SystemExit(0 if run.report['passed'] else 1)


if __name__ == '__main__':
    main()
