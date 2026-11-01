"""Offline A7 archive install in the dedicated Docker acceptance container.

Mount the checkout read-only at /inputs and an owned evidence directory at
/evidence. Run as container root for installation, then run acceptance as10001.
No host services, global host dependencies, or live application state change.
"""
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import tarfile

ROOT = Path('/opt/dragonhydra-a7-acceptance')
INPUTS = Path('/inputs')
EVIDENCE = Path('/evidence')
ARCHIVE = INPUTS/'build/linux/prep-20261101-a7/dragonhydra-linux-dev-8f170de1559b.tar.gz'
SOURCE = INPUTS/'build/connections/sports-package-3-20261031/qwen-api-r1/api-state'

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def source_hashes():
    return {p.relative_to(SOURCE).as_posix(): sha(p)
            for p in [SOURCE/'core.sqlite3', *sorted((SOURCE/'raw').rglob('*.payload'))]}

def main():
    report = {'passed': False, 'commands': [], 'service_activated': False,
              'source_mounted_readonly': True, 'network': 'none'}
    try:
        assert sha(ARCHIVE) == 'a146186c9a1416059fbd6e9978a3da7a62ec8592b8ed9dae6989a04a934ca05a'
        ROOT.mkdir(mode=0o700)  # Refuse existing output; retain all diagnostics.
        with tarfile.open(ARCHIVE) as package:
            package.extractall(ROOT/'bundle', filter='data')
        bundle = ROOT/'bundle/dragonhydra-linux-dev-8f170de1559b'
        state, prefix = ROOT/'state', ROOT/'installed'
        command = ['/bin/bash', str(bundle/'install.sh'), '--prefix', str(prefix),
                   '--state', str(state), '--port', '18763', '--apply']
        result = subprocess.run(command, capture_output=True, text=True, timeout=120)
        (EVIDENCE/'a7-install.stdout.log').write_text(result.stdout)
        (EVIDENCE/'a7-install.stderr.log').write_text(result.stderr)
        report['commands'].append({'argv': command, 'exit_code': result.returncode})
        assert result.returncode == 0, 'Inspect retained installation logs'
        report['installation'] = json.loads(result.stdout.strip().splitlines()[-1])
        assert report['installation']['installation']['server_import_verified']
        # Only this historical stopped snapshot with empty WAL is eligible for
        # immutable reading; never use this recipe against an active database.
        assert (SOURCE/'core.sqlite3-wal').stat().st_size == 0
        before = source_hashes()
        with closing(sqlite3.connect((SOURCE/'core.sqlite3').as_uri()+'?mode=ro&immutable=1', uri=True)) as source:
            with closing(sqlite3.connect(state/'core.sqlite3')) as target:
                source.backup(target)
                report['cancelled_copied_jobs'] = target.execute(
                    "UPDATE product_jobs SET status='cancelled',cancel_requested=1 WHERE status IN ('queued','running','interrupted')").rowcount
                target.execute('UPDATE connector_settings SET interval_seconds=0,next_due=0')
                target.commit()
        shutil.copytree(SOURCE/'raw', state/'raw')
        report['source_before'], report['source_after'] = before, source_hashes()
        assert report['source_before'] == report['source_after']
        for path in [ROOT, *ROOT.rglob('*')]:
            os.chown(path, 10001, 10001)
        state.chmod(0o700)
        (state/'core.sqlite3').chmod(0o600)
        report.update(passed=True, runtime_uid=10001, state_mode='0700', database_mode='0600')
    finally:
        temporary = EVIDENCE/'A7-INSTALLATION.json.tmp'
        temporary.write_text(json.dumps(report, indent=2)+'\n')
        temporary.replace(EVIDENCE/'A7-INSTALLATION.json')
    print(json.dumps({'passed': report['passed']}))

if __name__ == '__main__':
    main()
