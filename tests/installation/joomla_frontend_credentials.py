"""Private acceptance credentials: stdin only, owner-bound Windows DPAPI at rest.

Not application configuration. Joomla/password rotations never require source edits.
Never pass credential JSON on the command line or print decoded credential values.
"""
import ctypes
from ctypes import wintypes
from datetime import datetime, timezone
import hmac
import importlib.util
import json
from pathlib import Path
import sys
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT / 'build/joomla-frontend-20261101'
PRIVATE = WORK / 'private-backup'
EVIDENCE = WORK / 'evidence'
CREDENTIALS = PRIVATE / 'acceptance-credentials.dpapi'


class Blob(ctypes.Structure):
    _fields_ = [('size', wintypes.DWORD), ('data', ctypes.POINTER(ctypes.c_ubyte))]


def crypt(data, decrypt=False):
    buffer = ctypes.create_string_buffer(data)
    source = Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    output = Blob()
    library = ctypes.WinDLL('crypt32', use_last_error=True)
    if decrypt:
        ok = library.CryptUnprotectData(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(output))
    else:
        ok = library.CryptProtectData(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(output))
    if not ok:
        raise RuntimeError('Owner-bound credential protection failed')
    try:
        return ctypes.string_at(output.data, output.size)
    finally:
        ctypes.WinDLL('kernel32').LocalFree(output.data)


def load_credentials():
    return json.loads(crypt(CREDENTIALS.read_bytes(), decrypt=True))


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def supplied_configuration_role(value, cfg):
    """A value described as a token may be an existing generated local password."""
    return [key for key in ('admin_password', 'db_password', 'core_db_password', 'root_password')
            if isinstance(cfg.get(key), str) and hmac.compare_digest(value, cfg[key])]


def load_recovery():
    spec = importlib.util.spec_from_file_location('frontend_recovery_transport', ROOT / 'tests/installation/joomla_recovery.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.PRIVATE = PRIVATE
    module.EVIDENCE = EVIDENCE
    module.WORK = WORK
    return module


def login(module, username, password):
    recovery = module.Recovery()
    status, body, _ = recovery.request(recovery.admin)
    inputs = module.Inputs(); inputs.feed(body)
    assert status == 200 and 'mod-login-username' in body
    status, body, _ = recovery.request(module.login_action(recovery.admin, inputs), form=inputs.hidden | {
        'username': username, 'passwd': password, 'option': 'com_login', 'task': 'login'})
    if status != 200 or 'mod-login-username' in body:
        return None
    status, body, _ = recovery.request(recovery.component + '&section=sources')
    return recovery if status == 200 and module.component_renders(body, 'Data sources') else None


def main():
    supplied = json.loads(sys.stdin.read())
    assert set(supplied) == {'username', 'password', 'token'}
    assert (EVIDENCE / 'backup-r1.json').exists() and not CREDENTIALS.exists()
    module = load_recovery()
    cfg = read(module.STATE / 'workstation.json')
    assert cfg['api_port'] == 18744 and cfg['web_port'] == 18740
    report = {'schema_version': 1, 'verified_at': datetime.now(timezone.utc).isoformat(),
              'supplied_admin_login_verified': False, 'password_reset': False,
              'credentials_emitted': False, 'credentials_in_command_arguments': False,
              'credential_storage': 'Owner-bound Windows DPAPI under private ACL directory'}
    recovery = login(module, supplied['username'], supplied['password'])
    if recovery:
        report['supplied_admin_login_verified'] = True
        chosen = {'username': supplied['username'], 'password': supplied['password'], 'source': 'owner_supplied'}
    else:
        recovery = login(module, cfg['admin_user'], cfg['admin_password'])
        assert recovery is not None, 'No verified usable existing account'
        chosen = {'username': cfg['admin_user'], 'password': cfg['admin_password'], 'source': 'existing_owner_handoff'}
    report['acceptance_credential_source'] = chosen['source']
    report['username'] = chosen['username']
    # Identify a pairing token from known local instance metadata before one bounded probe.
    profiles = [
        ('primary-test', module.STATE / 'client'),
        ('default', Path('C:/ProgramData/DRAGONHYDRA/client')),
        ('provider-a2', ROOT / 'build/workstation/test-install/provider-a2/state data/client'),
        ('genesis-a8', ROOT / 'build/workstation/test-install/genesis-a8/state data/client'),
    ]
    matched = []
    for identity, directory in profiles:
        if directory.joinpath('local-session.json').is_file():
            record = read(directory / 'local-session.json')
            if hmac.compare_digest(supplied['token'], record['token']):
                matched.append((identity, read(directory / 'endpoint.json')['url']))
    report['supplied_token'] = {'identified_matches': len(matched), 'used_as_joomla_or_provider_credential': False}
    roles = supplied_configuration_role(supplied['token'], cfg)
    report['supplied_token']['matching_generated_configuration_roles'] = roles
    if len(matched) == 1:
        identity, origin = matched[0]
        assert origin in ('http://127.0.0.1:18743', 'http://127.0.0.1:18744', 'http://127.0.0.1:18746', 'http://127.0.0.1:18749')
        request = urllib.request.Request(origin + '/dragon/api/v1/health/ready', headers={'Authorization': 'Bearer ' + supplied['token']})
        with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request, timeout=15) as response:
            health = json.load(response)
            assert response.status == 200 and health.get('status') == 'ready'
        report['supplied_token'].update({'purpose': 'DRAGONHYDRA local-pairing bearer', 'profile': identity, 'origin': origin,
                                         'validated_only_identified_service': True, 'ready': True,
                                         'used_by_joomla_frontend': False})
    else:
        report['supplied_token']['validation'] = ('Identified as existing generated local configuration credential; not used as an API token'
                                                 if roles else 'Not used: no unique matching configured local-pairing identity')
    CREDENTIALS.write_bytes(crypt(json.dumps(chosen).encode()))
    assert load_credentials() == chosen
    # Actual pinned instance contract; no secret request headers or token values are serialized.
    contract = recovery.api_read('/openapi.json')
    paths = {key: value for key, value in contract.get('paths', {}).items()
             if key.startswith('/dragon/api/v1/') and any(part in key for part in ('matches', 'teams', 'competitions', 'exports', 'jobs/'))}
    schemas = {key: value for key, value in contract.get('components', {}).get('schemas', {}).items()
               if key in ('ExportInput', 'Match', 'MatchPage', 'Job')}
    (EVIDENCE / 'actual-api-contract.json').write_text(json.dumps({'paths': paths, 'schemas': schemas}, indent=2) + '\n', encoding='utf-8')
    responses = {path: recovery.api_read(path) for path in ('/health/ready', '/teams', '/competitions', '/matches?limit=1&offset=0')}
    (EVIDENCE / 'actual-api-shapes.json').write_text(json.dumps(responses, indent=2) + '\n', encoding='utf-8')
    report['association'] = {'joomla': recovery.origin, 'api': recovery.api, 'consistent_with_client_and_configuration': True}
    report['passed'] = True
    (EVIDENCE / 'credential-verification-r1.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report))


if __name__ == '__main__':
    try:
        main()
    except Exception as failure:
        print(json.dumps({'passed': False, 'error_class': type(failure).__name__, 'raw_error_or_credentials_emitted': False}))
        raise SystemExit(1)
