"""Build a Linux wheel from complete frozen A4 application inputs, never live src.

Only selected hash-verified build metadata/templates come from older prep-r2.
No dependency installation, download, service change or existing output rewrite.
"""
from __future__ import annotations

import argparse
import base64
import configparser
import csv
from datetime import datetime, timezone
from email.parser import BytesParser
import hashlib
from importlib import metadata
import io
import json
import os
from pathlib import Path, PurePosixPath
import runpy
import shutil
import stat
import subprocess
import sys
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[2]
A4 = ROOT/'build/connections/payload-20261031-a4'
PREP = ROOT/'build/linux/prep-20261031-r2'
PREP_BUNDLE = PREP/'dragonhydra-linux-dev-9f3d6e5ab108'
A4_HASH = '8b3e7e0e440b9f4d090517237724999bcd824d86f460663e65d940c9c1d20fd5'
PREP_HASH = '9f3d6e5ab1082a81c19308cdce3bea2e1efd3d31729227a027248644d56a86c4'
TEMPLATES = ('preflight.py', 'install.sh', 'run-server.sh', 'dragonhydra.service.in', 'README.md')
BUILD_SUPPORT = ('pyproject.toml', 'README.md', 'config/runtime/server-python314.lock.txt',
                 *(f'packaging/linux/{name}' for name in TEMPLATES))
FORBIDDEN = {'.db', '.sqlite3', '.dpapi', '.pem', '.key', '.pfx', '.jks', '.keystore', '.pyc', '.gguf'}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def canonical(files):
    return hashlib.sha256(json.dumps(files, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


def write_json(path, document):
    Path(path).write_text(json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False)+'\n', encoding='utf-8')


def safe_relative(value):
    path = PurePosixPath(value)
    if (not isinstance(value, str) or path.is_absolute() or '..' in path.parts
            or '\\' in value or ':' in value or str(path) != value or not path.parts
            or path.suffix.lower() in FORBIDDEN or path.name in ('.env', 'local-session.json', 'vault.json', 'id_rsa', 'id_ed25519')):
        raise ValueError('Unsafe/private frozen input path')
    return path


def verify_snapshot(manifest_path, source, expected_hash, key):
    manifest_path, source = Path(manifest_path), Path(source).resolve()
    document = json.loads(manifest_path.read_text(encoding='utf-8'))
    files, seen = document['files'], set()
    if document.get('source_sha') is not None or not files or canonical(files) != expected_hash or document[key] != expected_hash:
        raise ValueError('Frozen source identity mismatch')
    for item in files:
        name = str(safe_relative(item['path']))
        if name in seen:
            raise ValueError('Duplicate frozen input path')
        seen.add(name)
        target = source/name
        if (target.is_symlink() or not target.is_file() or not target.resolve().is_relative_to(source)
                or any(parent.is_symlink() for parent in target.parents if parent != source and parent.is_relative_to(source))
                or not 0 <= item['bytes'] <= 8*1024*1024 or target.stat().st_size != item['bytes'] or sha(target) != item['sha256']):
            raise ValueError('Frozen input drift: '+name)
    return {'manifest': document, 'source': source, 'manifest_path': manifest_path,
            'expected_hash': expected_hash, 'key': key, 'files': {f['path']: f for f in files}}


def checked_copy(source, destination, entry):
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)
    if destination.stat().st_size != entry['bytes'] or sha(destination) != entry['sha256']:
        raise ValueError('Input changed during staging: '+entry['path'])


def stage_source(a4, support, destination, tool_path, *, support_names=BUILD_SUPPORT):
    """Copy the full frozen origin first; never start from an old/live src tree."""
    destination = Path(destination)
    if destination.exists():
        raise ValueError('Preserve existing source output')
    entries = dict(a4['files'])
    bindings = {name: a4['source']/name for name in entries}
    for name in support_names:
        safe_relative(name)
        if name in entries:
            raise ValueError('Overlapping application/build-support input: '+name)
        if name not in BUILD_SUPPORT or name not in support['files']:
            raise ValueError('Unsupported build-support input: '+name)
        entries[name] = support['files'][name]
        bindings[name] = support['source']/name
    own_name = 'packaging/linux-native/prepare_frozen_bundle.py'
    if own_name in entries:
        raise ValueError('Packaging tool input collision')
    tool_path = Path(tool_path)
    entries[own_name] = {'path': own_name, 'bytes': tool_path.stat().st_size, 'sha256': sha(tool_path)}
    bindings[own_name] = tool_path
    destination.mkdir(parents=True)
    for name, entry in sorted(entries.items()):
        checked_copy(bindings[name], destination/name, entry)
    expected_app = {name for name in a4['files'] if name.startswith('src/dragonhydra/')}
    actual_app = {p.relative_to(destination).as_posix() for p in (destination/'src/dragonhydra').rglob('*') if p.is_file()}
    if actual_app != expected_app:
        raise ValueError('Incomplete or mixed application source tree')
    for snap in (a4, support):
        verify_snapshot(snap['manifest_path'], snap['source'], snap['expected_hash'], snap['key'])
    files = [entries[name] for name in sorted(entries)]
    document = {'schema_version': 1, 'kind': 'complete-frozen-a4-with-explicit-linux-build-support',
                'source_sha': None, 'source_content_sha256': canonical(files), 'files': files,
                'application_snapshot_sha256': a4['expected_hash'], 'linux_support_snapshot_sha256': support['expected_hash'],
                'application_files': len(expected_app), 'support_files': list(support_names),
                'packaging_tool_sha256': entries[own_name]['sha256']}
    return document


def verify_application_wheel(wheel, source_manifest):
    expected = {item['path'].removeprefix('src/'): item for item in source_manifest['files']
                if item['path'].startswith('src/dragonhydra/')}
    with ZipFile(wheel) as archive:
        members = archive.infolist()
        names = [item.filename for item in members if not item.is_dir()]
        if len(names) != len(set(names)) or not wheel.name.endswith('-py3-none-any.whl'):
            raise ValueError('Invalid wheel names or compatibility tag')
        for item in members:
            safe_relative(item.filename.rstrip('/'))
            if stat.S_ISLNK(item.external_attr >> 16) or item.file_size > 8*1024*1024:
                raise ValueError('Unsafe wheel member')
        actual = {name for name in names if name.startswith('dragonhydra/')}
        if actual != set(expected)|{'dragonhydra/build_info.json'}:
            raise ValueError('Wheel application is incomplete or contains mixed source')
        for name, entry in expected.items():
            raw = archive.read(name)
            if len(raw) != entry['bytes'] or hashlib.sha256(raw).hexdigest() != entry['sha256']:
                raise ValueError('Wheel does not match complete A4 application: '+name)
        identity = json.loads(archive.read('dragonhydra/build_info.json'))
        if (identity.get('source_sha') is not None or identity.get('source_content_sha256') != source_manifest['source_content_sha256']
                or identity.get('application_snapshot_sha256') != source_manifest['application_snapshot_sha256']):
            raise ValueError('Wheel origin/composite identity mismatch')
        prefix = 'dragonhydra-0.4.0a1.dist-info/'
        meta = BytesParser().parsebytes(archive.read(prefix+'METADATA'))
        if meta['Name'] != 'dragonhydra' or meta['Version'] != '0.4.0a1' or meta['Requires-Python'].replace(' ', '') != '>=3.14,<3.15':
            raise ValueError('Unexpected wheel package/runtime metadata')
        entry_points = configparser.ConfigParser()
        entry_points.read_string(archive.read(prefix+'entry_points.txt').decode())
        if entry_points['console_scripts']['dragon'] != 'dragonhydra.packaging_entry:main' or entry_points['console_scripts']['dragonhydra-server'] != 'dragonhydra.server:main':
            raise ValueError('Wheel entry points changed')
        rows = list(csv.reader(io.StringIO(archive.read(prefix+'RECORD').decode(), newline='')))
        if len(rows) != len(names) or {row[0] for row in rows} != set(names):
            raise ValueError('Incomplete wheel RECORD')
        for name, digest, size in rows:
            if name == prefix+'RECORD':
                if digest or size:
                    raise ValueError('Self-referential RECORD')
                continue
            raw = archive.read(name)
            wanted = 'sha256='+base64.urlsafe_b64encode(hashlib.sha256(raw).digest()).decode().rstrip('=')
            if digest != wanted or size != str(len(raw)):
                raise ValueError('Wheel RECORD integrity mismatch')
        return {'passed': True, 'application_files': len(expected), 'record_entries': len(rows),
                'requires_python': meta['Requires-Python'], 'requires_dist': meta.get_all('Requires-Dist'),
                'tag': 'py3-none-any', 'source_content_sha256': source_manifest['source_content_sha256'],
                'application_snapshot_sha256': source_manifest['application_snapshot_sha256'], 'source_sha': None}


def linux_proof(work, wheel, source_manifest, helpers):
    script = work/'linux-wheel-proof.py'
    payload = {'work': helpers['windows_to_wsl'](work), 'wheel': helpers['windows_to_wsl'](wheel),
               'identity': source_manifest['source_content_sha256'], 'origin': source_manifest['application_snapshot_sha256']}
    code = 'CONFIG='+repr(payload)+'\n'+'''import contextlib,importlib,io,json,os,pathlib,sys,zipfile
work=pathlib.Path(CONFIG['work']);site=work/'linux-proof'/'site-packages'
for key in list(os.environ):
 if key.startswith('DRAGONHYDRA_'): os.environ.pop(key)
site.mkdir(parents=True,exist_ok=False)
with zipfile.ZipFile(CONFIG['wheel']) as archive: archive.extractall(site)
sys.path.insert(0,str(site));os.chdir(site.parent)
import dragonhydra
from dragonhydra.build_meta import info
from dragonhydra.packaging_entry import main
identity=info()
assert identity['source_sha'] is None and identity['source_content_sha256']==CONFIG['identity']
assert identity['application_snapshot_sha256']==CONFIG['origin']
names=['connectors.core','connectors.football','connectors.research','connectors.multisport','connectors.service','connectors.store','local_ai','local_ai_service','local_ai_settings','mariadb_migration']
paths={name:importlib.import_module('dragonhydra.'+name).__file__ for name in names}
assert pathlib.Path(dragonhydra.__file__).is_relative_to(site)
assert all(pathlib.Path(value).is_relative_to(site) for value in paths.values())
sys.argv=['dragon','score','--format','json'];out=io.StringIO()
with contextlib.redirect_stdout(out): status=main()
score=json.loads(out.getvalue());assert status in (None,0) and score['cases']
from dragonhydra.local_ai_settings import Settings
settings=Settings(site.parent/'settings-state');settings.state.mkdir()
assert settings.public()=={'endpoint':'','configured':False,'endpoint_source':'none','credential_source':'none'}
from dragonhydra.local_ai import LocalAIError
try: settings.configure('http://127.0.0.1:19999','SYNTHETIC-only-settings-key-20261031')
except LocalAIError as error: assert error.code=='VAULT_PLATFORM'
else: raise AssertionError('Linux must not pretend DPAPI credential storage succeeded')
assert settings.public()['configured'] is False and not settings.path.exists()
assert not list(settings.state.rglob('*.dpapi')) and not list(settings.state.glob('*.tmp'))
print(json.dumps({'passed':True,'python':sys.version,'module':str(pathlib.Path(dragonhydra.__file__).relative_to(work)),
 'source_content_sha256':identity['source_content_sha256'],'application_snapshot_sha256':identity['application_snapshot_sha256'],
 'cli_score_cases':len(score['cases']),'imported_modules':names,'linux_credential_failure':'VAULT_PLATFORM',
 'checkout_imported':False,'server_started':False,'services_changed':False,'model_inference':False}))
'''
    script.write_text(code, encoding='utf-8')
    command = [r'C:\Windows\System32\wsl.exe', '--distribution', 'Ubuntu-26.04', '--cd', helpers['windows_to_wsl'](ROOT),
               '--exec', '/usr/bin/python3', '-I', '-S', '-B', helpers['windows_to_wsl'](script)]
    result = subprocess.run(command, capture_output=True, timeout=90)
    (work/'linux-proof.stdout.log').write_bytes(result.stdout)
    (work/'linux-proof.stderr.log').write_bytes(result.stderr)
    report = {'exit_code': result.returncode, 'passed': False, 'command': ['wsl.exe', '-d', 'Ubuntu-26.04', '--exec', 'python3', '-I', '-S', '-B', 'linux-wheel-proof.py']}
    if result.returncode == 0:
        report.update(json.loads(result.stdout))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--verify-wsl', action='store_true')
    args = parser.parse_args()
    work = args.work.resolve()
    if not work.is_relative_to(ROOT/'build/linux') or work == ROOT/'build/linux' or work.exists():
        parser.error('Select a fresh project-owned build/linux child; existing evidence is retained.')
    if os.name != 'nt' or sys.version_info[:2] != (3,14) or metadata.version('build') != '1.4.0' or metadata.version('uv_build') != '0.12.7':
        parser.error('Reuse the verified Windows Python3.14/build1.4.0/uv_build0.12.7 environment.')
    a4 = verify_snapshot(A4/'SOURCE-MANIFEST.json', A4/'source', A4_HASH, 'content_sha256')
    support = verify_snapshot(PREP_BUNDLE/'SOURCE-MANIFEST.json', PREP/'source', PREP_HASH, 'source_content_sha256')
    if len(a4['files']) != 62 or sum(name.startswith('src/dragonhydra/') for name in a4['files']) != 55:
        raise ValueError('Complete frozen A4 application scope was not established')
    helpers = runpy.run_path(str(support['source']/'scripts/build_linux_bundle.py'))
    work.mkdir(parents=True)
    report = {'schema_version':1, 'passed':False, 'started_at':datetime.now(timezone.utc).isoformat(),
              'installations':False, 'downloads':False, 'services_changed':False, 'source_sha':None,
              'application_snapshot_sha256':A4_HASH, 'linux_support_snapshot_sha256':PREP_HASH,
              'python':sys.version, 'build':metadata.version('build'), 'uv_build':metadata.version('uv_build')}
    try:
        source = work/'source'
        manifest = stage_source(a4, support, source, Path(__file__))
        write_json(work/'SOURCE-MANIFEST.json', manifest)
        matrix = json.loads((source/'packaging/release/version.json').read_text())
        identity = {'version':matrix['product_version'], 'python_version':matrix['python_version'],
                    'source_sha':None, 'source_content_sha256':manifest['source_content_sha256'],
                    'application_snapshot_sha256':A4_HASH, 'linux_support_snapshot_sha256':PREP_HASH,
                    'api_namespace':matrix['api_namespace'], 'schema_version':matrix['schema_version'],
                    'build_kind':'complete-frozen-a4-linux-preparation'}
        write_json(source/'src/dragonhydra/build_info.json', identity)
        artifacts = work/'wheel';artifacts.mkdir()
        env = helpers['build_environment']()
        env['SOURCE_DATE_EPOCH'] = '1793404800'
        backend = shutil.which('uv-build', path=env['PATH'])
        if not backend:
            raise ValueError('Existing pinned backend executable unavailable')
        command = [sys.executable, '-B', '-m', 'build', '--wheel', '--no-isolation', '--outdir', str(artifacts), str(source)]
        result = subprocess.run(command, capture_output=True, env=env, timeout=120)
        (work/'wheel-build.stdout.log').write_bytes(result.stdout)
        (work/'wheel-build.stderr.log').write_bytes(result.stderr)
        report['build_command'] = ['runtime/server-env/Scripts/python.exe','-B','-m','build','--wheel','--no-isolation','--outdir','wheel','source']
        report['build_exit_code'] = result.returncode
        if result.returncode:
            raise ValueError('Wheel backend failed; retain build logs')
        wheels = list(artifacts.glob('*.whl'))
        if len(wheels) != 1:
            raise ValueError('Expected exactly one backend-produced wheel')
        wheel = wheels[0]
        helpers['inspect_wheel'](wheel, manifest['source_content_sha256'])
        report['wheel_verification'] = verify_application_wheel(wheel, manifest)
        bundle = work/('dragonhydra-linux-frozen-a4-'+manifest['source_content_sha256'][:12]);bundle.mkdir()
        shutil.copyfile(wheel, bundle/wheel.name)
        shutil.copyfile(work/'SOURCE-MANIFEST.json', bundle/'SOURCE-MANIFEST.json')
        shutil.copyfile(a4['manifest_path'], bundle/'A4-ORIGIN-SOURCE-MANIFEST.json')
        shutil.copyfile(support['manifest_path'], bundle/'LINUX-SUPPORT-ORIGIN-SOURCE-MANIFEST.json')
        for name in TEMPLATES:
            (bundle/name).write_text((source/'packaging/linux'/name).read_text(encoding='utf-8'), encoding='utf-8', newline='\n')
        shutil.copyfile(source/'config/runtime/server-python314.lock.txt', bundle/'server-python314.lock.txt')
        files = [{'path':p.name,'bytes':p.stat().st_size,'sha256':sha(p)} for p in sorted(bundle.iterdir())]
        write_json(bundle/'MANIFEST.json', {'schema_version':1, 'kind':'complete-frozen-a4-linux-preparation-bundle',
                   'source_sha':None, 'source_content_sha256':manifest['source_content_sha256'],
                   'application_snapshot_sha256':A4_HASH, 'linux_support_snapshot_sha256':PREP_HASH,
                   'wheel':wheel.name, 'files':files})
        preflight = runpy.run_path(str(bundle/'preflight.py'))
        preflight['verify_bundle'](bundle)
        for snap in (a4,support):
            verify_snapshot(snap['manifest_path'],snap['source'],snap['expected_hash'],snap['key'])
        report.update(status='complete_frozen_a4_wheel_and_bundle_verified', passed=True,
                      source_content_sha256=manifest['source_content_sha256'], source_files=len(manifest['files']), application_files=55,
                      bundle=bundle.relative_to(ROOT).as_posix(), wheel={'filename':wheel.name,'bytes':wheel.stat().st_size,'sha256':sha(wheel)},
                      existing_linux_dependencies=17, dependency_status='Direct requirements unchanged; native dependency closure/run is the next package gate, not this core-only proof',
                      existing_r6_runtime_changed=False)
        if args.verify_wsl:
            report['linux_core'] = linux_proof(work,bundle/wheel.name,manifest,helpers)
            if not report['linux_core']['passed']:
                raise ValueError('Native new-wheel core proof failed; retain diagnostics')
        report['limits'] = ['No API process or systemd service started by this preparation',
                           'No full Linux desktop/Joomla/PHP/MariaDB package', 'No model inference or fresh provider HTTP claim',
                           'A4 snapshot excludes newer shared-source StatsBomb context work', 'No Git commit provenance or byte-reproducibility claim']
    except Exception as error:
        report.update(passed=False,status='failed',error={'type':type(error).__name__,'message':str(error)})
        raise
    finally:
        report['finished_at'] = datetime.now(timezone.utc).isoformat()
        write_json(work/'BUILD-REPORT.json',report)
        print(json.dumps({k:report.get(k) for k in ('passed','status','source_content_sha256','application_files','bundle','wheel','linux_core','error')},indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
