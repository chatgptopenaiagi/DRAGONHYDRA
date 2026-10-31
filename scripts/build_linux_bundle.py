"""Build a scoped current-source wheel and Linux preparation bundle offline.

Uses the existing Python build/uv_build environment. No package installation,
Docker start, operating-system updates, VPS access or service activation occurs.
An optional scoped existing Ubuntu WSL probe executes only project-owned files.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
from importlib import metadata
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys
import tarfile
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ('preflight.py', 'install.sh', 'run-server.sh', 'dragonhydra.service.in', 'README.md')
FORBIDDEN = {'.sqlite3', '.db', '.dpapi', '.pem', '.key', '.keystore', '.jks', '.pfx', '.pyc'}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, indent=2) + '\n', encoding='utf-8')


def build_environment():
    env = {key: value for key, value in os.environ.items() if key not in ('PYTHONPATH', 'PYTHONHOME')
           and not key.startswith('DRAGONHYDRA_')}
    # Direct invocation of a Windows venv interpreter does not activate its
    # Scripts directory. The uv_build shim resolves uv-build through PATH.
    env['PATH'] = str(Path(sys.executable).parent) + os.pathsep + env.get('PATH', '')
    return env


def collect_inputs(root):
    package = root / 'src/dragonhydra'
    selected = []
    for path in package.rglob('*'):
        if not path.is_file() or '__pycache__' in path.parts or path.suffix == '.pyc' or path.name == 'build_info.json':
            continue
        if path.suffix in FORBIDDEN or path.name == '.env' or path.is_symlink():
            raise ValueError('UNSAFE_SOURCE_INPUT')
        if path.suffix != '.py' and not path.is_relative_to(package / 'resources'):
            raise ValueError('UNEXPECTED_SOURCE_INPUT')
        selected.append(path)
    selected += [root / name for name in ('pyproject.toml', 'README.md', 'packaging/release/version.json',
                                          'config/runtime/server-python314.lock.txt', 'scripts/build_linux_bundle.py')]
    selected += [root / 'packaging/linux' / name for name in TEMPLATES]
    files = []
    for path in sorted(selected):
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 8 * 1024 * 1024:
            raise ValueError('INVALID_SOURCE_INPUT')
        files.append({'path': path.relative_to(root).as_posix(), 'bytes': path.stat().st_size, 'sha256': digest(path)})
    if not files:
        raise ValueError('EMPTY_SOURCE_SCOPE')
    return files


def snapshot(root, work):
    files = collect_inputs(root)
    source = work / 'source'
    for item in files:
        target = source / item['path']
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root / item['path'], target)
        if digest(target) != item['sha256']:
            raise ValueError('SOURCE_CHANGED_DURING_SNAPSHOT')
    content_hash = hashlib.sha256(json.dumps(files, sort_keys=True, ensure_ascii=False,
                                            separators=(',', ':')).encode()).hexdigest()
    manifest = {'schema_version': 1, 'kind': 'scoped_working_tree_snapshot', 'source_sha': None,
                'source_content_sha256': content_hash, 'files': files}
    write_json(work / 'SOURCE-MANIFEST.json', manifest)
    return source, manifest


def inspect_wheel(path, source_hash):
    with ZipFile(path) as archive:
        names = archive.namelist()
        for item in archive.infolist():
            name = PurePosixPath(item.filename)
            if (name.is_absolute() or '..' in name.parts or '\\' in item.filename
                    or name.suffix in FORBIDDEN or item.file_size > 8 * 1024 * 1024
                    or (item.external_attr >> 16) & 0o170000 == 0o120000):
                raise ValueError('UNSAFE_WHEEL_MEMBER')
        if len(names) != len(set(names)) or sum(item.file_size for item in archive.infolist()) > 64 * 1024 * 1024:
            raise ValueError('INVALID_WHEEL_SIZE_OR_DUPLICATES')
        required = ('dragonhydra/api.py', 'dragonhydra/connectors/service.py', 'dragonhydra/local_ai.py',
                    'dragonhydra/resources/web/app.js', 'dragonhydra/resources/data/raw/openfootball-2025-26-en1.json')
        if any(name not in names for name in required) or not path.name.endswith('-py3-none-any.whl'):
            raise ValueError('WHEEL_CAPABILITY_OR_TAG_MISSING')
        info = json.loads(archive.read('dragonhydra/build_info.json'))
        if info['source_sha'] is not None or info['source_content_sha256'] != source_hash:
            raise ValueError('WHEEL_SOURCE_IDENTITY_MISMATCH')
        return {'members': len(names), 'build': info, 'tag': 'py3-none-any'}


def windows_to_wsl(path):
    path = path.resolve()
    if path.drive.lower() != 'c:':
        raise ValueError('WSL_PROBE_REQUIRES_OWNED_C_DRIVE_PROJECT')
    return '/mnt/c/' + '/'.join(path.parts[1:])


def verify_wsl(work, bundle, wheel, source_hash):
    script = work / 'linux-smoke.py'
    # This script runs from the existing Ubuntu interpreter. Every output stays
    # in the selected /mnt/c project work directory; no pip or apt command runs.
    code = '''import contextlib,io,json,os,pathlib,subprocess,sys,zipfile
work=pathlib.Path(WORK)
bundle=pathlib.Path(BUNDLE)
wheel=bundle/WHEEL
site=work/'linux-smoke'/'site-packages'
site.mkdir(parents=True,exist_ok=False)
with zipfile.ZipFile(wheel) as archive: archive.extractall(site)
sys.path.insert(0,str(site))
os.chdir(site.parent)
import dragonhydra
from dragonhydra.build_meta import info
from dragonhydra.packaging_entry import main
identity=info()
assert identity['source_sha'] is None and identity['source_content_sha256']==SOURCE_HASH
assert pathlib.Path(dragonhydra.__file__).is_relative_to(site)
sys.argv=['dragon','score','--format','json']
captured=io.StringIO()
with contextlib.redirect_stdout(captured): status=main()
score=json.loads(captured.getvalue())
assert status in (None,0) and score['cases']
preflight=subprocess.run([sys.executable,'-I','-B',str(bundle/'preflight.py'),'--bundle',str(bundle)],capture_output=True,text=True,timeout=20)
target=json.loads(preflight.stdout)
print(json.dumps({'passed':True,'python':sys.version,'python_executable':sys.executable,'module':dragonhydra.__file__,'source_content_sha256':SOURCE_HASH,'cli_score_cases':len(score['cases']),'preflight_exit_code':preflight.returncode,'preflight':target,'server_runtime_verified':False,'service_activated':False}))
'''
    code = ('WORK=' + repr(windows_to_wsl(work)) + '\nBUNDLE=' + repr(windows_to_wsl(bundle)) +
            '\nWHEEL=' + repr(wheel.name) + '\nSOURCE_HASH=' + repr(source_hash) + '\n' + code)
    script.write_text(code, encoding='utf-8')
    command = [r'C:\Windows\System32\wsl.exe', '--distribution', 'Ubuntu-26.04', '--cd', windows_to_wsl(ROOT),
               '--exec', '/usr/bin/python3', '-I', '-B', windows_to_wsl(script)]
    result = subprocess.run(command, capture_output=True, timeout=50)
    (work / 'linux-smoke.stdout.log').write_bytes(result.stdout)
    (work / 'linux-smoke.stderr.log').write_bytes(result.stderr)
    report = {'command': command, 'exit_code': result.returncode, 'passed': False}
    if result.returncode == 0:
        report.update(json.loads(result.stdout.decode('utf-8')))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work', required=True, type=Path)
    parser.add_argument('--verify-wsl', action='store_true')
    args = parser.parse_args()
    work = args.work.resolve()
    if not work.is_relative_to(ROOT / 'build/linux') or work == ROOT / 'build/linux' or work.exists():
        parser.error('Choose a new project-owned child directory under build/linux.')
    if sys.version_info[:2] != (3, 14) or metadata.version('uv_build') != '0.12.7':
        parser.error('Reuse the existing Python 3.14 environment with uv_build 0.12.7.')
    work.mkdir(parents=True)
    report = {'schema_version': 1, 'status': 'running', 'passed': False,
              'started_at': datetime.now(timezone.utc).isoformat(), 'python': sys.executable,
              'build_version': metadata.version('build'), 'uv_build_version': metadata.version('uv_build'),
              'installations': False, 'downloads': False, 'service_activated': False,
              'limitations': ['No authorized VPS target is configured.', 'Android production publisher identity is not configured.']}
    try:
        source, source_manifest = snapshot(ROOT, work)
        source_hash = source_manifest['source_content_sha256']
        report['source_content_sha256'] = source_hash
        matrix = json.loads((source / 'packaging/release/version.json').read_text())
        build_info = {'version': matrix['product_version'], 'python_version': matrix['python_version'],
                      'api_namespace': matrix['api_namespace'], 'schema_version': matrix['schema_version'],
                      'source_sha': None, 'source_content_sha256': source_hash, 'build_kind': 'linux-preparation-snapshot'}
        write_json(source / 'src/dragonhydra/build_info.json', build_info)
        artifacts = work / 'wheel'
        artifacts.mkdir()
        env = build_environment()
        backend = shutil.which('uv-build', path=env['PATH'])
        if not backend:
            raise ValueError('EXISTING_UV_BUILD_EXECUTABLE_UNAVAILABLE')
        report['backend_executable'] = backend
        command = [sys.executable, '-B', '-m', 'build', '--wheel', '--no-isolation', '--outdir', str(artifacts), str(source)]
        built = subprocess.run(command, capture_output=True, env=env, timeout=90)
        report['build_command'], report['build_exit_code'] = command, built.returncode
        (work / 'wheel-build.stdout.log').write_bytes(built.stdout)
        (work / 'wheel-build.stderr.log').write_bytes(built.stderr)
        if built.returncode:
            raise ValueError('WHEEL_BUILD_FAILED')
        wheels = list(artifacts.glob('*.whl'))
        if len(wheels) != 1:
            raise ValueError('EXPECTED_ONE_WHEEL')
        wheel = wheels[0]
        report['wheel'] = inspect_wheel(wheel, source_hash)
        bundle = work / ('dragonhydra-linux-dev-' + source_hash[:12])
        bundle.mkdir()
        shutil.copyfile(wheel, bundle / wheel.name)
        shutil.copyfile(work / 'SOURCE-MANIFEST.json', bundle / 'SOURCE-MANIFEST.json')
        for name in TEMPLATES:
            # Shell/systemd files have native LF independently of checkout EOL.
            text = (source / 'packaging/linux' / name).read_text(encoding='utf-8')
            (bundle / name).write_text(text, encoding='utf-8', newline='\n')
        shutil.copyfile(source / 'config/runtime/server-python314.lock.txt', bundle / 'server-python314.lock.txt')
        files = [{'path': path.name, 'bytes': path.stat().st_size, 'sha256': digest(path)} for path in sorted(bundle.iterdir())]
        manifest = {'schema_version': 1, 'kind': 'linux-preparation-development-bundle', 'source_sha': None,
                    'source_content_sha256': source_hash, 'wheel': wheel.name, 'files': files}
        write_json(bundle / 'MANIFEST.json', manifest)
        # Exercise the real integrity checker before archiving, without installing.
        import importlib.util
        spec = importlib.util.spec_from_file_location('linux_preflight_for_build', bundle / 'preflight.py')
        preflight = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(preflight)
        preflight.verify_bundle(bundle)
        archive = work / (bundle.name + '.tar.gz')
        with tarfile.open(archive, 'w:gz', format=tarfile.PAX_FORMAT) as output:
            for path in sorted(bundle.iterdir()):
                entry = output.gettarinfo(str(path), arcname=bundle.name + '/' + path.name)
                entry.uid = entry.gid = 0
                entry.uname = entry.gname = ''
                entry.mode = 0o755 if path.suffix == '.sh' else 0o644
                with path.open('rb') as content:
                    output.addfile(entry, content)
        report['artifact'] = {'path': str(archive.relative_to(ROOT)), 'bytes': archive.stat().st_size, 'sha256': digest(archive)}
        report.update(passed=True, status='prepared_linux_runtime_unverified')
        if args.verify_wsl:
            linux = verify_wsl(work, bundle, bundle / wheel.name, source_hash)
            report['linux'] = linux
            if linux['passed']:
                report['status'] = ('linux_core_verified_server_requires_dependencies'
                                    if not linux['preflight']['runtime']['ready'] else 'linux_core_verified_server_not_started')
            else:
                report['limitations'].append('The actual Linux smoke did not pass; inspect preserved diagnostics.')
        print(json.dumps({'passed': report['passed'], 'status': report['status'], 'artifact': report['artifact'],
                          'linux_smoke_passed': report.get('linux', {}).get('passed'),
                          'server_runtime_verified': False, 'report': str((work / 'build-report.json').relative_to(ROOT))}))
    except Exception as error:
        report.update(passed=False, status='build_failed', error={'type': type(error).__name__, 'code': str(error)})
        raise
    finally:
        report['finished_at'] = datetime.now(timezone.utc).isoformat()
        write_json(work / 'build-report.json', report)
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
