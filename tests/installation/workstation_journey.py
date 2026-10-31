"""Exercise one isolated, installed Windows workstation, never the live product.

Run with the existing project Playwright environment after the installer has
finished. Service restart is permitted only beneath build/workstation/test-install
and only after the registered executable and state arguments have been checked.
"""
from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
import time
import traceback
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlsplit
from urllib.request import Request, urlopen
from uuid import uuid4
from zipfile import ZipFile


ROOT = Path(__file__).resolve().parents[2]
API = '/dragon/api/v1'


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def python_modules(pid):
    class Entry(ctypes.Structure):
        _fields_ = [('dwSize', wintypes.DWORD), ('th32ModuleID', wintypes.DWORD),
                    ('th32ProcessID', wintypes.DWORD), ('GlblcntUsage', wintypes.DWORD),
                    ('ProccntUsage', wintypes.DWORD), ('modBaseAddr', ctypes.POINTER(ctypes.c_byte)),
                    ('modBaseSize', wintypes.DWORD), ('hModule', wintypes.HMODULE),
                    ('szModule', wintypes.WCHAR * 256), ('szExePath', wintypes.WCHAR * 260)]
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    kernel.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel.Module32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(Entry)]
    kernel.Module32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(Entry)]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.CreateToolhelp32Snapshot(0x08 | 0x10, pid)
    if handle == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    entry = Entry()
    entry.dwSize = ctypes.sizeof(entry)
    modules = []
    try:
        okay = kernel.Module32FirstW(handle, ctypes.byref(entry))
        if not okay:
            raise ctypes.WinError(ctypes.get_last_error())
        while okay:
            if entry.szModule.lower().startswith('python'):
                modules.append(entry.szExePath)
            okay = kernel.Module32NextW(handle, ctypes.byref(entry))
    finally:
        kernel.CloseHandle(handle)
    return modules


class Journey:
    def __init__(self, args):
        if sys.flags.optimize:
            raise RuntimeError('Acceptance must run with Python assertions enabled; remove PYTHONOPTIMIZE/-O.')
        self.args = args
        self.root = args.workspace_root.resolve()
        allowed = self.root / 'build/workstation/test-install'
        self.install, self.state, self.output = args.install_root.resolve(), args.state_root.resolve(), args.output.resolve()
        for path in (self.install, self.state):
            assert path.is_relative_to(allowed) and path != allowed, 'Only isolated workstation test installations are accepted'
        assert not self.install.is_relative_to(self.state) and not self.state.is_relative_to(self.install), 'Separate binaries and mutable state are required'
        assert self.output.is_relative_to(self.root / 'build/workstation/evidence'), 'Receipts must stay in workstation evidence'
        assert re.fullmatch(r'Dragonhydra[A-Za-z0-9_-]{0,60}', args.service_name), 'Invalid exact test service name'
        self.output.mkdir(parents=True, exist_ok=True)
        self.secrets = []
        self.commands = []
        self.checks = []
        self.record = {'schema_version': 1, 'started_at': self.now(), 'passed': False,
                       'scope': 'Isolated installed workstation on current Windows host; no clean machine or reboot claim',
                       'environment': {'os': platform.platform(), 'architecture': platform.machine(),
                                       'harness_python': platform.python_version(), 'harness_interpreter': sys.executable},
                       'install_root': str(self.install), 'state_root': str(self.state),
                       'service_name': args.service_name, 'checks': self.checks,
                       'not_run': ['Clean-machine installation', 'Windows reboot', 'SQLite-to-MariaDB canonical migration',
                                   'Real live-provider import', 'Local LLM inference',
                                   'Joomla reader-role account ACL on this installed instance',
                                   'Native download SaveAs dialog; actual workbook download exercised in installed dashboard browser']}
        self.cfg = read_json(self.state / 'workstation.json')
        for key, value in self.cfg.items():
            if any(word in key.lower() for word in ('password', 'secret', 'token')) and isinstance(value, str):
                self.secrets.append(value)
        assert Path(self.cfg['install_root']).resolve() == self.install
        assert Path(self.cfg['state_root']).resolve() == self.state
        assert self.cfg['service_name'] == args.service_name
        self.load_endpoint()

    @staticmethod
    def now():
        return datetime.now(timezone.utc).isoformat()

    def redact(self, value):
        text = str(value)
        for secret in sorted(set(self.secrets), key=len, reverse=True):
            if secret:
                text = text.replace(secret, '[REDACTED]')
        return text

    def check(self, group, name, **details):
        self.checks.append({'group': group, 'name': name, 'passed': True, **details})
        print(json.dumps({'passed': name, 'group': group}), flush=True)

    def load_endpoint(self):
        self.endpoint = read_json(self.state / 'kernel/endpoint.json')
        self.base = self.endpoint['url'].rstrip('/')
        # The server's original token deliberately grants only its service identity
        # and SYSTEM access. Exercise the same owner-readable pairing copy as the
        # installed client; never relax or take ownership of the kernel ACL.
        self.token = read_json(self.state / 'client/local-session.json')['token']
        self.secrets.append(self.token)
        assert self.base == f"http://127.0.0.1:{self.cfg['api_port']}"
        assert self.cfg['api_base'].rstrip('/') == self.base + API
        self.web = f"http://127.0.0.1:{self.cfg['web_port']}"
        assert read_json(self.state / 'client/endpoint.json')['url'].rstrip('/') == self.base
        assert isinstance(self.token, str) and len(self.token) >= 20, 'Owner-readable client pairing is missing'

    def run(self, command, *, stdin=None, timeout=90):
        started = time.monotonic()
        result = subprocess.run(command, input=stdin, text=True, encoding='utf-8', errors='replace',
                                capture_output=True, timeout=timeout, cwd=self.root)
        self.commands.append({'argv': [self.redact(x) for x in command], 'exit_code': result.returncode,
                              'duration_seconds': round(time.monotonic() - started, 3),
                              'stdout': self.redact(result.stdout), 'stderr': self.redact(result.stderr)})
        assert result.returncode == 0, self.redact(result.stderr or result.stdout)[-1500:]
        return result.stdout

    def powershell(self, script, values=None, timeout=90):
        # Inputs travel as JSON on stdin, never interpolated into shell source.
        source = "$ErrorActionPreference='Stop';$v=[Console]::In.ReadToEnd()|ConvertFrom-Json;" + script
        return self.run(['pwsh', '-NoLogo', '-NoProfile', '-NonInteractive', '-Command', source],
                        stdin=json.dumps(values or {}), timeout=timeout)

    def service(self):
        script = """
        $s=Get-CimInstance Win32_Service -Filter (\"Name='\"+$v.name+\"'\");
        if(-not $s){throw 'Exact owned service missing.'};
        $p=Get-CimInstance Win32_Process -Filter ('ProcessId='+$s.ProcessId);
        $ports=@(Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue|Where-Object {$_.LocalPort -in $v.ports}|ForEach-Object {
          $q=Get-CimInstance Win32_Process -Filter ('ProcessId='+$_.OwningProcess);
          @{port=$_.LocalPort;address=$_.LocalAddress;pid=$_.OwningProcess;executable=$q.ExecutablePath;created=[string]$q.CreationDate}
        });
        @{name=$s.Name;state=$s.State;path=$s.PathName;account=$s.StartName;pid=$s.ProcessId;start_mode=$s.StartMode;executable=$p.ExecutablePath;listeners=$ports}|ConvertTo-Json -Depth 5
        """
        ports = [self.cfg[k] for k in ('api_port', 'web_port', 'database_port')] + [18732, 18733, 18734]
        if self.args.expected_conflict_port:
            ports.append(self.args.expected_conflict_port)
        row = json.loads(self.powershell(script, {'name': self.args.service_name, 'ports': ports}))
        expected = f'"{self.install / "workstation/DragonhydraService.exe"}" --state "{self.state}" --name {self.args.service_name}'
        assert row['path'].casefold() == expected.casefold(), 'Service ImagePath ownership mismatch; no restart attempted'
        assert row['state'] == 'Running'
        assert Path(row['executable']).resolve() == self.install / 'workstation/DragonhydraService.exe'
        assert row['account'].casefold() in ('nt authority\\localservice', 'localservice'), 'Unexpected service identity'
        return row

    def call(self, method, path, body=None, *, auth=True, key=None, origin=None):
        headers = {'Content-Type': 'application/json'}
        if auth:
            headers['Authorization'] = 'Bearer ' + self.token
        if key:
            headers['Idempotency-Key'] = key
        if origin:
            headers['Origin'] = origin
        target = self.base + (path if path.startswith(API) else API + path)
        request = Request(target, None if body is None else json.dumps(body).encode(), headers, method=method)
        try:
            with urlopen(request, timeout=15) as response:
                raw = response.read()
                return response.status, json.loads(raw) if 'json' in response.headers.get('Content-Type', '') else raw
        except HTTPError as exc:
            raw = exc.read()
            return exc.code, json.loads(raw) if 'json' in exc.headers.get('Content-Type', '') else raw

    def job(self, identifier, seconds=75):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            code, row = self.call('GET', '/jobs/' + identifier)
            assert code == 200
            if row['status'] == 'succeeded':
                return row
            assert row['status'] not in ('failed', 'cancelled', 'interrupted'), self.redact(row.get('error'))
            time.sleep(.2)
        raise AssertionError('Installed durable job exceeded verification deadline')

    def workbook(self, data, filename):
        with ZipFile(io.BytesIO(data)) as book:
            assert b'name="Match"' in book.read('xl/workbook.xml')
            assert b'name="Metadata"' in book.read('xl/workbook.xml')
            assert self.match_id.encode() in book.read('xl/worksheets/sheet1.xml')
        path = self.output / filename
        path.write_bytes(data)
        return {'filename': filename, 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}

    def inspect(self):
        self.before = self.service()
        self.check('installation', 'exact-owned-service-running-as-LocalService', service_pid=self.before['pid'], start_mode=self.before['start_mode'])
        for key, directory in [('api_port', 'server'), ('web_port', 'web/apache'), ('database_port', 'web/mariadb')]:
            rows = [r for r in self.before['listeners'] if r['port'] == self.cfg[key]]
            assert rows and all(r['address'] in ('127.0.0.1', '::1') for r in rows), 'Packaged component must bind privately'
            assert all(Path(r['executable']).resolve().is_relative_to(self.install / directory) for r in rows)
        self.check('installation', 'private-product-processes-own-selected-loopback-ports', ports={k: self.cfg[k] for k in ('api_port', 'web_port', 'database_port')})
        if self.args.expected_conflict_port:
            self.blocker = [r for r in self.before['listeners'] if r['port'] == self.args.expected_conflict_port]
            assert self.blocker and self.cfg['api_port'] != self.args.expected_conflict_port
            self.check('installation', 'occupied-preferred-port-preserved', occupied_port=self.args.expected_conflict_port,
                       selected_api_port=self.cfg['api_port'], blocker_pids=sorted({r['pid'] for r in self.blocker}))
        modules = python_modules(self.endpoint['pid'])
        assert modules and all(Path(m).resolve().is_relative_to(self.install / 'server') for m in modules)
        self.check('installation', 'actual-loaded-private-python-runtime', modules=[str(Path(m).relative_to(self.install)) for m in modules])
        status = read_json(self.state / 'status.json')
        assert status['stage'] == 'ready' and status['backend'] == 'sqlite'
        assert status['admin_database'] == 'MariaDB'
        self.check('installation', 'explicit-kernel-sqlite-and-separate-MariaDB-administration', optional_ai=status['optional_ai'])
        php = self.install / 'web/php/php.exe'
        hook = self.install / 'web/manage.php'
        web_status = json.loads(self.run([str(php), '-c', str(self.state / 'web-config/php.ini'),
                                         str(hook), str(self.state / 'workstation.json'), 'status']))
        assert web_status['site_configured'] and web_status['php_thread_safe']
        assert web_status['extension']['identity'] == 'com_dragonhydra' and web_status['extension']['enabled']
        assert web_status['api_base'] == self.cfg['api_base']
        assert web_status['sports_database_backend'] == 'sqlite' and not web_status['reserved_core_authority_active']
        self.record['web_stack'] = web_status
        self.check('installation', 'installed-private-PHP-MariaDB-Joomla-extension',
                   php_version=web_status['php_version'], database_version=web_status['database_version'],
                   extension=web_status['extension'])
        for component, binary in [('server', 'server/DRAGONHYDRA-Server.exe'), ('client', 'client/DRAGONHYDRA-Client.exe'),
                                  ('launcher', 'workstation/DragonhydraLauncher.exe'), ('service', 'workstation/DragonhydraService.exe')]:
            path = self.install / binary
            self.record.setdefault('installed_binaries', {})[component] = {'path': binary, 'bytes': path.stat().st_size, 'sha256': digest(path)}
        with urlopen(self.web + '/', timeout=15) as response:
            assert response.status == 200 and b'<html' in response.read().lower()
        self.check('installation', 'installed-Joomla-frontend-HTTP-200')

    def api(self):
        code, health = self.call('GET', '/health/ready')
        assert code == 200 and health['backend'] == 'sqlite'
        self.record['kernel_build'] = health
        assert self.call('GET', '/health/ready', auth=False)[0] == 401
        assert self.call('POST', '/session', {'token': '日' * 25}, auth=False)[0] == 401
        assert self.call('POST', '/connections/openfootball/sync', {}, origin='https://invalid.example')[0] == 403
        self.check('api', 'authenticated-health-rejected-token-and-browser-origin')
        self.idempotency = 'installed-workstation-test-' + uuid4().hex
        code, row = self.call('POST', '/connections/openfootball/sync', {}, key=self.idempotency)
        assert code == 202
        self.import_id = row['id']
        imported = self.job(self.import_id)
        assert imported['result']['record_count'] == 760
        assert self.call('POST', '/connections/openfootball/sync', {}, key=self.idempotency)[1]['id'] == self.import_id
        matches = self.call('GET', '/matches?limit=1')[1]
        assert matches['total'] == 760
        self.selected = matches['items'][0]
        self.match_id = self.selected['id']
        self.record['canonical_match'] = self.selected
        self.check('api', 'retained-public-760-record-import-and-idempotent-job', job_id=self.import_id, record_count=760, source='packaged retained OpenFootball data; not live acquisition')
        assert self.call('GET', '/matches/' + self.match_id)[1]['id'] == self.match_id
        assert self.call('GET', '/teams/' + self.selected['home']['id'])[0] == 200
        standings = self.call('GET', '/competitions/' + self.selected['competition_id'] + '/standings')
        assert standings[0] == 200 and not standings[1]['official']
        assert self.call('GET', '/matches/' + self.match_id + '/predictions')[0] == 200
        self.check('api', 'same-canonical-match-team-reconstructed-standings-and-models', match_id=self.match_id)
        code, submitted = self.call('POST', '/matches/' + self.match_id + '/explanations', {})
        assert code == 202
        explained = self.job(submitted['id'])['result']
        assert explained['kind'] == 'deterministic' and explained['evidence']
        citation = self.call('GET', explained['evidence'][0]['url'])
        assert citation[0] == 200 and citation[1]['evidence_id'] == explained['evidence'][0]['id']
        self.check('api', 'deterministic-explanation-cites-retained-source-record', evidence_id=citation[1]['evidence_id'], llm_generated=False)
        code, submitted = self.call('POST', '/exports', {'match_id': self.match_id, 'format': 'xlsx'})
        assert code == 202
        exported = self.job(submitted['id'])['result']
        code, workbook = self.call('GET', exported['download_url'])
        assert code == 200
        self.check('api', 'installed-worker-real-XLSX-export', **self.workbook(workbook, 'api-selected-match.xlsx'))
        system = self.call('GET', '/system')[1]
        assert system['administration_url'] == self.web + '/administrator/'
        self.check('api', 'installed-client-administration-endpoint-configured', administration_url=system['administration_url'])

    def native(self):
        path = self.output / 'native-client.json'
        script = self.root / 'tests/installation/workstation_native.ps1'
        label = 'Open match: ' + self.selected['home']['name'] + ' versus ' + self.selected['away']['name']
        self.run(['pwsh', '-NoLogo', '-NoProfile', '-File', str(script), '-InstallRoot', str(self.install),
                  '-StateRoot', str(self.state), '-ServiceName', self.args.service_name, '-Output', str(path),
                  '-ExpectedMatchId', self.match_id, '-ExpectedMatchLabel', label], timeout=330)
        receipt = read_json(path)
        assert receipt['passed'], receipt.get('error')
        assert receipt.get('client_exit') == 'graceful', 'Installed native client must close normally'
        self.check('native', 'installed-launcher-native-human-journey', receipt=path.name, native_check_groups=len(receipt['checks']))

    def browser(self):
        from playwright.sync_api import sync_playwright, expect, TimeoutError as PlaywrightTimeout
        errors = []
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel='msedge', headless=True)
            context = browser.new_context(viewport={'width': 1440, 'height': 1050}, accept_downloads=True)
            page = context.new_page()
            page.on('pageerror', lambda exc: errors.append(str(exc)))
            try:
                page.goto(self.base + '/#token=' + self.token, wait_until='domcontentloaded')
                expect(page.get_by_role('heading', name='Today’s football')).to_be_visible(timeout=30000)
                assert '#token=' not in page.url
                page.get_by_role('button', name='Browse retained matches', exact=True).first.click()
                page.locator('.match-card[data-match-id="' + self.match_id + '"]').click()
                expect(page.get_by_role('heading', name='Match overview')).to_be_visible()
                original = page.url
                page.locator('.team-button').first.click()
                expect(page.get_by_role('heading', name='Recent form', exact=True)).to_be_visible()
                page.get_by_role('button', name='← Return to selected match').click()
                page.get_by_role('button', name='Open standings').click()
                expect(page.get_by_text('RECONSTRUCTED', exact=True)).to_be_visible()
                page.get_by_role('button', name='← Return to selected match').click()
                assert page.url == original
                self.check('browser', 'installed-dashboard-match-team-standings-return-context', match_id=self.match_id)
                page.get_by_role('tab', name='Lineups', exact=True).click()
                expect(page.get_by_text('This source does not provide this match context. Missing data does not mean zero.')).to_be_visible()
                page.get_by_role('tab', name='Odds & chart').click()
                expect(page.get_by_role('heading', name='Compatible odds & history')).to_be_visible()
                page.get_by_role('tab', name='Analysis', exact=True).click()
                page.get_by_role('button', name='Explain this match').click()
                expect(page.get_by_text('DETERMINISTIC EVIDENCE SUMMARY', exact=True)).to_be_visible(timeout=75000)
                with context.expect_page() as opened:
                    page.locator('.explanation-citation').first.click()
                cited = opened.value
                cited.wait_for_load_state('domcontentloaded')
                assert json.loads(cited.locator('body').inner_text())['evidence_id']
                cited.close()
                page.screenshot(path=str(self.output / 'dashboard-analysis.png'), full_page=True)
                self.check('browser', 'truthful-provider-gaps-model-explanation-and-open-evidence')
                page.get_by_role('tab', name='Overview', exact=True).click()
                page.get_by_role('button', name='Export to Excel', exact=True).click()
                expect(page.get_by_text('Report ready', exact=True)).to_be_visible(timeout=75000)
                with page.expect_download() as captured:
                    page.get_by_role('link', name='Download Excel report').click()
                download = captured.value
                file = self.output / 'browser-selected-match.xlsx'
                download.save_as(str(file))
                self.check('browser', 'visible-export-download-saves-actual-workbook', **self.workbook(file.read_bytes(), file.name))
                page.get_by_role('link', name='Today', exact=True).click()
                page.get_by_role('button', name='Browse retained matches', exact=True).first.click()
                expect(page.get_by_role('heading', name='Retained matches', exact=True)).to_be_visible()
                expect(page.locator('.match-card').first).to_be_visible()
                pattern = '**/dragon/api/v1/matches?*'
                page.route(pattern, lambda route: route.fulfill(status=503, content_type='application/json', body=json.dumps({'error': {'code': 'INSTALL_TEST_OUTAGE', 'message': 'Isolated verification outage; retry is available.'}})))
                page.get_by_role('button', name='Refresh current view').click()
                expect(page.get_by_text('Isolated verification outage; retry is available.')).to_be_visible()
                page.unroute(pattern)
                page.get_by_role('button', name='Retry', exact=True).click()
                expect(page.locator('.match-card').first).to_be_visible()
                self.check('browser', 'isolated-browser-only-outage-visible-retry', application_services_interrupted=False)
                with context.expect_page() as opened:
                    page.get_by_role('button', name='Administration', exact=True).first.click()
                administration = opened.value
                # The newly created popup can initially be about:blank; waiting
                # on that document's load is not proof its target has navigated.
                administration.wait_for_url(re.compile(re.escape(self.web) + r'/administrator(?:/|\?|$).*'),
                                             wait_until='domcontentloaded', timeout=30000)
                assert administration.url.startswith(self.web + '/administrator/')
                administration.close()
                self.check('browser', 'administration-control-opens-installed-Joomla')

                admin_context = browser.new_context(viewport={'width': 1440, 'height': 1050}, reduced_motion='reduce')
                admin = admin_context.new_page()
                admin.on('pageerror', lambda exc: errors.append(str(exc)))
                component = self.web + '/administrator/index.php?option=com_dragonhydra'
                admin.goto(component)
                expect(admin.locator('#mod-login-username')).to_be_visible()
                admin.locator('#mod-login-username').fill(self.cfg['admin_user'])
                admin.locator('#mod-login-password').fill(self.cfg['admin_password'])
                admin.get_by_role('button', name='Log in', exact=True).click()
                expect(admin.locator('#mod-login-username')).not_to_be_visible(timeout=30000)
                hide_tour = admin.get_by_role('button', name='Hide Forever', exact=True)
                try:
                    hide_tour.wait_for(state='visible', timeout=5000)
                    hide_tour.click()
                    hide_tour.wait_for(state='hidden')
                except PlaywrightTimeout:
                    pass
                admin.goto(component + '&section=sources')
                expect(admin.get_by_role('heading', name='Data sources', exact=True)).to_be_visible()
                assert 'BRIDGE_NOT_CONFIGURED' not in admin.inner_text('body')
                assert admin_context.request.post(component + '&task=actions.sync', form={}).status == 403
                self.check('joomla', 'installed-extension-real-administrator-login-signed-source-status-and-CSRF')
                admin.get_by_role('button', name='Import public results', exact=True).click()
                expect(admin.get_by_role('heading', name='Import job', exact=True)).to_be_visible()
                joomla_job = parse_qs(urlsplit(admin.url).query)['job_id'][0]
                deadline = time.monotonic() + 75
                while time.monotonic() < deadline and not admin.get_by_role('link', name='View imported matches', exact=True).is_visible():
                    assert not admin.get_by_text('failed', exact=True).is_visible()
                    time.sleep(.3)
                    admin.get_by_role('link', name='Refresh job status', exact=True).click()
                expect(admin.get_by_role('link', name='View imported matches', exact=True)).to_be_visible()
                assert self.job(joomla_job)['result']['record_count'] == 760
                admin.get_by_role('link', name='View imported matches', exact=True).click()
                match = admin.locator('.dragonhydra-administration tbody th a').filter(has_text=self.selected['home']['name'] + ' — ' + self.selected['away']['name']).first
                expect(match).to_be_visible()
                assert parse_qs(urlsplit(match.get_attribute('href')).query)['match_id'][0] == self.match_id
                match.click()
                expect(admin.get_by_role('heading', name=self.selected['home']['name'] + ' — ' + self.selected['away']['name'], exact=True)).to_be_visible()
                assert admin.locator('a[href*="#match/"]').get_attribute('href').endswith('/#match/' + self.match_id)
                admin.screenshot(path=str(self.output / 'joomla-canonical-match.png'), full_page=True)
                self.check('joomla', 'typed-import-job-displays-same-canonical-match-as-native-client', job_id=joomla_job, match_id=self.match_id)
                for section, heading in [('odds', 'Odds administration'), ('models', 'AI and models'), ('research', 'Research'), ('databases', 'Database connections'), ('system', 'System')]:
                    admin.goto(component + '&section=' + section)
                    expect(admin.get_by_role('heading', name=heading, exact=True)).to_be_visible()
                    assert 'The kernel request could not complete' not in admin.inner_text('body')
                self.check('joomla', 'administrator-sections-open-with-shared-kernel')
                admin_context.close()
                assert not errors, self.redact(errors)
            except Exception:
                for name, target in [('dashboard-failure.png', page), ('joomla-failure.png', locals().get('admin'))]:
                    if target and not target.is_closed():
                        try:
                            # Password fields are never captured; conceal them if a login fails.
                            target.locator('input[type=password]').evaluate_all("nodes => nodes.forEach(n => n.value = '')")
                            target.screenshot(path=str(self.output / name), full_page=True)
                        except Exception:
                            pass
                raise
            finally:
                context.close()
                browser.close()

    def restart(self):
        before_token = self.token
        before_pid = self.endpoint['pid']
        # Revalidate every ownership argument immediately before the only service mutation.
        current = self.service()
        expected = current['path']
        source = """
        $s=Get-CimInstance Win32_Service -Filter (\"Name='\"+$v.name+\"'\");
        if(-not $s -or $s.PathName -cne $v.expected){throw 'Service ownership changed; restart refused.'};
        Restart-Service -Name $v.name -ErrorAction Stop;
        (Get-Service -Name $v.name).WaitForStatus('Running',[TimeSpan]::FromSeconds(90));
        @{name=$v.name;state=[string](Get-Service -Name $v.name).Status}|ConvertTo-Json
        """
        self.powershell(source, {'name': self.args.service_name, 'expected': expected}, timeout=150)
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            try:
                status = read_json(self.state / 'status.json')
                self.load_endpoint()
                if status['stage'] == 'ready' and self.endpoint['pid'] != before_pid and self.call('GET', '/health/ready')[0] == 200:
                    break
            except (OSError, ValueError):
                pass
            time.sleep(.5)
        else:
            raise AssertionError('Owned service did not recover all components before deadline')
        assert self.token == before_token, 'Pairing was lost during restart'
        assert self.call('GET', '/matches?limit=1')[1]['total'] == 760
        assert self.call('GET', '/matches/' + self.match_id)[1]['version'] == self.selected['version']
        assert self.call('POST', '/connections/openfootball/sync', {}, key=self.idempotency)[1]['id'] == self.import_id
        assert self.job(self.import_id)['status'] == 'succeeded'
        with urlopen(self.web + '/', timeout=15) as response:
            assert response.status == 200
        after = self.service()
        assert current['path'] == after['path']
        if self.args.expected_conflict_port:
            assert [r for r in after['listeners'] if r['port'] == self.args.expected_conflict_port] == self.blocker
        for port in (18732, 18733, 18734):
            original = [r for r in self.before['listeners'] if r['port'] == port]
            assert [r for r in after['listeners'] if r['port'] == port] == original, 'A previously running service changed during isolated test'
        self.check('recovery', 'owned-service-restart-retains-pairing-data-revisions-and-idempotency', previous_kernel_pid=before_pid, new_kernel_pid=self.endpoint['pid'], record_count=760)
        self.check('recovery', 'Joomla-and-unrelated-listeners-preserved-after-owned-restart', joomla_http_status=200, protected_ports=[18732, 18733, 18734])

    def execute(self):
        try:
            assert os.name == 'nt', 'Native Windows host required'
            self.inspect()
            self.api()
            self.native()
            self.browser()
            self.restart()
            self.record['passed'] = True
        except Exception as exc:
            self.record['error'] = self.redact(f'{type(exc).__name__}: {exc}')
            self.record['traceback'] = self.redact(traceback.format_exc())
        finally:
            self.record['finished_at'] = self.now()
            self.record['check_groups'] = {group: sum(c['group'] == group for c in self.checks) for group in sorted({c['group'] for c in self.checks})}
            (self.output / 'commands.json').write_text(self.redact(json.dumps(self.commands, indent=2)), encoding='utf-8')
            (self.output / 'journey.json').write_text(self.redact(json.dumps(self.record, indent=2)), encoding='utf-8')
        print(json.dumps({'passed': self.record['passed'], 'evidence': str(self.output / 'journey.json'), 'error': self.record.get('error')}, indent=2))
        return 0 if self.record['passed'] else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--install-root', required=True, type=Path)
    parser.add_argument('--state-root', required=True, type=Path)
    parser.add_argument('--service-name', required=True)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--workspace-root', type=Path, default=ROOT)
    parser.add_argument('--expected-conflict-port', type=int)
    return Journey(parser.parse_args()).execute()


if __name__ == '__main__':
    sys.exit(main())
