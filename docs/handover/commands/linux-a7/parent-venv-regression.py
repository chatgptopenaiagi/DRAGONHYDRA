"""Offline Linux parent-venv regression, with no retained application data.

Run in a fresh CPython3.14 Linux container with the repository mounted read-only
at /repo and a fresh writable evidence directory at /evidence. The17 cached
wheels and original frozen A6 bundle are required. Disable container networking.
The original A6 installer remains untouched; current source must reject its
inaccessible child dependencies. This creates only disposable /tmp prefixes.
"""
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path('/repo')
EVIDENCE = Path('/evidence')
BUNDLE = ROOT / 'build/linux/prep-20261031-a6/dragonhydra-linux-dev-3319aed91dd0'


def run(command):
    result = subprocess.run([str(item) for item in command], capture_output=True, text=True, timeout=90)
    return {'command': [str(item) for item in command], 'exit_code': result.returncode,
            'stdout': result.stdout, 'stderr': result.stderr}


def main():
    destination = EVIDENCE / 'PARENT-VENV-REGRESSION.json'
    if destination.exists():
        raise FileExistsError('Use a fresh evidence directory; prior reports are preserved')
    report = {'python': sys.version, 'network': 'none', 'steps': []}
    parent = Path('/tmp/a7-parent-probe')
    for command in (
        [sys.executable, '-m', 'venv', parent],
        [parent / 'bin/python', '-m', 'pip', 'install', '--no-index', '--require-hashes',
         '--find-links', ROOT / 'runtime/linux-native/locked-wheels', '-r',
         ROOT / 'build/linux/native-kernel-20261031/public-r4/requirements.lock'],
    ):
        step = run(command)
        report['steps'].append(step)
        if step['exit_code']:
            raise RuntimeError(step)
    old = run([parent / 'bin/python', BUNDLE / 'preflight.py', '--bundle', BUNDLE,
               '--prefix', '/tmp/a7-old-install', '--state', '/tmp/a7-old-state', '--apply'])
    child = run(['/tmp/a7-old-install/venv/bin/python', '-I', '-c', 'import fastapi,uvicorn,openpyxl,tzdata'])
    report['original_installer'] = old
    report['original_child_import'] = child
    report['original_false_success_reproduced'] = old['exit_code'] == 0 and child['exit_code'] != 0
    fixed = run([parent / 'bin/python', ROOT / 'packaging/linux/preflight.py', '--bundle', BUNDLE,
                 '--prefix', '/tmp/a7-fixed-install', '--state', '/tmp/a7-fixed-state', '--apply'])
    report['current_installer'] = fixed
    report['current_state_created'] = Path('/tmp/a7-fixed-state').exists()
    report['current_launcher_created'] = Path('/tmp/a7-fixed-install/run-server.sh').exists()
    report['fixed_fail_closed'] = (fixed['exit_code'] == 2
                                   and 'INSTALLED_RUNTIME_DEPENDENCIES_UNAVAILABLE' in fixed['stdout']
                                   and not report['current_state_created']
                                   and not report['current_launcher_created'])
    report['passed'] = report['original_false_success_reproduced'] and report['fixed_fail_closed']
    destination.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({key: report[key] for key in ('original_false_success_reproduced', 'fixed_fail_closed', 'passed')}))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
