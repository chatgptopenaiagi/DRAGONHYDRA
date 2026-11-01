"""Owned A8 installed-native shortcut, browsing, export and persistence acceptance.

The application pairs itself. This helper never inserts a token into the page,
opens a substitute browser, writes credentials, controls services or fetches a
provider feed. The coordinator separately authorizes its A8 service lifecycle.
"""
from __future__ import annotations

import argparse
import base64
import csv
from datetime import datetime, timezone
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import time
from urllib.parse import unquote, urlsplit
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT/'build/workstation/evidence/genesis-a8'
PROFILE = ROOT/'build/workstation/test-install/genesis-a8'
INSTALL = PROFILE/'application files'
STATE = PROFILE/'state data'
SERVICE = 'DragonhydraGenesisA8Test'
API = '/dragon/api/v1'


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def sha(data):
    return hashlib.sha256(data).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False,
                      separators=(',', ':'), allow_nan=False).encode()


def utc():
    return datetime.now(timezone.utc).isoformat()


class Journey:
    def __init__(self, args):
        self.args = args
        self.output = args.output.resolve()
        assert self.output.is_relative_to(EVIDENCE) and self.output != EVIDENCE and not self.output.exists(), 'Fresh A8 evidence directory required'
        assert not args.binary_override or args.phase == 'smoke', 'A binary override is only a pre-shipping smoke check'
        self.cfg = read(STATE/'workstation.json')
        assert self.cfg['install_root'] == str(INSTALL) and self.cfg['state_root'] == str(STATE) and self.cfg['service_name'] == SERVICE
        self.origin = 'http://127.0.0.1:'+str(self.cfg['api_port'])
        endpoint = read(STATE/'client/endpoint.json')
        assert endpoint['url'] == self.origin
        self.token = read(STATE/'client/local-session.json')['token']  # Redaction only; never used to authenticate this page.
        self.pairing_hash = sha((STATE/'client/local-session.json').read_bytes())
        self.binary = (args.binary_override or INSTALL/'client/DRAGONHYDRA-Client.exe').resolve()
        assert self.binary.is_file() and self.binary.is_relative_to(ROOT)
        self.native = load('a8_native_process_proof', ROOT/'tests/ui/native_webview_journey.py')
        self.native.BASE = EVIDENCE
        self.windows = self.native.Windows()
        self.windows.private_directory(self.output)
        self.links = load('a8_links_journey', ROOT/'tests/installation/genesis_a8_links.py')
        self.report = {'schema_version': 1, 'phase': args.phase, 'mode': args.mode, 'passed': False,
                       'started_at': utc(), 'scope': 'Actual installed Tauri native WebView2 with automatic application pairing',
                       'harness_sha256': sha(Path(__file__).read_bytes()),
                       'binary': str(self.binary), 'binary_sha256': sha(self.binary.read_bytes()),
                       'install_root': str(INSTALL), 'state_root': str(STATE), 'service_name': SERVICE,
                       'api_origin': self.origin, 'checks': [], 'processes': [],
                       'provider_api_acquisition_requested': False, 'model_requests_requested': False,
                       'credential_or_settings_writes_requested': False, 'service_controls_requested': False,
                       'blocked_requests': [], 'page_errors': []}
        self.page = None
        self.pw = None
        self.client = None
        self.launcher = None
        self.client_info = None

    def safe(self, value):
        return str(value).replace(self.token, '[REDACTED]').split('#token=')[0]

    def check(self, name, details=None, **values):
        self.report['checks'].append({'name': name, 'passed': True, **(details or {}), **values})

    def request(self, path, *, body=None, expected=200, binary=False):
        assert path.startswith(API+'/')
        result = self.page.evaluate('''async ({path,body,binary})=>{
          const options=body===null?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)};
          const response=await fetch(path,options);
          if(binary){const bytes=new Uint8Array(await response.arrayBuffer());let text='';for(const byte of bytes)text+=String.fromCharCode(byte);return {status:response.status,data:btoa(text)};}
          return {status:response.status,data:await response.json()};
        }''', {'path': path, 'body': body, 'binary': binary})
        assert result['status'] == expected, f'Actual native page request {path} returned HTTP{result["status"]}'
        return base64.b64decode(result['data']) if binary else result['data']

    def job(self, identifier, seconds=90):
        deadline = time.monotonic()+seconds
        while time.monotonic() < deadline:
            result = self.request(API+'/jobs/'+identifier)
            if result['status'] == 'succeeded':
                return result
            assert result['status'] not in ('failed', 'cancelled', 'interrupted'), 'Own durable job did not succeed'
            self.page.wait_for_timeout(150)
        raise TimeoutError('Own durable worker job timed out')

    def configured_shortcut(self):
        command = "[Environment]::GetFolderPath('CommonDesktopDirectory')"
        desktop = subprocess.check_output([r'C:\Program Files\PowerShell\7\pwsh.exe', '-NoProfile', '-Command', command], text=True).strip()
        shortcut = Path(desktop)/('DRAGONHYDRA Workstation - '+SERVICE+'.lnk')
        assert shortcut.is_file(), 'Official installed shortcut missing'
        # Inspect only this exact installed shortcut; no credentials are read.
        code = "$s=(New-Object -ComObject WScript.Shell).CreateShortcut($args[0]);@{target=$s.TargetPath;arguments=$s.Arguments}|ConvertTo-Json"
        # Structured stdin avoids embedding the shortcut path in shell source.
        code = "$v=[Console]::In.ReadToEnd()|ConvertFrom-Json;$s=(New-Object -ComObject WScript.Shell).CreateShortcut($v.path);@{target=$s.TargetPath;arguments=$s.Arguments}|ConvertTo-Json"
        probe = subprocess.run([r'C:\Program Files\PowerShell\7\pwsh.exe', '-NoProfile', '-Command', code],
                               input=json.dumps({'path': str(shortcut)}), capture_output=True, text=True, timeout=20, check=True)
        binding = json.loads(probe.stdout)
        assert Path(binding['target']).resolve() == INSTALL/'workstation/DragonhydraLauncher.exe'
        assert binding['arguments'] == '--state "'+str(STATE)+'"'
        return shortcut, binding

    def launch(self, index):
        from playwright.sync_api import sync_playwright, expect
        assert self.client_info is None
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        self.native.PORT = port
        profile = self.output/('profile-'+str(index))
        self.windows.private_directory(profile)
        baseline = set(self.windows.tree())
        environment = {key: value for key, value in os.environ.items()
                       if key.upper() not in ('PWDEBUG', 'DEBUG', 'DEBUG_FILE') and not key.upper().startswith('WEBVIEW2_')}
        environment['WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS'] = f'--remote-debugging-address=127.0.0.1 --remote-debugging-port={port}'
        environment['WEBVIEW2_USER_DATA_FOLDER'] = str(profile)
        launch = {'index': index, 'port': port, 'binary': str(self.binary)}
        if self.args.binary_override:
            launch['method'] = 'Rebuilt client pre-shipping explicit-state smoke; not shortcut execution'
            self.client = subprocess.Popen([str(self.binary), '--state', str(STATE/'client'), '--profile', str(profile)], env=environment,
                                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW)
        elif self.args.mode == 'bare':
            launch['method'] = 'Actual installed client EXE without state arguments'
            self.client = subprocess.Popen([str(self.binary)], env=environment, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                           creationflags=subprocess.CREATE_NO_WINDOW)
        else:
            shortcut, binding = self.configured_shortcut()
            launch.update(method='Actual official installed .lnk ShellExecute', shortcut=str(shortcut), binding=binding)
            previous = dict(os.environ)
            try:
                for name in tuple(os.environ):
                    if name.upper().startswith('WEBVIEW2_') or name.upper() in ('PWDEBUG', 'DEBUG', 'DEBUG_FILE'):
                        os.environ.pop(name, None)
                os.environ.update({key: environment[key] for key in ('WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS', 'WEBVIEW2_USER_DATA_FOLDER')})
                os.startfile(str(shortcut))
            finally:
                os.environ.clear()
                os.environ.update(previous)
        deadline = time.monotonic()+50
        while time.monotonic() < deadline:
            candidates = []
            for pid, row in self.windows.tree().items():
                if pid in baseline or row['name'].lower() != self.binary.name.lower():
                    continue
                try:
                    info = self.windows.process(pid)
                except (OSError, RuntimeError):
                    continue
                if Path(info['path']) == self.binary:
                    candidates.append(info)
            assert len(candidates) < 2, 'More than one newly launched exact A8 client; ownership ambiguous'
            if candidates:
                self.client_info = candidates[0]
                break
            time.sleep(.1)
        assert self.client_info is not None, 'Official launcher did not create its corresponding installed client'
        self.native.integrity_guard(self.client_info['integrity_class'])
        launch['client_process'] = self.client_info
        while time.monotonic() < deadline:
            listeners = self.windows.listeners()
            if listeners:
                self.native.listener_guard(listeners, self.windows.descendants(self.client_info['pid'])-{self.client_info['pid']})
                break
            time.sleep(.1)
        else:
            raise TimeoutError('No owned native WebView2 loopback CDP listener')
        launch['listeners'] = listeners
        # Child debug environment was restored before the Playwright driver.
        removed = {key: os.environ.pop(key) for key in tuple(os.environ) if key.upper() in ('PWDEBUG', 'DEBUG', 'DEBUG_FILE')}
        try:
            self.pw = sync_playwright().start()
        finally:
            os.environ.update(removed)
        self.browser = self.pw.chromium.connect_over_cdp('http://127.0.0.1:'+str(port), timeout=15000)
        assert len(self.browser.contexts) == 1
        self.context = self.browser.contexts[0]
        deadline = time.monotonic()+30
        while time.monotonic() < deadline:
            targets = [page for page in self.context.pages if page.url.startswith(self.origin+'/')]
            if len(targets) == 1:
                self.page = targets[0]
                break
            time.sleep(.1)
        assert self.page is not None, 'Native client did not target its configured installed server'
        self.page.set_default_timeout(20000)
        self.context.route('**/*', self.guard)
        self.page.on('pageerror', lambda error: self.report['page_errors'].append(self.safe(error)[:500]))
        expect(self.page.locator('#service-state')).to_have_text('Server ready · sqlite', timeout=30000)
        assert '#token=' not in self.page.url
        assert self.page.locator('#login-form').is_hidden(), 'Pairing UI still visible'
        assert self.page.evaluate('Boolean(window.chrome?.webview && window.__TAURI_INTERNALS__)')
        health = self.request(API+'/health/ready')
        assert health['status'] == 'ready'
        launch['route'] = self.native.safe_url(self.page.url)
        launch['automatic_pairing'] = True
        self.report['processes'].append(launch)
        self.check('native_startup_automatic_pairing_'+str(index), health=health, launch=launch)

    def guard(self, route):
        request = route.request
        parsed = urlsplit(request.url)
        path = unquote(parsed.path)
        opener = parsed.hostname == 'ipc.localhost' and path == '/plugin:opener|open_url' and request.method in ('POST', 'OPTIONS')
        same = parsed.scheme+'://'+parsed.netloc == self.origin
        own_post = path in (API+'/session', API+'/exports') or re.fullmatch(re.escape(API)+r'/matches/[a-f0-9]{64}/explanations', path)
        if opener or parsed.scheme in ('data', 'blob') or (same and (request.method in ('GET', 'HEAD') or request.method == 'POST' and own_post)):
            route.continue_()
        else:
            self.report['blocked_requests'].append({'method': request.method, 'origin': parsed.scheme+'://'+parsed.netloc, 'path': path})
            route.abort('blockedbyclient')

    def snapshot(self, exports=None):
        items, offset, total = [], 0, None
        while total is None or offset < total:
            page = self.request(API+f'/matches?limit=200&offset={offset}')
            total = page['total']
            items.extend(page['items'])
            offset += 200
        assert total == len(items) and total > 0
        connections = self.request(API+'/connections')
        return {'records': total, 'all_match_presentations_sha256': sha(canonical(sorted(items, key=lambda row: row['id']))),
                'match_identifiers_sha256': sha(canonical(sorted(row['id'] for row in items))),
                'connection_settings_sha256': self.links.settings_fingerprint(connections),
                'pairing_file_sha256': sha((STATE/'client/local-session.json').read_bytes()),
                'exports': exports or []}

    def administration(self):
        helpers = self.links.load_windows_helpers()
        browser = helpers.default_browser()
        pattern = re.compile(r'DRAGONHYDRA|Joomla|Administration', re.I)
        previous = helpers.browser_window_receipts(self.windows, browser, pattern)
        original = self.page.url
        system = self.request(API+'/system')
        expected = 'http://127.0.0.1:'+str(self.cfg['web_port'])+'/administrator/'
        assert system['administration_url'] == expected
        self.page.get_by_role('button', name='Administration', exact=True).click()
        deadline = time.monotonic()+30
        receipts = []
        while time.monotonic() < deadline:
            receipts = helpers.browser_window_receipts(self.windows, browser, pattern)
            if receipts and receipts != previous:
                break
            self.page.wait_for_timeout(100)
        assert receipts and receipts != previous, 'Administration did not reach the registered default browser'
        assert self.page.url == original
        actual = self.windows.process(self.client_info['pid'])
        assert actual['creation_filetime'] == self.client_info['creation_filetime']
        self.check('native_administration_default_browser_open', expected_url=expected,
                   default_browser=browser, browser_windows_before=previous,
                   browser_window_receipts=receipts, native_route_unchanged=True)

    def export_bytes(self, job, kind):
        result = job['result']
        data = self.request(result['download_url'], binary=True)
        assert sha(data) == result['sha256'] and len(data) == result['bytes']
        if kind == 'json':
            assert json.loads(data)['match']['id'] == self.selected['id']
        elif kind == 'csv':
            rows = list(csv.reader(io.StringIO(data.decode('utf-8-sig'))))
            assert rows and any(self.selected['id'] in row for row in rows)
        else:
            with ZipFile(io.BytesIO(data)) as book:
                assert b'name="Match"' in book.read('xl/workbook.xml')
                assert b'name="Metadata"' in book.read('xl/workbook.xml')
                assert self.selected['id'].encode() in book.read('xl/worksheets/sheet1.xml')
        target = self.output/'exports'/result['filename']
        target.parent.mkdir(exist_ok=True)
        target.write_bytes(data)
        return {'job_id': job['id'], 'format': kind, 'filename': result['filename'],
                'download_url': result['download_url'], 'bytes': len(data), 'sha256': sha(data)}

    def full(self):
        from playwright.sync_api import expect
        self.page.get_by_role('link', name='Today', exact=True).click()
        self.page.get_by_role('button', name='Browse retained matches', exact=True).click()
        expect(self.page.get_by_role('heading', name='Retained matches', exact=True)).to_be_visible()
        before = self.snapshot()
        assert before['records'] == 760, 'Expected bundled retained fixture inventory differs'
        self.check('football_library_native_navigation', record_count=before['records'], displayed_cards=self.page.locator('.match-card').count())
        finished = self.request(API+'/matches?status=finished&limit=1')['items']
        assert finished
        self.selected = finished[0]
        self.page.locator('#match-competition').select_option(self.selected['competition_id'])
        self.page.locator('#match-search').fill(self.selected['home']['name']+' '+self.selected['away']['name'])
        self.page.get_by_role('button', name='Apply filters', exact=True).click()
        self.page.locator('[data-match-id="'+self.selected['id']+'"]').click()
        expect(self.page.locator('.match-hero')).to_be_visible()
        self.check('retained_finished_match_opened', match=self.selected)
        self.page.locator('[data-team-id]').first.click()
        expect(self.page.get_by_role('heading', name='Recent form', exact=True)).to_be_visible()
        assert self.page.locator('.form-token').count() > 0
        self.check('team_recent_form_native_navigation', form_entries=self.page.locator('.form-token').count())
        self.page.get_by_role('button', name='← Return to selected match', exact=True).click()
        self.page.get_by_role('button', name='Open standings', exact=True).click()
        expect(self.page.locator('tbody tr')).to_have_count(20)
        standings = self.request(API+'/competitions/'+self.selected['competition_id']+'/standings')
        assert len(standings['items']) == 20 and sum(item['played'] for item in standings['items']) > 0
        self.check('standings_native_navigation_and_calculation', teams=20, items_sha256=sha(canonical(standings['items'])))
        self.page.get_by_role('button', name='← Return to selected match', exact=True).click()
        self.page.get_by_role('tab', name='Analysis', exact=True).click()
        expect(self.page.get_by_role('heading', name='Model probabilities', exact=True)).to_be_visible()
        prediction = self.request(API+'/matches/'+self.selected['id']+'/predictions')
        self.check('sports_analysis_structured_result', result=prediction)
        with self.page.expect_response(lambda r: r.request.method == 'POST' and r.url.endswith('/explanations')) as response:
            self.page.get_by_role('button', name='Explain this match', exact=True).click()
        queued = response.value.json()
        explanation = self.job(queued['id'])
        assert explanation['result']['kind'] == 'deterministic'
        expect(self.page.locator('#explanation-result a[href*="/evidence/"]')).to_be_visible()
        self.check('deterministic_analysis_native_job', job_id=queued['id'], result=explanation['result'])
        self.page.get_by_role('tab', name='Overview', exact=True).click()
        with self.page.expect_response(lambda r: r.request.method == 'POST' and r.url.endswith('/exports')) as response:
            self.page.get_by_role('button', name='Export to Excel', exact=True).click()
        excel = self.job(response.value.json()['id'])
        expect(self.page.get_by_role('link', name='Download Excel report', exact=True)).to_be_visible()
        exports = [self.export_bytes(excel, 'xlsx')]
        for kind in ('json', 'csv'):
            queued = self.request(API+'/exports', body={'match_id': self.selected['id'], 'format': kind}, expected=202)
            exports.append(self.export_bytes(self.job(queued['id']), kind))
        self.check('actual_json_csv_excel_export_files', exports=exports, scope='Native Excel control plus authenticated native-page HTTP file downloads; no native SaveAs dialog')
        self.links.verify_connection_links(self.page, self.windows, self.report,
                                           on_check=lambda name, result: self.check(name, result))
        after = self.snapshot(exports)
        for key in ('records', 'all_match_presentations_sha256', 'match_identifiers_sha256', 'connection_settings_sha256', 'pairing_file_sha256'):
            assert before[key] == after[key], 'Retained state changed during bounded native journey: '+key
        self.report['selected_match'] = self.selected
        self.report['persistence_snapshot'] = after
        self.cleanup()
        self.launch(2)
        self.verify_persistence(self.report)

    def verify_persistence(self, baseline):
        before = baseline['persistence_snapshot']
        after = self.snapshot(before['exports'])
        for key in ('records', 'all_match_presentations_sha256', 'match_identifiers_sha256', 'connection_settings_sha256', 'pairing_file_sha256'):
            assert before[key] == after[key], 'State changed after restart: '+key
        for exported in before['exports']:
            job = self.request(API+'/jobs/'+exported['job_id'])
            assert job['status'] == 'succeeded'
            assert sha(self.request(exported['download_url'], binary=True)) == exported['sha256']
        selected = baseline['selected_match']
        assert self.request(API+'/matches/'+selected['id']) == selected
        self.report['persistence_snapshot'] = after
        self.report['selected_match'] = selected
        self.check('restart_retains_matches_pairing_settings_durable_jobs_and_exports', records=after['records'], exports=len(before['exports']))

    def cleanup(self):
        if self.client_info is not None:
            self.report.setdefault('cleanup', []).append({'pid': self.client_info['pid'],
                'method': 'Exact owned image and creation-time handle validation',
                'terminated': self.windows.terminate_owned(self.client_info)})
            self.client_info = None
        if self.pw is not None:
            self.pw.stop()
            self.pw = None
        self.client = None
        self.page = None

    def run(self):
        try:
            self.launch(1)
            if self.args.phase == 'full':
                self.full()
            elif self.args.phase == 'persistence':
                assert self.args.baseline and self.args.baseline.is_file()
                baseline = read(self.args.baseline)
                assert baseline['passed']
                self.verify_persistence(baseline)
            else:
                self.report['persistence_snapshot'] = self.snapshot()
                self.check('retained_inventory_accessible_after_automatic_pairing', records=self.report['persistence_snapshot']['records'])
                if self.args.administration:
                    self.administration()
            assert sha((STATE/'client/local-session.json').read_bytes()) == self.pairing_hash
            self.report['pairing_metadata_unchanged'] = True
            self.report['passed'] = True
        except Exception as error:
            self.report['error'] = {'type': type(error).__name__, 'message': self.safe(error)}
        finally:
            try:
                self.cleanup()
            except Exception as error:
                self.report['cleanup_error'] = self.safe(error)
                self.report['passed'] = False
            self.report['finished_at'] = utc()
            temporary = self.output/'verification.json.tmp'
            temporary.write_text(json.dumps(self.report, indent=2, ensure_ascii=False)+'\n', encoding='utf-8')
            temporary.replace(self.output/'verification.json')
        print(json.dumps({'passed': self.report['passed'], 'checks': len(self.report['checks']),
                          'error': self.report.get('error'), 'report': str(self.output/'verification.json')}))
        return 0 if self.report['passed'] else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--phase', choices=['smoke', 'full', 'persistence'], default='smoke')
    parser.add_argument('--mode', choices=['shortcut', 'bare'], default='shortcut')
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--binary-override', type=Path)
    parser.add_argument('--baseline', type=Path)
    parser.add_argument('--administration', action='store_true', help='In smoke mode, test the actual Administration button and default-browser handoff')
    args = parser.parse_args()
    return Journey(args).run()


if __name__ == '__main__':
    raise SystemExit(main())
