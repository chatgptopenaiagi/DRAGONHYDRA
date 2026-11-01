"""Read-only primary Windows client/shortcut and backend compatibility receipts.

This does not launch a GUI, connect to CDP, inspect a DOM, enter credentials,
click a link, or control a service. Native automatic pairing and OS-browser
handoff remain separate checks performed through the Windows Computer Use API.
The client metadata token is used only in process memory for exact loopback GETs.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import unittest
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener


ROOT = Path(__file__).resolve().parents[2]
PROFILE = ROOT/'build/workstation/test-install'
STATE = PROFILE/'state data'
INSTALL = PROFILE/'application files'
BOUNDARY = ROOT/'build/system-control-center-20261101/evidence'
SERVICE = 'DragonhydraWorkstationTest'
ORIGIN = 'http://127.0.0.1:18744'
API = '/dragon/api/v1'
CLIENT_SHA256 = 'f4e8fbae68c4fdc3f52c7f9baaeb98f375df26e34dced3dc87c7988d9a4c0617'
CLIENT_BYTES = 10078208
POWERSHELL = r'C:\Program Files\PowerShell\7\pwsh.exe'


def utc():
    return datetime.now(timezone.utc).isoformat()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False,
                      separators=(',', ':'), allow_nan=False).encode()


def get_is_allowed(path):
    return path in (API+'/health/ready', API+'/system/modules', API+'/connections',
                    API+'/matches?limit=1') or bool(re.fullmatch(re.escape(API)+r'/matches/[a-f0-9]{64}', path))


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, new_url):
        return None


class Preflight:
    def __init__(self, output, expected_retained_count=None):
        if os.name != 'nt':
            raise RuntimeError('WINDOWS_REQUIRED')
        self.output = output.resolve()
        if (self.output == BOUNDARY or not self.output.is_relative_to(BOUNDARY)
                or self.output.exists()):
            raise ValueError('FRESH_OWNED_EVIDENCE_DIRECTORY_REQUIRED')
        # Reuse only this helper's filesystem ACL implementation, not its UI or
        # process lifecycle methods. Profiles/session cookies are not created.
        spec = importlib.util.spec_from_file_location('primary_preflight_acl', ROOT/'tests/ui/native_webview_journey.py')
        native = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(native)
        native.BASE = BOUNDARY
        native.Windows().private_directory(self.output)
        self.expected_retained_count = expected_retained_count
        self.token = None
        self.opener = build_opener(ProxyHandler({}), NoRedirect())
        self.report = {'schema_version': 1, 'started_at': utc(), 'passed': False,
            'scope': 'Read-only installed bytes, official shortcut, metadata and authenticated backend GET compatibility',
            'service_name': SERVICE, 'api_origin': ORIGIN, 'joomla_origin': 'http://127.0.0.1:18740',
            'harness_sha256': digest(__file__), 'checks': [],
            'gui_launch_requested': False, 'ui_input_requested': False,
            'cdp_connection_requested': False, 'session_post_requested': False,
            'service_controls_requested': False, 'provider_or_model_calls_requested': False,
            'native_automatic_pairing': 'NOT_RUN', 'native_external_browser_handoff': 'NOT_RUN'}

    def check(self, identifier, **evidence):
        self.report['checks'].append({'id': identifier, 'status': 'PASS',
                                      'observed_at': utc(), **evidence})

    def get(self, path):
        if not get_is_allowed(path):
            raise ValueError('NON_ALLOWLISTED_READ')
        request = Request(ORIGIN+path, headers={'Authorization': 'Bearer '+self.token,
                                               'Accept': 'application/json'}, method='GET')
        with self.opener.open(request, timeout=5) as response:
            if response.status != 200 or response.geturl() != ORIGIN+path:
                raise RuntimeError('UNEXPECTED_LOCAL_RESPONSE')
            raw = response.read(2*1024*1024+1)
        if len(raw) > 2*1024*1024:
            raise RuntimeError('LOCAL_RESPONSE_TOO_LARGE')
        return json.loads(raw)

    def target(self):
        cfg = read(STATE/'workstation.json')
        if (cfg['service_name'] != SERVICE or Path(cfg['install_root']).resolve() != INSTALL
                or Path(cfg['state_root']).resolve() != STATE or cfg['api_port'] != 18744
                or cfg['web_port'] != 18740 or cfg['database_port'] != 18741):
            raise RuntimeError('PRIMARY_INSTALLATION_BINDING_MISMATCH')
        client = INSTALL/'client/DRAGONHYDRA-Client.exe'
        if client.stat().st_size != CLIENT_BYTES or digest(client) != CLIENT_SHA256:
            raise RuntimeError('EXPECTED_REPAIRED_CLIENT_NOT_INSTALLED')
        self.check('installed_repaired_client_bytes', path=str(client), bytes=CLIENT_BYTES, sha256=CLIENT_SHA256)
        payload = {'service': SERVICE, 'state': str(STATE)}
        command = r'''
$v=[Console]::In.ReadToEnd()|ConvertFrom-Json
$path=Join-Path ([Environment]::GetFolderPath('CommonDesktopDirectory')) ('DRAGONHYDRA Workstation - '+$v.service+'.lnk')
if(-not(Test-Path -LiteralPath $path -PathType Leaf)){throw 'OFFICIAL_SHORTCUT_MISSING'}
$s=(New-Object -ComObject WScript.Shell).CreateShortcut($path)
$service=Get-CimInstance Win32_Service -Filter ("Name='"+$v.service+"'")
@{shortcut=$path;target=$s.TargetPath;arguments=$s.Arguments;service=@{name=$service.Name;state=$service.State;account=$service.StartName;process_id=$service.ProcessId}}|ConvertTo-Json -Depth 4
'''
        result = subprocess.run([POWERSHELL, '-NoProfile', '-NonInteractive', '-Command', command],
            input=json.dumps(payload), text=True, capture_output=True, timeout=25)
        if result.returncode:
            raise RuntimeError('READ_ONLY_SHORTCUT_OR_SERVICE_INSPECTION_FAILED')
        binding = json.loads(result.stdout)
        if (Path(binding['target']).resolve() != INSTALL/'workstation/DragonhydraLauncher.exe'
                or binding['arguments'] != '--state "'+str(STATE)+'"'
                or binding['service']['name'] != SERVICE or binding['service']['state'] != 'Running'):
            raise RuntimeError('OFFICIAL_SHORTCUT_OR_SERVICE_BINDING_MISMATCH')
        self.check('official_shortcut_and_running_service', **binding)
        client_endpoint, kernel_endpoint = read(STATE/'client/endpoint.json'), read(STATE/'kernel/endpoint.json')
        if client_endpoint['url'] != ORIGIN or kernel_endpoint['url'] != ORIGIN or client_endpoint['pid'] != kernel_endpoint['pid']:
            raise RuntimeError('CLIENT_KERNEL_ENDPOINT_MISMATCH')
        self.token = read(STATE/'client/local-session.json')['token']
        if not isinstance(self.token, str) or not re.fullmatch(r'[a-zA-Z0-9_-]{20,200}', self.token):
            raise RuntimeError('CLIENT_PAIRING_METADATA_INVALID')
        self.check('primary_endpoint_metadata', kernel_pid=kernel_endpoint['pid'],
                   source_sha=kernel_endpoint.get('source_sha'))

    def read_acceptance(self):
        hashes = {name: digest(STATE/'client'/name) for name in ('endpoint.json', 'local-session.json')}
        health = self.get(API+'/health/ready')
        if health.get('status') != 'ready' or health.get('backend') != 'sqlite':
            raise RuntimeError('ASSOCIATED_BACKEND_NOT_READY')
        self.check('client_metadata_authorizes_backend_read', status=health['status'],
            backend=health['backend'], version=health.get('version'), source_sha=health.get('source_sha'),
            scope='Bearer GET using existing client metadata; this is not native automatic-pairing acceptance')
        modules = self.get(API+'/system/modules')
        if modules.get('schema_version') != 1 or modules.get('summary', {}).get('total_modules') != 18 or not modules.get('read_only'):
            raise RuntimeError('MODULE_REGISTRY_CONTRACT_MISMATCH')
        self.check('module_registry_reader_compatibility', core_state=modules['core_state'], summary=modules['summary'])
        matches = self.get(API+'/matches?limit=1')
        if not matches.get('items') or matches['total'] < 1:
            raise RuntimeError('RETAINED_MATCHES_UNAVAILABLE')
        if self.expected_retained_count is not None and matches['total'] != self.expected_retained_count:
            raise RuntimeError('RETAINED_COUNT_DIFFERS_FROM_ACCEPTANCE_BASELINE')
        first = matches['items'][0]
        if not re.fullmatch(r'[a-f0-9]{64}', first.get('id', '')):
            raise RuntimeError('INVALID_RETAINED_IDENTIFIER')
        detail = self.get(API+'/matches/'+first['id'])
        if detail != first:
            raise RuntimeError('RETAINED_DETAIL_CONTRACT_MISMATCH')
        self.check('retained_match_read', total=matches['total'], match={key: detail.get(key) for key in
            ('id', 'source_id', 'competition', 'home', 'away', 'event_date', 'status', 'score', 'received_at')},
            detail_sha256=hashlib.sha256(canonical(detail)).hexdigest())
        connections = self.get(API+'/connections')
        settings = [{key: item.get(key) for key in ('id', 'config', 'interval_seconds', 'credential_configured')}
                    for item in connections['items']]
        provider = next(item for item in connections['items'] if item['id'] == 'api-football')
        url = urlsplit(provider['registration_url'])
        if (url.scheme != 'https' or not url.hostname or url.username or url.password
                or url.query or url.fragment):
            raise RuntimeError('PROVIDER_LINK_NOT_PUBLIC_HTTPS')
        self.check('provider_link_metadata', provider='api-football', expected_url=provider['registration_url'],
            settings_sha256=hashlib.sha256(canonical(sorted(settings, key=lambda item: item['id']))).hexdigest(),
            scope='API destination only; OS browser handoff remains NOT_RUN')
        if hashes != {name: digest(STATE/'client'/name) for name in hashes}:
            raise RuntimeError('PAIRING_METADATA_CHANGED_DURING_READS')
        self.check('pairing_endpoint_metadata_preserved', hashes=hashes)
        spec = importlib.util.spec_from_file_location('primary_browser_association', ROOT/'tests/installation/desktop_external_links.py')
        helpers = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(helpers)
        self.check('default_browser_association_read', association=helpers.default_browser(),
                   scope='Windows association metadata only; no browser launched or controlled')

    def run(self):
        try:
            self.target()
            self.read_acceptance()
            self.report['passed'] = True
        except Exception as error:
            # HTTP bodies, exceptions and private configuration are never logged.
            self.report['error'] = {'type': type(error).__name__,
                'code': str(error) if re.fullmatch(r'[A-Z_]{1,100}', str(error)) else 'READ_ONLY_PREFLIGHT_FAILED',
                'http_status': error.code if isinstance(error, HTTPError) else None}
        finally:
            self.report['finished_at'] = utc()
            raw = json.dumps(self.report, indent=2, ensure_ascii=False)+'\n'
            if self.token and self.token in raw:
                raise RuntimeError('SECRET_IN_RECEIPT_REFUSED')
            temporary = self.output/'verification.json.tmp'
            temporary.write_text(raw, encoding='utf-8')
            temporary.replace(self.output/'verification.json')
        print(json.dumps({'passed': self.report['passed'], 'checks': len(self.report['checks']),
                          'report': str(self.output/'verification.json'), 'error': self.report.get('error')}))
        return 0 if self.report['passed'] else 1


class ReadOnlyGuardTests(unittest.TestCase):
    def test_only_exact_primary_read_routes_are_admitted(self):
        for path in (API+'/health/ready', API+'/system/modules', API+'/connections',
                     API+'/matches?limit=1', API+'/matches/'+'a'*64):
            self.assertTrue(get_is_allowed(path), path)
        for path in ('http://127.0.0.1:18743'+API+'/health/ready', API+'/system/shutdown',
                     API+'/connections/api-football/sync', API+'/jobs',
                     API+'/matches?limit=1&token=not-allowed', API+'/matches/../system'):
            self.assertFalse(get_is_allowed(path), path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--expected-retained-count', type=int)
    parser.add_argument('--execute-read-only-checks', action='store_true')
    parser.add_argument('--self-test', action='store_true')
    args = parser.parse_args()
    if args.self_test:
        result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(ReadOnlyGuardTests))
        return 0 if result.wasSuccessful() else 1
    if not args.execute_read_only_checks or args.output is None:
        parser.error('Read --help; use --execute-read-only-checks with a fresh --output after deployment')
    return Preflight(args.output, args.expected_retained_count).run()


if __name__ == '__main__':
    raise SystemExit(main())
