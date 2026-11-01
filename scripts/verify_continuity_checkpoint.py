"""Read-only continuity hash verification; never executes historical acceptance helpers."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.is_relative_to(ROOT / 'build') or output.exists():
        parser.error('Use a fresh report path beneath this repository build directory')
    checks = []

    def read(path):
        return json.loads((ROOT / path).read_text(encoding='utf-8-sig'))

    def verify(path, expected, size=None):
        target = ROOT / path
        actual = None
        if target.is_file():
            with target.open('rb') as handle:
                actual = hashlib.file_digest(handle, 'sha256').hexdigest()
        length = target.stat().st_size if target.is_file() else None
        checks.append(dict(path=Path(path).as_posix(), expected_sha256=expected,
                           sha256=actual, bytes=length,
                           passed=actual == expected and (size is None or length == size)))

    state = read('docs/handover/ENGINEERING-STATE.json')
    for item in read('docs/handover/VERIFIED-ARTIFACTS.json')['artifacts']:
        verify(item['path'], item['sha256'], item['bytes'])
    a6 = state['a6']
    for phase in ('preflight', 'repair', 'readchecks', 'independent_installed_acceptance'):
        verify(a6[phase]['receipt'], a6[phase]['sha256'])
    verify(a6['installed_summary']['path'], a6['installed_summary']['sha256'])
    linux = state['linux_a6_preparation']
    work = Path(linux['work'])
    verify(linux['archive']['path'], linux['archive']['sha256'], linux['archive']['bytes'])
    verify(work / 'wheel' / linux['wheel']['filename'], linux['wheel']['sha256'], linux['wheel']['bytes'])
    verify(linux['receipt'], linux['receipt_sha256'])
    verify(linux['independent_review']['path'], linux['independent_review']['sha256'])
    integrity = read(linux['receipt'])
    for path, digest in integrity['input_and_evidence_hashes'].items():
        verify(work / path, digest)
    for path, digest in integrity['historical_linux_archives_preserved'].items():
        verify(path, digest)
    verify('scripts/build_linux_bundle.py', linux['builder_sha256'])
    verify('dist/connections/workstation-a5-r2/DRAGONHYDRA-0.4.1-dev.1-Workstation-win-x64-Setup.exe',
           'b8bcc4d7ee26ea7db2f163fd20fecdbd95349ef5ac085d40375f43e5918d7544')
    git = r'C:\Program Files\Git\cmd\git.exe'
    head = subprocess.check_output([git, 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    branch = subprocess.check_output([git, 'branch', '--show-current'], cwd=ROOT, text=True).strip()
    report = dict(schema_version=1, verified_at=datetime.now(timezone.utc).isoformat(),
                  passed=all(c['passed'] for c in checks), branch=branch, head=head,
                  scope='Current file hashes only; historical tests were not rerun',
                  checks=checks, check_count=len(checks), application_execution=False,
                  service_actions=False, database_access=False, model_or_provider_actions=False)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x', encoding='utf-8') as handle:
        json.dump(report, handle, indent=2)
        handle.write('\n')
    print(json.dumps({'passed': report['passed'], 'checks': len(checks),
                      'failures': [c for c in checks if not c['passed']], 'output': str(output)}))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
