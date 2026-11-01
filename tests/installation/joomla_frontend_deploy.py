"""Apply one verified component/template package to the fixed, backed-up site."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT / 'build/joomla-frontend-20261101'
STATE = ROOT / 'build/workstation/test-install/state data'
PHP = ROOT / 'build/workstation/test-install/application files/web/php/php.exe'


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    package = args.package.resolve(); output = args.output.resolve()
    assert package.is_relative_to(ROOT / 'dist/joomla')
    assert output.parent == WORK / 'evidence' and not output.exists()
    cfg = read(STATE / 'workstation.json')
    assert cfg['service_name'] == 'DragonhydraWorkstationTest' and cfg['web_port'] == 18740 and cfg['api_port'] == 18744
    assert read(WORK / 'evidence/backup-r1.json')['passed'] and (WORK / 'evidence/deployment-plan.json').exists()
    manifest = read(package.with_suffix('.manifest.json'))
    assert sha(package) == manifest['sha256'] and manifest['version'] == '0.4.1-dev.2'
    command = [str(PHP), '-c', str(STATE / 'web-config/php.ini'), str(STATE / 'site/cli/joomla.php'),
               'extension:install', '--path=' + str(package), '--no-interaction', '--no-ansi']
    report = {'schema_version': 1, 'passed': False, 'started_at': datetime.now(timezone.utc).isoformat(),
              'scope': 'Original DragonhydraWorkstationTest Joomla CLI supported package install/upgrade',
              'package': str(package), 'bytes': package.stat().st_size, 'sha256': sha(package),
              'source_sha': manifest.get('source_sha'), 'command': command, 'service_restart_requested': False}
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=150)
    # Installer diagnostics are retained only after private-value redaction.
    from joomla_frontend_credentials import load_credentials
    secrets = [load_credentials()['password'], read(STATE / 'client/local-session.json')['token']]
    secrets += [cfg[key] for key in ('root_password', 'db_password', 'core_db_password', 'admin_password')]
    def redact(text):
        for value in secrets:
            text = text.replace(value, '[REDACTED]')
        return text
    report.update({'exit_code': result.returncode, 'stdout': redact(result.stdout), 'stderr': redact(result.stderr),
                   'finished_at': datetime.now(timezone.utc).isoformat(), 'passed': result.returncode == 0})
    output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'passed': report['passed'], 'exit_code': result.returncode, 'report': str(output),
                      'safe_output': report['stdout'][-2500:], 'safe_error': report['stderr'][-1000:]}, indent=2))
    raise SystemExit(result.returncode)


if __name__ == '__main__':
    main()
