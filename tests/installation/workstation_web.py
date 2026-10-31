"""Run file-only provisioning checks against an assembled private web payload.

Does not launch Apache/MariaDB or access the working application. Integration
installation and real Joomla browser checks belong to the coordinating harness.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import socket
import subprocess
from pathlib import Path


def sha(path: Path) -> str:
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def free_ports() -> list[int]:
    listeners = [socket.socket() for _ in range(3)]
    try:
        for listener in listeners:
            listener.bind(('127.0.0.1', 0))
        return [listener.getsockname()[1] for listener in listeners]
    finally:
        for listener in listeners:
            listener.close()


def run(payload: Path, cfg: Path, action: str, *, bare: bool = False) -> subprocess.CompletedProcess:
    state = json.loads(cfg.read_text(encoding='utf-8'))
    command = [str(payload / 'php/php.exe')]
    command += ['-n'] if bare else ['-c', str(Path(state['state_root']) / 'web-config/php.ini')]
    command += [str(payload / 'manage.php'), str(cfg), action]
    env = dict(os.environ)
    env['PATH'] = os.pathsep.join(str(payload / name) for name in ['php', 'apache/bin', 'mariadb/bin']) + os.pathsep + env.get('PATH', '')
    return subprocess.run(command, capture_output=True, text=True, timeout=120, env=env)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--payload', type=Path, required=True)
    parser.add_argument('--state', type=Path, required=True)
    parser.add_argument('--evidence', type=Path, required=True)
    args = parser.parse_args()
    payload = args.payload.resolve()
    state = args.state.resolve()
    if state.exists() and any(state.iterdir()):
        raise ValueError('Use a new isolated test state directory')
    state.mkdir(parents=True, exist_ok=True)
    args.evidence.parent.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((payload / 'payload-manifest.json').read_text(encoding='utf-8'))
    assertions = []
    for entry in manifest['files']:
        file = payload / entry['path']
        assert file.stat().st_size == entry['bytes'] and sha(file) == entry['sha256'], entry['path']
    assertions.append({'name': 'payload_inventory_hashes', 'passed': True, 'files': len(manifest['files'])})
    ports = free_ports()
    cfg = {'install_root': str(payload.parent), 'state_root': str(state), 'web_port': ports[0],
           'database_port': ports[1], 'api_port': ports[2], 'api_base': f'http://127.0.0.1:{ports[2]}/dragon/api/v1',
           'bridge_secret_path': str(state / 'kernel/joomla-bridge.json'), 'root_password': secrets.token_urlsafe(36),
           'db_name': 'dragonhydra_admin', 'db_user': 'dragonhydra_admin', 'db_password': secrets.token_urlsafe(36),
           'core_db_name': 'dragonhydra_core', 'core_db_user': 'dragonhydra_core', 'core_db_password': secrets.token_urlsafe(36),
           'admin_user': 'dragon-workstation-test', 'admin_password': secrets.token_urlsafe(36),
           'admin_email': 'workstation@dragonhydra.invalid', 'site_name': 'DRAGONHYDRA isolated preparation test'}
    cfg_path = state / 'private-test.json'
    cfg_path.write_text(json.dumps(cfg), encoding='utf-8')
    initial = run(payload, cfg_path, 'prepare', bare=True)
    assert initial.returncode == 0, initial.stdout + initial.stderr
    result = json.loads(initial.stdout)
    assert result['prepared'] and result['database_connection_attempted'] is False
    assert not (state / 'mysql-data/mysql').exists()
    assert (state / 'site/installation/joomla.php').is_file()
    assertions.append({'name': 'bare_php_prepare_without_database', 'passed': True})
    # Simulate the installer's one-time removal; repair must not restore it.
    installer = state / 'site/installation/joomla.php'
    installer.unlink()
    repeated = run(payload, cfg_path, 'prepare', bare=True)
    assert repeated.returncode == 0 and not installer.exists()
    for name in ['my.ini', 'httpd.conf', 'php.ini']:
        content = (state / 'web-config' / name).read_text(encoding='utf-8')
        assert cfg['root_password'] not in content and cfg['db_password'] not in content
    httpd = (state / 'web-config/httpd.conf').read_text(encoding='utf-8')
    assert f'Listen 127.0.0.1:{ports[0]}' in httpd and 'Require local' in httpd
    assert 'ServerRoot "' + str(payload / 'apache').replace('\\', '/') + '"' in httpd
    assertions.append({'name': 'idempotent_prepare_private_portable_configurations', 'passed': True})
    cfg['api_base'] = f'http://127.0.0.1:{ports[2]}/administrator/'
    cfg_path.write_text(json.dumps(cfg), encoding='utf-8')
    rejected = run(payload, cfg_path, 'prepare', bare=True)
    assert rejected.returncode != 0
    error = json.loads(rejected.stdout)
    assert error['error']['code'] == 'API_BASE_MUST_SELECT_LOCAL_VERSIONED_KERNEL'
    assert cfg['root_password'] not in rejected.stdout + rejected.stderr
    assertions.append({'name': 'invalid_identity_endpoint_rejected_without_secrets', 'passed': True})
    cfg['api_base'] = f'http://127.0.0.1:{ports[2]}/dragon/api/v1'
    cfg_path.write_text(json.dumps(cfg), encoding='utf-8')
    report = {'source_sha': manifest['source_sha'], 'passed': True, 'assertions': assertions,
              'services_started': False, 'database_connection_attempted': False,
              'scope': 'File-only private payload provisioning; real installation/browser tests reported separately'}
    args.evidence.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
