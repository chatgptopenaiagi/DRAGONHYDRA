"""Build an isolated development server from a hashed, scoped source snapshot.

This deliberately does not invoke the source-locked release or workstation
installer: their verified immutable component versions are separate artifacts.
Run with the existing Python 3.14 server environment. No packages are installed.
"""
from __future__ import annotations

import argparse
import base64
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import zipfile


ROOT = Path(__file__).resolve().parents[1]
LAB = Path(r'C:\xampp\DRAGONHYDRA-CORE-NEXT-LAB')
SQL_SCHEMA = Path('src/dragonhydra/research_storage/schema_sqlserver.sql')
RESEARCH_INPUTS = tuple(Path('src/dragonhydra/research_storage') / name for name in
                        ('__init__.py', 'base.py', 'service.py', 'sqlite.py', 'sqlserver.py', 'schema_sqlserver.sql'))
SQL_DRIVER_LOCK = Path('config/runtime/sqlserver-python314-windows.lock.txt')
PUBLIC_RESEARCH_INPUTS = (
    (Path('config/research-storage.example.json'), Path('config/research-storage.example.json')),
    (SQL_DRIVER_LOCK, Path('config/runtime/sqlserver-python314-windows.lock.txt')),
    (Path('docs/integrations/MICROSOFT-SQLSERVER-INTEGRATION.md'), Path('docs/MICROSOFT-SQLSERVER-INTEGRATION.md')),
)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')


def product_inputs(root):
    """Allow the one reviewed SQL resource, not arbitrary runtime/config data."""
    selected = []
    for path in (root / 'src/dragonhydra').rglob('*'):
        if path.is_file() and '__pycache__' not in path.parts and path.suffix != '.pyc' and path.name != 'build_info.json':
            if not (path.suffix == '.py' or path.is_relative_to(root / 'src/dragonhydra/resources')
                    or path == root / SQL_SCHEMA):
                raise RuntimeError('Unexpected product source input: ' + str(path.relative_to(root)))
            selected.append(path)
    if not set(root / name for name in RESEARCH_INPUTS).issubset(selected):
        raise RuntimeError('The scoped source is missing a research adapter or SQL schema input.')
    return selected


def research_driver(root, wheel):
    """Pin the optional native connector for this Windows distribution only.

    This validates installed wheel bytes, without connecting to SQL Server or
    asserting availability of the separately installed Microsoft ODBC driver.
    PyInstaller follows the extension's native imports using its existing hook.
    """
    lock = (root / SQL_DRIVER_LOCK).read_text(encoding='utf-8')
    pins = re.findall(r'^pyodbc==([^\s]+)\s+--hash=sha256:([a-f0-9]{64})\s*$', lock, re.M)
    if len(pins) != 1:
        raise RuntimeError('Expected one hash-pinned Windows pyodbc dependency.')
    wheel = Path(os.path.abspath(wheel))
    for path in (wheel, *wheel.parents):
        if path.is_symlink() or getattr(path, 'is_junction', lambda: False)():
            raise RuntimeError('Linked SQL connector wheel input is not permitted.')
    if (wheel.name != 'pyodbc-'+pins[0][0]+'-cp314-cp314-win_amd64.whl'
            or not wheel.is_file() or digest(wheel) != pins[0][1]):
        raise RuntimeError('SQL connector wheel differs from the Windows dependency lock.')
    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
        if len(set(name.lower() for name in names)) != len(names):
            raise RuntimeError('Duplicate SQL connector wheel member.')
        native = {name: hashlib.sha256(archive.read(name)).hexdigest()
                  for name in names if Path(name).suffix.lower() in ('.pyd', '.dll')}
    distribution = importlib.metadata.distribution('pyodbc')
    if distribution.version != pins[0][0]:
        raise RuntimeError('Installed pyodbc differs from the Windows SQL dependency lock.')
    binaries = []
    for entry in distribution.files or ():
        if entry.suffix.lower() not in ('.pyd', '.dll'):
            continue
        path = Path(distribution.locate_file(entry))
        if path.is_symlink() or not path.is_file() or not entry.hash or entry.hash.mode != 'sha256':
            raise RuntimeError('SQL connector binary has no regular hash-verified wheel member.')
        expected = base64.urlsafe_b64decode(entry.hash.value + '=' * (-len(entry.hash.value) % 4)).hex()
        if (native.get(entry.as_posix()) != expected or digest(path) != expected
                or (entry.size is not None and path.stat().st_size != entry.size)):
            raise RuntimeError('SQL connector binary differs from its installed wheel RECORD.')
        binaries.append({'path': str(path), 'name': entry.as_posix(), 'bytes': path.stat().st_size, 'sha256': expected})
    if len([entry for entry in binaries if entry['name'] == 'pyodbc.cp314-win_amd64.pyd']) != 1:
        raise RuntimeError('The Windows CPython 3.14 x64 SQL connector extension is unavailable.')
    if set(native) != {entry['name'] for entry in binaries}:
        raise RuntimeError('The installed SQL connector native members differ from the locked wheel.')
    return {'version': distribution.version, 'wheel': str(wheel), 'wheel_sha256': pins[0][1], 'binaries': binaries,
            'host_prerequisite': 'Microsoft ODBC Driver 18 and an explicitly configured accessible SQL Server; neither is bundled'}


def verify_research_payload(payload, snapshot, driver):
    schema = payload / '_internal/dragonhydra/research_storage/schema_sqlserver.sql'
    if not schema.is_file() or digest(schema) != digest(snapshot / SQL_SCHEMA):
        raise RuntimeError('Frozen SQL schema is missing or differs from the scoped source.')
    for entry in driver['binaries']:
        # The pinned pyodbc wheel is a top-level extension. Any future vendor
        # directory remains relative to site-packages; never accept a basename-only match.
        target = payload / '_internal' / entry['name']
        if not target.is_file() or digest(target) != entry['sha256']:
            raise RuntimeError('Frozen SQL connector binary is missing or changed: ' + entry['name'])


def copy_research_guidance(payload, snapshot):
    """Ship only these Git-bound public instructions, never installed settings."""
    for source, relative in PUBLIC_RESEARCH_INPUTS:
        original, target = snapshot / source, payload / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(original, target)
        if digest(target) != digest(original):
            raise RuntimeError('Standalone research instructions changed while copying: ' + source.as_posix())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work', type=Path, required=True,
                        help='Fresh directory within build/connections; existing evidence is never overwritten')
    parser.add_argument('--builder-packages', type=Path, default=ROOT / 'runtime/genesis2-pyinstaller-builder')
    parser.add_argument('--sqlserver-wheel', type=Path, required=True,
                        help='Existing Windows CPython 3.14 x64 pyodbc wheel, verified against the scoped public lock; never installed by this builder')
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
    selected = product_inputs(ROOT)
    driver = research_driver(ROOT, args.sqlserver_wheel)  # Fail before creating a build on missing/unverified optional native inputs.
    selected += [ROOT / 'packaging/windows' / name
                 for name in ('product-server.spec', 'server_entry.py', 'version_info.txt')]
    selected += [ROOT / 'packaging/release/version.json']
    selected += [ROOT / source for source, _ in PUBLIC_RESEARCH_INPUTS]
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
              'research_storage': driver,
              'required_research_inputs': [path.as_posix() for path in RESEARCH_INPUTS],
              'public_research_inputs': [{'source': source.as_posix(), 'payload': target.as_posix()}
                                        for source, target in PUBLIC_RESEARCH_INPUTS],
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
        verify_research_payload(payload, snapshot, driver)
        copy_research_guidance(payload, snapshot)
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
