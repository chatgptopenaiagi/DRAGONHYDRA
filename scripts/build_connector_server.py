"""Build an isolated development server from a hashed, scoped source snapshot.

This deliberately does not invoke the source-locked release or workstation
installer: their verified immutable component versions are separate artifacts.
Run with the existing Python 3.14 server environment. No packages are installed.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile


ROOT = Path(__file__).resolve().parents[1]
LAB = Path(r'C:\xampp\DRAGONHYDRA-CORE-NEXT-LAB')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work', type=Path, required=True,
                        help='Fresh directory within build/connections; existing evidence is never overwritten')
    parser.add_argument('--builder-packages', type=Path, default=ROOT / 'runtime/genesis2-pyinstaller-builder')
    parser.add_argument('--skip-verification', action='store_true', help='Build only; report remains built_unverified')
    parser.add_argument('--source-sha', help='Exact clean candidate Git commit; never inferred for a working-tree build')
    args = parser.parse_args()
    if os.name != 'nt' or sys.version_info[:2] != (3, 14):
        raise SystemExit('This development payload requires the existing Windows Python 3.14 server runtime.')
    work, packages = args.work.resolve(), args.builder_packages.resolve()
    allowed_roots = [ROOT/'build/connections',LAB/'build']
    if not any(work.is_relative_to(parent) and work != parent for parent in allowed_roots):
        raise SystemExit('Use a fresh owned child directory beneath build/connections or the CORE NEXT lab build root.')
    if work.exists():
        raise SystemExit('The selected build directory already exists; preserve it and choose a fresh directory.')
    if not any(packages.is_relative_to(parent) for parent in [ROOT,LAB/'tools']) or not (packages / 'PyInstaller').is_dir():
        raise SystemExit('The existing project-local PyInstaller package directory is unavailable.')
    for path in [work,packages]:
        for parent in [path,*path.parents]:
            if parent.is_symlink() or getattr(parent,'is_junction',lambda:False)():
                raise SystemExit('Linked build/package directories are not isolated.')
    if args.source_sha:
        head = subprocess.check_output(['git','-C',str(ROOT),'rev-parse','HEAD'],text=True).strip()
        if args.source_sha != head:
            raise SystemExit('Frozen source commit differs from the candidate checkout.')
        changes = subprocess.check_output(['git','-C',str(ROOT),'status','--porcelain','--untracked-files=all'],text=True)
        if changes.strip():
            raise SystemExit('Commit candidate source and reports before the release build; tracked/untracked changes exist.')
    canonical = {}
    if args.source_sha:
        archived = subprocess.check_output(['git','-C',str(ROOT),'archive','--format=zip',args.source_sha])
        with zipfile.ZipFile(io.BytesIO(archived)) as archive:
            canonical = {name:archive.read(name) for name in archive.namelist() if not name.endswith('/')}

    # Scope is explicit: importable product source and the three packaging inputs.
    # Databases, raw acquired connector bytes, credentials and old releases never
    # enter the snapshot. Only the reviewed, bundled public sample resources do.
    selected = []
    for path in (ROOT / 'src/dragonhydra').rglob('*'):
        if path.is_file() and '__pycache__' not in path.parts and path.suffix != '.pyc' and path.name != 'build_info.json':
            if not (path.suffix == '.py' or path.is_relative_to(ROOT / 'src/dragonhydra/resources')):
                raise SystemExit('Unexpected product source input: ' + str(path.relative_to(ROOT)))
            selected.append(path)
    selected += [ROOT / 'packaging/windows' / name
                 for name in ('product-server.spec', 'server_entry.py', 'version_info.txt')]
    selected += [ROOT / 'packaging/release/version.json']
    selected += [ROOT / 'tests/installation' / name
                 for name in ('frozen_server.py', 'connector_payload.py')]
    selected += [Path(__file__).resolve()]
    required_context_inputs = [ROOT/'src/dragonhydra'/name for name in (
        'local_ai.py', 'local_ai_context.py', 'local_ai_service.py', 'api.py', 'api_contracts.py', 'jobs.py',
        'source_context.py', 'connectors/statsbomb_context.py', 'connectors/statsbomb_context_parser.py',
        'connectors/statsbomb_context_jobs.py', 'connectors/statsbomb_context_view.py',
        'resources/web/app.js', 'resources/web/index.html', 'resources/web/style.css')]
    if not set(required_context_inputs).issubset(selected):
        raise SystemExit('The scoped source is missing a context module or dashboard input.')
    files = []
    for path in sorted(selected):
        if path.is_symlink() or path.stat().st_size > 8 * 1024 * 1024:
            raise SystemExit('Unexpected linked or oversized source input: ' + str(path.relative_to(ROOT)))
        name = path.relative_to(ROOT).as_posix()
        raw = canonical[name] if args.source_sha else path.read_bytes()
        files.append({'path': name, 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()})
    serialized = json.dumps(files, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()
    source_hash = hashlib.sha256(serialized).hexdigest()
    work.mkdir(parents=True)
    snapshot = work / 'source'
    for entry in files:
        original, target = ROOT / entry['path'], snapshot / entry['path']
        target.parent.mkdir(parents=True, exist_ok=True)
        if args.source_sha:
            target.write_bytes(canonical[entry['path']])
        else:
            shutil.copyfile(original, target)
        if digest(target) != entry['sha256']:
            raise RuntimeError('Source changed while snapshotting: ' + entry['path'])
    source_manifest = {'schema_version': 1, 'kind': 'scoped_working_tree_snapshot',
                       'source_sha': args.source_sha, 'content_sha256': source_hash, 'files': files}
    write_json(work / 'SOURCE-MANIFEST.json', source_manifest)
    # Preserve version/API compatibility while explicitly identifying development
    # content by its SHA-256, never by the unrelated current Git HEAD commit.
    matrix = json.loads((snapshot / 'packaging/release/version.json').read_text())
    metadata = {'version': matrix['product_version'], 'python_version': matrix['python_version'],
                'source_sha': args.source_sha, 'api_namespace': matrix['api_namespace'],
                'schema_version': matrix['schema_version'], 'build_kind': 'core-next-frozen-source' if args.source_sha else 'connector-development-snapshot',
                'source_content_sha256': source_hash, 'source_manifest': 'SOURCE-MANIFEST.json'}
    write_json(work / 'build_info.json', metadata)
    report = {'schema_version': 1, 'status': 'running', 'started_at': datetime.now(timezone.utc).isoformat(),
              'source_content_sha256': source_hash, 'source_manifest': 'SOURCE-MANIFEST.json',
              'python': sys.executable, 'python_version': sys.version, 'builder_packages': str(packages),
              'versions': {name: importlib.metadata.version(name) for name in ('fastapi', 'uvicorn', 'tzdata', 'openpyxl')},
              'required_context_inputs': [path.relative_to(ROOT).as_posix() for path in required_context_inputs],
              'commands': [], 'scope': 'Unsigned development Windows x64 server; no installer replacement or clean-machine claim'}
    env = os.environ.copy()
    env['PYTHONPATH'] = str(snapshot / 'src') + os.pathsep + str(packages)
    env['PYTHONNOUSERSITE'] = '1'
    env['PYINSTALLER_CONFIG_DIR'] = str(work/'tool-cache')
    env['DRAGONHYDRA_BUILD_INFO'] = str(work / 'build_info.json')
    for name in ('PYTHONHOME', 'DRAGONHYDRA_SOURCE_SHA'):
        env.pop(name, None)

    def run(name, argv):
        print('COMMAND:', subprocess.list2cmdline(list(map(str, argv))), flush=True)
        started = datetime.now(timezone.utc)
        with (work / (name + '.log')).open('w', encoding='utf-8') as output:
            result = subprocess.run(list(map(str, argv)), cwd=snapshot, env=env,
                                    stdout=output, stderr=subprocess.STDOUT)
        report['commands'].append({'name': name, 'argv': list(map(str, argv)), 'exit_code': result.returncode,
                                   'seconds': (datetime.now(timezone.utc) - started).total_seconds(), 'log': name + '.log'})
        print('OUTPUT:', name, 'exit', result.returncode, 'log', str(work / (name + '.log')), flush=True)
        if result.returncode:
            raise RuntimeError(name + ' failed; inspect its retained log.')

    try:
        run('pyinstaller', [sys.executable, '-B', '-m', 'PyInstaller', '--noconfirm',
                           '--distpath', work / 'dist', '--workpath', work / 'pyinstaller',
                           snapshot / 'packaging/windows/product-server.spec'])
        payload = work / 'dist/DRAGONHYDRA-Server-x64'
        binary = payload / 'DRAGONHYDRA-Server.exe'
        if not binary.is_file():
            raise RuntimeError('Expected private-runtime server executable was not produced.')
        shutil.copyfile(work / 'SOURCE-MANIFEST.json', payload / 'SOURCE-MANIFEST.json')
        shutil.copyfile(work / 'build_info.json', payload / 'BUILD-INFO.json')
        if not (payload / '_internal/tzdata/zoneinfo/America/New_York').is_file():
            raise RuntimeError('The frozen runtime is missing its required Eastern timezone data.')
        for name in ('app.js', 'index.html', 'style.css'):
            if digest(payload / '_internal/dragonhydra/resources/web' / name) != digest(snapshot / 'src/dragonhydra/resources/web' / name):
                raise RuntimeError('Frozen dashboard resource drift: ' + name)
        if not args.skip_verification:
            run('frozen-server', [sys.executable, '-B', snapshot / 'tests/installation/frozen_server.py',
                                  '--binary', binary, '--output', work / 'frozen-server.json'])
            run('connector-payload', [sys.executable, '-B', snapshot / 'tests/installation/connector_payload.py',
                                     '--binary', binary, '--work', work / 'connector-check',
                                     '--source-content-sha256', source_hash])
        report['status'] = 'built_unverified' if args.skip_verification else 'verified_current_host'
        report['payload'] = str(payload)
        inventory = [{'path': path.relative_to(payload).as_posix(), 'bytes': path.stat().st_size, 'sha256': digest(path)}
                     for path in sorted(payload.rglob('*')) if path.is_file()]
        manifest = {'schema_version': 1, 'files': inventory}
        write_json(work / 'PAYLOAD-MANIFEST.json', manifest)
        write_json(payload / 'PAYLOAD-MANIFEST.json', manifest)
        report['binary_sha256'] = digest(binary)
        report['payload_files'] = len(inventory)
    except Exception as exc:
        report.update(status='failed', error=str(exc))
        raise
    finally:
        report['finished_at'] = datetime.now(timezone.utc).isoformat()
        write_json(work / 'BUILD-REPORT.json', report)
        print(json.dumps({key: report.get(key) for key in ('status', 'source_content_sha256', 'payload', 'binary_sha256')}, indent=2), flush=True)


if __name__ == '__main__':
    main()
