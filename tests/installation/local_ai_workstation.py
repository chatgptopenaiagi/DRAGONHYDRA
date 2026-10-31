"""Real installed LocalService DPAPI settings and offline-Qwen acceptance.

Read-only preflight is the default. --apply operates only on the named isolated
provider test workstation, starts one owned hidden model runner, and restores
the credential-free baseline. No global environment or service-account key copy.
"""
from __future__ import annotations

import argparse
from contextlib import closing
import ctypes
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import secrets
import socket
import sqlite3
import subprocess
import sys
import time
import traceback
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import ProxyHandler, Request, build_opener

ROOT = Path(__file__).resolve().parents[2]
API = '/dragon/api/v1'
SERVICE = 'DragonhydraProvidersA2Test'
POWERSHELL = Path(r'C:\Program Files\PowerShell\7\pwsh.exe')
CONFIG = '/local-model/configuration'
sys.path.insert(0, str(ROOT / 'src'))
from dragonhydra.server import protect

helper_spec = importlib.util.spec_from_file_location('_verified_local_model_helpers', ROOT / 'scripts/probe_local_ai.py')
helper = importlib.util.module_from_spec(helper_spec)
helper_spec.loader.exec_module(helper)


def stamp():
    return datetime.now(timezone.utc).isoformat()


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(',', ':')).encode()


class Journey:
    def __init__(self, args):
        self.args = args
        self.install, self.state, self.output = args.install_root.resolve(), args.state_root.resolve(), args.output.resolve()
        permitted = ROOT / 'build/workstation/test-install/provider-a2'
        assert args.service_name == SERVICE, 'Only the explicitly isolated provider test service is accepted.'
        assert self.install == permitted / 'application files' and self.state == permitted / 'state data'
        assert self.output.is_relative_to(ROOT / 'build/workstation/evidence') and not self.output.exists()
        for path in (self.install, self.state):
            assert path.is_dir() and not path.is_symlink() and not path.is_junction()
        assert os.name == 'nt' and not sys.flags.optimize
        self.output.mkdir(parents=True)
        protect(self.output)
        self.private = []
        self.checks = []
        self.opener = build_opener(ProxyHandler({}))
        self.model = self.stdout = self.stderr = None
        self.model_port = None
        self.model_key = None
        self.key_file = self.output / 'private-model-key.txt'
        self.changed_configuration = False
        self.baseline = None
        self.report = {'schema_version': 1, 'started_at': stamp(), 'passed': False, 'applied': bool(args.apply),
                       'service_name': SERVICE, 'install_root': str(self.install), 'state_root': str(self.state),
                       'checks': self.checks, 'downloads': False, 'software_installations': False,
                       'global_environment_changed': False, 'service_account_key_copy': False,
                       'scope': 'Current installed isolated LocalService workstation, real UI/API settings and constrained offline Qwen source-fact selection.',
                       'clean_machine_tested': False, 'windows_reboot_tested': False,
                       'source_bindings': {'harness_sha256': digest(Path(__file__)),
                                           'runner_helper_sha256': digest(ROOT / 'scripts/probe_local_ai.py')}}
        self.load_endpoint()

    def safe(self, value):
        result = str(value)
        for secret in sorted(set(self.private), key=len, reverse=True):
            result = result.replace(secret, '[REDACTED]')
        return result

    def save(self, name, value):
        (self.output / name).write_text(self.safe(json.dumps(value, ensure_ascii=False, indent=2)) + '\n', encoding='utf-8')

    def passed(self, name, **details):
        self.checks.append({'name': name, 'passed': True, **details})
        print(json.dumps({'passed': name}), flush=True)

    def powershell(self, script, values=None, timeout=45):
        source = "$ErrorActionPreference='Stop';$v=[Console]::In.ReadToEnd()|ConvertFrom-Json;" + script
        result = subprocess.run([str(POWERSHELL), '-NoLogo', '-NoProfile', '-NonInteractive', '-Command', source],
                                input=json.dumps(values or {}), capture_output=True, text=True,
                                encoding='utf-8', errors='replace', timeout=timeout, cwd=ROOT)
        if result.returncode:
            raise RuntimeError('Owned service metadata/control operation failed: ' + self.safe(result.stderr)[-800:])
        return json.loads(result.stdout)

    def service(self):
        result = self.powershell("""
        $s=Get-CimInstance Win32_Service -Filter ("Name='"+$v.name+"'");
        if(-not $s){throw 'Exact isolated service missing.'};
        $p=Get-CimInstance Win32_Process -Filter ('ProcessId='+$s.ProcessId);
        @{name=$s.Name;state=$s.State;path=$s.PathName;account=$s.StartName;pid=$s.ProcessId;executable=$p.ExecutablePath}|ConvertTo-Json
        """, {'name': SERVICE})
        expected = f'"{self.install / "workstation/DragonhydraService.exe"}" --state "{self.state}" --name {SERVICE}'
        assert result['path'].casefold() == expected.casefold(), 'Service ImagePath ownership mismatch.'
        assert result['state'] == 'Running' and result['account'].casefold() in ('nt authority\\localservice', 'localservice')
        assert Path(result['executable']).resolve() == self.install / 'workstation/DragonhydraService.exe'
        return result

    def load_endpoint(self):
        self.token = read(self.state / 'client/local-session.json')['token']
        assert isinstance(self.token, str) and len(self.token) >= 20
        self.private.append(self.token)
        self.endpoint = read(self.state / 'client/endpoint.json')
        self.url = self.endpoint['url'].rstrip('/')
        parsed = urlsplit(self.url)
        assert parsed.scheme == 'http' and parsed.hostname == '127.0.0.1' and parsed.port
        assert parsed.path in ('', '/') and not parsed.query and not parsed.fragment and not parsed.username

    def call(self, path, body=None, *, timeout=12):
        request = Request(self.url + API + path, data=canonical(body) if body is not None else None,
                          headers={'Authorization': 'Bearer ' + self.token, 'Content-Type': 'application/json'},
                          method='PUT' if path == CONFIG and body is not None else 'POST' if body is not None else 'GET')
        try:
            with self.opener.open(request, timeout=timeout) as response:
                raw = response.read(128 * 1024 + 1)
                assert len(raw) <= 128 * 1024
                if self.model_key:
                    assert self.model_key.encode() not in raw, 'An API response exposed the generated model key.'
                return response.status, json.loads(raw)
        except HTTPError as error:
            error.close()
            raise

    def configuration(self):
        status, current = self.call(CONFIG)
        assert status == 200 and set(current) == {'endpoint', 'configured', 'endpoint_source', 'credential_source'}
        assert current['endpoint_source'] != 'environment' and current['credential_source'] != 'environment', 'Existing environment overrides are not modified by this test.'
        return current

    def passive_health(self, configured, stage):
        expected = 'configured_not_tested' if configured else 'not_configured'
        _, ready = self.call('/health/ready')
        _, system = self.call('/system')
        assert ready['status'] == 'ready' and ready['optional_ai'] == expected
        assert system['ai'] == expected
        assert system['local_ai'] == {'status': expected, 'configured': configured,
                                       'mode': 'constrained_source_fact_selection', 'runtime_health': 'not_checked'}
        self.report.setdefault('passive_health_checks', []).append(
            {'stage': stage, 'ready_optional_ai': ready['optional_ai'], 'system_ai': system['ai'],
             'local_ai': system['local_ai']})

    def sports_fingerprint(self):
        path = self.state / 'kernel/core.sqlite3'
        with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)) as db:
            schema = db.execute('SELECT type,name,sql FROM sqlite_master ORDER BY type,name').fetchall()
            tables = [row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' AND name NOT LIKE 'product_%' ORDER BY name")]
            rows = {}
            for name in tables:
                assert re.fullmatch('[A-Za-z_][A-Za-z_0-9]*', name)
                values = db.execute('SELECT * FROM "' + name + '"').fetchall()
                def binary(value):
                    if isinstance(value, bytes):
                        return {'bytes_sha256': hashlib.sha256(value).hexdigest()}
                    raise TypeError()
                encoded = sorted(json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True,
                                            separators=(',', ':'), default=binary).encode() for value in values)
                rows[name] = {'rows': len(encoded), 'sha256': hashlib.sha256(b'\n'.join(encoded)).hexdigest()}
        return {'schema_sha256': hashlib.sha256(canonical(schema)).hexdigest(), 'sports_tables': rows,
                'excluded_mutable_application_tables': 'product_* sessions, jobs, updates and schema receipt tables'}

    def originals(self):
        development = []
        source = ROOT / 'runtime/connections/product/endpoint.json'
        if source.is_file():
            development.append(read(source))
        frozen = ROOT / 'build/connections/evidence/frozen-a2-upgrade.json'
        if frozen.is_file():
            development.append(read(frozen)['current'])
        return self.powershell("""
        $services=@(Get-CimInstance Win32_Service|Where-Object {$_.Name -in @('DragonhydraWorkstation','DragonhydraWorkstationTest')}|ForEach-Object {
          @{name=$_.Name;state=$_.State;path=$_.PathName;account=$_.StartName;pid=$_.ProcessId}
        });
        $ports=@(18732..18745)+@($v.development|ForEach-Object {([Uri]$_.url).Port});
        $listeners=@(Get-NetTCPConnection -State Listen|Where-Object {$_.LocalPort -in $ports}|ForEach-Object {
          $p=Get-CimInstance Win32_Process -Filter ('ProcessId='+$_.OwningProcess);
          @{address=$_.LocalAddress;port=$_.LocalPort;pid=$_.OwningProcess;executable=$p.ExecutablePath;created=[string]$p.CreationDate}
        });
        @{services=$services;listeners=$listeners}|ConvertTo-Json -Depth 6
        """, {'development': development})

    def check_originals(self):
        current = self.originals()
        assert sorted(current['services'], key=lambda row: row['name']) == sorted(self.before_originals['services'], key=lambda row: row['name']), 'An original Windows service changed.'
        transitions = []
        receipts = [ROOT / 'build/connections/evidence' / name for name in
                    ('continuous-source-reload.json', 'local-model-settings-source-reload.json',
                     'provenance-source-reload.json', 'frozen-a2-upgrade.json')]
        receipts += self.args.allow_development_receipt
        listeners = current['listeners']
        for old in self.before_originals['listeners']:
            if old in listeners:
                continue
            matched = None
            for path in receipts:
                path = path.resolve()
                assert path.is_relative_to(ROOT / 'build/connections/evidence')
                if not path.is_file():
                    continue
                receipt = read(path)
                if not receipt.get('passed') or not receipt.get('pairing_retained'):
                    continue
                previous, replacement = receipt.get('previous', {}), receipt.get('current', {})
                if previous.get('stopped') != old['pid'] or not previous.get('graceful'):
                    continue
                port = urlsplit(replacement['url']).port
                if any(row['pid'] == replacement['pid'] and row['port'] == port for row in listeners):
                    matched = {'previous_pid': old['pid'], 'previous_port': old['port'], 'current_pid': replacement['pid'],
                               'current_url': replacement['url'], 'receipt': str(path.relative_to(ROOT)), 'receipt_sha256': digest(path)}
                    break
            assert matched, 'An original listener changed without an exact intentional root development receipt.'
            transitions.append(matched)
        c7 = ROOT / 'dist/workstation/0.4.1-dev.1/DRAGONHYDRA-0.4.1-dev.1-Workstation-win-x64-Setup.exe'
        assert digest(c7) == self.c7_hash
        self.report['originals_after'] = current
        self.report['intentional_root_development_transitions'] = transitions
        self.passed('Original C7 services, gateway listeners and installer preserved; authorized development transitions remain explicit', transitions=len(transitions))

    def preflight(self):
        self.owned = self.service()
        binary = self.install / 'server/DRAGONHYDRA-Server.exe'
        assert digest(binary) == self.args.expected_kernel_sha256, 'Installed kernel does not match root-approved artifact.'
        status, system = self.call('/system')
        assert status == 200 and system['build']['source_content_sha256'] == self.args.expected_source_content_sha256
        self.report['kernel'] = {'binary_sha256': digest(binary), 'source_content_sha256': self.args.expected_source_content_sha256,
                                 'source_manifest_sha256': digest(self.install / 'server/SOURCE-MANIFEST.json')}
        self.baseline = self.configuration()
        assert self.baseline == {'endpoint': '', 'configured': False, 'endpoint_source': 'none', 'credential_source': 'none'}, 'Refusing to replace any pre-existing user model setup or service environment override.'
        self.passive_health(False, 'credential-free baseline')
        self.before_sports = self.sports_fingerprint()
        self.before_originals = self.originals()
        c7 = ROOT / 'dist/workstation/0.4.1-dev.1/DRAGONHYDRA-0.4.1-dev.1-Workstation-win-x64-Setup.exe'
        self.c7_hash = digest(c7)
        assert self.c7_hash == 'a2a1cde06f7a9fbc86e1e564dc5aabb8984368bcf2c2d919f2f492568bd67d97'
        self.report.update(configuration_before=self.baseline, sports_before=self.before_sports,
                           originals_before=self.before_originals, preserved_c7_installer_sha256=self.c7_hash,
                           inference_caller={'service': SERVICE, 'identity': self.owned['account'],
                                             'role': 'Persists/decrypts its own DPAPI credential and calls the separate model endpoint'})
        self.save('before.json', self.report)
        self.passed('Exact installed LocalService identity, approved kernel, credential-free configuration and protected baselines verified')

    def start_model(self):
        class Memory(ctypes.Structure):
            _fields_ = [('length', ctypes.c_ulong), ('load', ctypes.c_ulong)] + [
                (name, ctypes.c_ulonglong) for name in ('total', 'available', 'total_page', 'available_page', 'total_virtual', 'available_virtual', 'extended')]
        memory = Memory(); memory.length = ctypes.sizeof(memory)
        assert ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(memory)) and memory.available >= 8 * 1024**3
        assert digest(helper.RUNTIME) == helper.RUNTIME_SHA and digest(helper.MODEL) == helper.MODEL_SHA
        self.report['model'] = {'path': str(helper.MODEL), 'sha256': helper.MODEL_SHA, 'bytes': helper.MODEL.stat().st_size,
                                'runtime': str(helper.RUNTIME), 'runtime_sha256': helper.RUNTIME_SHA,
                                'available_ram_bytes': memory.available, 'runner_offline_flag': True, 'airgap_verified': False}
        self.report['model']['standalone_runner_identity'] = self.powershell("""
        $identity=[Security.Principal.WindowsIdentity]::GetCurrent();
        @{name=$identity.Name;sid=$identity.User.Value;elevated=([Security.Principal.WindowsPrincipal]::new($identity)).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)}|ConvertTo-Json
        """)
        self.report['model']['autostarted_by_product'] = False
        with socket.socket() as selected:
            selected.bind(('127.0.0.1', 0))
            self.model_port = selected.getsockname()[1]
        self.model_url = 'http://127.0.0.1:' + str(self.model_port)
        self.model_key = secrets.token_urlsafe(48)
        self.private.append(self.model_key)
        self.key_file.write_text(self.model_key + '\n', encoding='utf-8')
        protect(self.key_file)
        arguments = [str(helper.RUNTIME), '--model', str(helper.MODEL), '--host', '127.0.0.1', '--port', str(self.model_port),
                     '--offline', '--device', 'none', '--n-gpu-layers', '0', '--threads', '4', '--ctx-size', '2048',
                     '--parallel', '1', '--batch-size', '256', '--ubatch-size', '64', '--no-kv-offload', '--no-webui',
                     '--no-slots', '--no-agent', '--reasoning', 'off', '--api-key-file', str(self.key_file),
                     '--alias', 'dragonhydra-compact-local', '--timeout', '90', '--log-disable']
        startup = subprocess.STARTUPINFO(); startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW; startup.wShowWindow = 0
        self.stdout, self.stderr = (self.output / 'model.stdout.log').open('wb'), (self.output / 'model.stderr.log').open('wb')
        self.model = subprocess.Popen(arguments, cwd=helper.RUNTIME.parent, stdin=subprocess.DEVNULL,
                                      stdout=self.stdout, stderr=self.stderr, creationflags=subprocess.CREATE_NEW_CONSOLE, startupinfo=startup)
        self.report['owned_model_pid'] = self.model.pid
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            assert self.model.poll() is None, 'Owned local model exited before readiness.'
            try:
                with self.opener.open(self.model_url + '/health', timeout=2) as response:
                    if json.loads(response.read(1024))['status'] == 'ok':
                        break
            except HTTPError as error:
                error.close()
            except (OSError, URLError, TimeoutError):
                pass
            time.sleep(.2)
        else:
            raise TimeoutError('Owned offline model startup deadline expired.')
        try:
            self.opener.open(self.model_url + '/v1/models', timeout=3).close()
            raise AssertionError('Owned model endpoint unexpectedly accepted an unauthenticated request.')
        except HTTPError as error:
            status = error.code; error.close()
            assert status == 401
        self.passed('Pinned existing Qwen loaded offline on owned hidden authenticated loopback runner')

    def stop_model(self):
        if self.model:
            self.report['model_shutdown'] = helper.stop_owned(self.model)
            self.model = None
        if self.stdout:
            self.stdout.close(); self.stdout = None
        if self.stderr:
            self.stderr.close(); self.stderr = None
        self.key_file.unlink(missing_ok=True)
        self.report['temporary_model_key_removed'] = not self.key_file.exists()
        if self.model_port:
            with socket.socket() as check:
                try:
                    check.bind(('127.0.0.1', self.model_port))
                    self.report['owned_model_port_released'] = True
                except OSError:
                    self.report['owned_model_port_released'] = False

    def restart(self, label):
        current = self.service()
        old_kernel = read(self.state / 'kernel/endpoint.json')['pid']
        old_token = self.token
        self.powershell("""
        $s=Get-CimInstance Win32_Service -Filter ("Name='"+$v.name+"'");
        if(-not $s -or $s.PathName -cne $v.expected){throw 'Exact owned service binding changed; restart refused.'};
        Restart-Service -Name $v.name -ErrorAction Stop;
        (Get-Service $v.name).WaitForStatus('Running',[TimeSpan]::FromSeconds(90));
        @{name=$v.name;state=[string](Get-Service $v.name).Status}|ConvertTo-Json
        """, {'name': SERVICE, 'expected': current['path']}, timeout=120)
        deadline = time.monotonic() + 150
        while time.monotonic() < deadline:
            try:
                self.load_endpoint()
                kernel = read(self.state / 'kernel/endpoint.json')
                stage = read(self.state / 'status.json')['stage']
                if stage == 'ready' and kernel['pid'] != old_kernel and self.call('/health/ready')[0] == 200:
                    break
            except (OSError, ValueError, URLError, TimeoutError):
                pass
            time.sleep(.3)
        else:
            raise TimeoutError('Exact owned workstation did not become ready after restart.')
        assert self.token == old_token and digest(self.install / 'server/DRAGONHYDRA-Server.exe') == self.args.expected_kernel_sha256
        self.report.setdefault('owned_service_restarts', []).append({'label': label, 'previous_kernel_pid': old_kernel, 'current_kernel_pid': kernel['pid'], 'pairing_retained': True})

    def open_analysis(self, browser):
        from playwright.sync_api import expect
        context = browser.new_context(viewport={'width': 1500, 'height': 1100}, reduced_motion='reduce')
        page = context.new_page()
        page.goto(self.url + '/#token=' + self.token, wait_until='domcontentloaded')
        expect(page.get_by_role('heading', name='Today’s football')).to_be_visible(timeout=30000)
        assert '#token=' not in page.url
        if not hasattr(self, 'match_id'):
            _, matches = self.call('/matches?provider=statsbomb&limit=1')
            if not matches['items']:
                _, matches = self.call('/matches?limit=1')
            self.match_id = matches['items'][0]['id']
            _, self.package = self.call('/matches/' + self.match_id + '/analysis-package')
            self.report.update(match_id=self.match_id, package_sha256=self.package['package_sha256'], evidence_id=self.package['evidence']['E1']['id'])
        page.goto(self.url + '/#match/' + self.match_id, wait_until='domcontentloaded')
        page.get_by_role('tab', name='Analysis', exact=True).click()
        expect(page.get_by_role('heading', name='Investigate the evidence')).to_be_visible()
        return context, page

    def model_action(self, page, accepted):
        from playwright.sync_api import expect
        path = self.url + API + '/matches/' + self.match_id + '/local-explanations'
        with page.expect_response(lambda response: response.url == path and response.request.method == 'POST', timeout=15000) as response:
            page.get_by_role('button', name='Use local model', exact=True).click()
        assert response.value.status == 202
        identifier = response.value.json()['id']
        deadline = time.monotonic() + 50
        while time.monotonic() < deadline:
            _, job = self.call('/jobs/' + identifier)
            if job['status'] in ('succeeded', 'failed', 'cancelled', 'interrupted'):
                break
            time.sleep(.2)
        else:
            raise TimeoutError('Actual installed model job did not finish within its bounded deadline.')
        assert job['status'] == 'succeeded'
        result = job['result']
        assert result['package_sha256'] == self.package['package_sha256']
        assert result['evidence'][0]['id'] == self.package['evidence']['E1']['id']
        target = page.locator('#explanation-result')
        if accepted:
            assert result['kind'] == 'local_llm' and result['local_ai']['accepted']
            assert result['mode'] == 'constrained_source_fact_selection'
            assert len(result['observations']) == 1 and result['observations'][0] in self.package['allowed_observations']
            expect(target.locator('.badge')).to_have_text('LOCAL MODEL · SOURCE FACT SELECTION', timeout=30000)
        else:
            assert result['kind'] == 'deterministic' and not result['local_ai']['accepted'] and result['local_ai']['code'] == 'AI_NOT_CONFIGURED'
            expect(target.locator('.badge')).to_have_text('DETERMINISTIC EVIDENCE SUMMARY', timeout=30000)
            expect(target.locator('.local-ai-diagnostic')).to_contain_text('AI_NOT_CONFIGURED')
        _, citation = self.call('/evidence/' + self.package['evidence']['E1']['id'])
        assert (citation.get('source_hash') or citation.get('raw_sha256')) == self.package['evidence']['E1']['source_sha256']
        return job

    def exercise(self):
        from playwright.sync_api import expect, sync_playwright
        self.start_model()
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel='msedge', headless=True)
            try:
                context, page = self.open_analysis(browser)
                try:
                    page.get_by_role('button', name='Configure local model', exact=True).click()
                    expect(page.locator('#local-model-key')).to_have_attribute('type', 'password')
                    page.locator('#local-model-endpoint').fill(self.model_url)
                    page.locator('#local-model-key').fill(self.model_key)
                    self.changed_configuration = True
                    with page.expect_response(lambda response: response.url == self.url + API + CONFIG and response.request.method == 'PUT', timeout=15000) as response:
                        page.get_by_role('button', name='Save local model', exact=True).click()
                    assert response.value.status == 200
                    saved = response.value.json()
                    assert self.model_key not in json.dumps(saved) and saved == self.configuration()
                    assert saved == {'endpoint': self.model_url, 'configured': True, 'endpoint_source': 'stored', 'credential_source': 'vault'}
                    expect(page.locator('#local-model-key')).to_have_value('')
                    expect(page.locator('.local-model-status')).to_contain_text('saved securely')
                    page.screenshot(path=str(self.output / 'settings-saved.png'), full_page=True)
                    self.report['configuration_saved'] = saved
                    self.passive_health(True, 'saved through Analysis UI')
                    self.passed('Actual Analysis UI saved endpoint/key through LocalService API; GET contains no key and identifies DPAPI vault')
                finally:
                    context.close()
                self.restart('stored DPAPI configuration persistence')
                persistent = self.configuration()
                assert persistent == saved
                self.passive_health(True, 'persisted after exact owned service restart')
                self.passed('Stored endpoint and DPAPI credential survive exact owned service restart without environment overrides')
                context, page = self.open_analysis(browser)
                try:
                    accepted = self.model_action(page, True)
                    self.save('accepted-job.json', accepted)
                    page.screenshot(path=str(self.output / 'accepted-local-fact.png'), full_page=True)
                    self.report['accepted_job_id'] = accepted['id']
                    self.passive_health(True, 'after accepted inference; passive status remains untested')
                    self.passed('Real offline Qwen job accepted after LocalService restart; exact fact and citation prove service-identity DPAPI decryption')
                    page.get_by_role('button', name='Configure local model', exact=True).click()
                    expect(page.locator('#local-model-key')).to_have_value('')
                    with page.expect_response(lambda response: response.url == self.url + API + CONFIG and response.request.method == 'PUT', timeout=15000) as response:
                        page.get_by_role('button', name='Remove saved model key', exact=True).click()
                    assert response.value.status == 200
                    removed = response.value.json()
                    assert not removed['configured'] and removed['credential_source'] == 'none'
                    assert self.model_key not in json.dumps(removed)
                    expect(page.locator('.local-model-status')).to_contain_text('Key: not set')
                    self.passed('Analysis UI removed the saved service key without returning its plaintext')
                finally:
                    context.close()
                self.call(CONFIG, {'endpoint': self.baseline['endpoint'], 'remove_credential': True})
                self.stop_model()
                assert self.report['temporary_model_key_removed'] and self.report['owned_model_port_released']
                self.restart('removed model credential fallback persistence')
                restored = self.configuration()
                assert restored == self.baseline
                self.passive_health(False, 'cleaned configuration after owned service restart')
                context, page = self.open_analysis(browser)
                try:
                    fallback = self.model_action(page, False)
                    self.save('fallback-job.json', fallback)
                    page.screenshot(path=str(self.output / 'fallback-after-removal.png'), full_page=True)
                    self.report['fallback_job_id'] = fallback['id']
                    self.passed('Removed key stays removed after restart and stopped runner; actual UI returns deterministic AI_NOT_CONFIGURED fallback')
                finally:
                    context.close()
            finally:
                browser.close()

    def execute(self):
        try:
            self.preflight()
            if self.args.apply:
                self.exercise()
                after = self.sports_fingerprint()
                assert after == self.before_sports, 'Sports evidence or SQLite schema changed during settings proof.'
                self.report['sports_after'] = after
                self.passed('Sports evidence table contents and SQLite schema are unchanged; model settings remain outside the database')
            self.check_originals()
            self.service()
            self.report['passed'] = True
        except Exception as error:
            self.report['error'] = self.safe(type(error).__name__ + ': ' + str(error))
            self.report['traceback'] = self.safe(traceback.format_exc())
        finally:
            if self.changed_configuration and self.baseline is not None:
                try:
                    self.load_endpoint()
                    self.call(CONFIG, {'endpoint': self.baseline['endpoint'], 'remove_credential': True})
                    self.report['configuration_restored'] = self.configuration() == self.baseline
                except Exception as error:
                    self.report['configuration_restored'] = False
                    self.report['cleanup_error'] = self.safe(type(error).__name__ + ': ' + str(error))
                    self.report['passed'] = False
            try:
                self.stop_model()
            except Exception as error:
                self.report['runner_cleanup_error'] = self.safe(type(error).__name__ + ': ' + str(error))
                self.report['passed'] = False
            if self.args.apply:
                self.report['passed'] = self.report['passed'] and self.report.get('configuration_restored', False) and self.report.get('temporary_model_key_removed', False) and self.report.get('owned_model_port_released', False)
            try:
                self.service()
                self.report['new_test_service_left_running'] = True
            except Exception as error:
                self.report['new_test_service_left_running'] = False
                self.report['final_service_error'] = self.safe(type(error).__name__ + ': ' + str(error))
                self.report['passed'] = False
            self.report.update(finished_at=stamp(), check_groups=len(self.checks))
            self.save('journey.json', self.report)
        print(json.dumps({'passed': self.report['passed'], 'applied': self.args.apply, 'groups': len(self.checks),
                          'error': self.report.get('error'), 'evidence': str(self.output / 'journey.json')}), flush=True)
        return 0 if self.report['passed'] else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--install-root', type=Path, default=ROOT / 'build/workstation/test-install/provider-a2/application files')
    parser.add_argument('--state-root', type=Path, default=ROOT / 'build/workstation/test-install/provider-a2/state data')
    parser.add_argument('--service-name', default=SERVICE)
    parser.add_argument('--expected-kernel-sha256', required=True)
    parser.add_argument('--expected-source-content-sha256', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--allow-development-receipt', type=Path, action='append', default=[])
    parser.add_argument('--apply', action='store_true', help='Run the authorized isolated UI/DPAPI/model/restart proof after a passing preflight')
    args = parser.parse_args()
    if not re.fullmatch('[a-f0-9]{64}', args.expected_kernel_sha256) or not re.fullmatch('[a-f0-9]{64}', args.expected_source_content_sha256):
        parser.error('Expected artifact and content hashes must be full SHA256 values.')
    return Journey(args).execute()


if __name__ == '__main__':
    raise SystemExit(main())
