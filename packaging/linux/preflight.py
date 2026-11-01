"""Inspect a Linux bundle without changing the target; installation is explicit.

The application wheel is installed only with --apply, into a new selected prefix.
Existing compatible Python packages are reused; no dependency is downloaded.
No systemd service, account, firewall, network or existing project is changed.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib
from importlib import metadata
import json
import os
from pathlib import Path, PurePosixPath
import platform
import shutil
import subprocess
import sys

DEPENDENCIES = {'fastapi': '0.162.0', 'uvicorn': '0.42.0', 'openpyxl': '3.1.5', 'tzdata': '2026.2'}


def verify_bundle(bundle):
    manifest = json.loads((bundle / 'MANIFEST.json').read_text(encoding='utf-8'))
    files = manifest['files']
    if manifest.get('schema_version') != 1 or not isinstance(files, list) or not files:
        raise ValueError('INVALID_BUNDLE_MANIFEST')
    seen = set()
    for item in files:
        name = PurePosixPath(item['path'])
        if name.is_absolute() or '..' in name.parts or '\\' in item['path'] or item['path'] in seen:
            raise ValueError('UNSAFE_BUNDLE_PATH')
        seen.add(item['path'])
        path = bundle / name
        if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(bundle.resolve()):
            raise ValueError('BUNDLE_FILE_UNAVAILABLE')
        if path.stat().st_size != item['bytes'] or hashlib.sha256(path.read_bytes()).hexdigest() != item['sha256']:
            raise ValueError('BUNDLE_FILE_INTEGRITY')
    wheel = manifest.get('wheel')
    if wheel not in seen or not str(wheel).endswith('-py3-none-any.whl'):
        raise ValueError('INVALID_BUNDLE_WHEEL')
    return manifest


def inspect_runtime():
    report = {'platform': platform.system(), 'python': platform.python_version(), 'python_executable': sys.executable,
              'python_compatible': sys.version_info[:2] == (3, 14), 'dependencies': {}, 'ready': False}
    for name, expected in DEPENDENCIES.items():
        item = {'required_version': expected, 'available': False}
        try:
            actual = metadata.version(name)
            importlib.import_module(name)
            item.update(available=actual == expected, installed_version=actual)
        except (metadata.PackageNotFoundError, ImportError, OSError):
            pass
        report['dependencies'][name] = item
    report['ready'] = (report['platform'] == 'Linux' and report['python_compatible']
                       and all(item['available'] for item in report['dependencies'].values()))
    return report


def safe_target(value):
    path = Path(value)
    if not path.is_absolute() or any(char in str(path) for char in ('\n', '\r', '\x00', '%', '"', '\\')):
        raise ValueError('TARGET_REQUIRES_SAFE_ABSOLUTE_PATH')
    if path == Path(path.anchor) or path.is_symlink():
        raise ValueError('TARGET_ROOT_OR_SYMLINK_REJECTED')
    return path.resolve()


def inspect_installed_runtime(python):
    """Check the child's real imports, independently of the calling venv."""
    probe = subprocess.run(
        [str(python), '-I', '-c',
         "import json,runpy,sys; print(json.dumps(runpy.run_path(sys.argv[1])['inspect_runtime']()))",
         str(Path(__file__).resolve())],
        check=True, capture_output=True, text=True, timeout=30)
    runtime = json.loads(probe.stdout)
    if not runtime.get('ready'):
        raise ValueError('INSTALLED_RUNTIME_DEPENDENCIES_UNAVAILABLE')
    return runtime


def install(bundle, manifest, prefix, state, port):
    """Explicit owned-prefix install; caller already verified runtime/integrity."""
    if os.name != 'posix' or platform.system() != 'Linux':
        raise ValueError('LINUX_REQUIRED')
    prefix, state = safe_target(prefix), safe_target(state)
    if prefix.exists():
        raise ValueError('INSTALL_PREFIX_EXISTS')
    # No implicit replacement, no dependency retrieval, no activation.
    prefix.mkdir(parents=True, mode=0o700)
    subprocess.run([sys.executable, '-m', 'venv', '--system-site-packages', str(prefix / 'venv')], check=True)
    python = prefix / 'venv/bin/python'
    # A nested venv inherits base-system packages, not its parent's local sites.
    # Check before installing the application or creating usable state/launchers.
    runtime = inspect_installed_runtime(python)
    subprocess.run([str(python), '-m', 'pip', 'install', '--no-index', '--no-deps', str(bundle / manifest['wheel'])], check=True)
    subprocess.run([str(python), '-m', 'pip', 'check'], check=True)
    subprocess.run([str(python), '-I', '-c', 'import dragonhydra.server'], check=True, timeout=30)
    launcher = prefix / 'run-server.sh'
    shutil.copyfile(bundle / 'run-server.sh', launcher)
    launcher.chmod(0o700)
    state.mkdir(parents=True, exist_ok=True, mode=0o700)
    template = (bundle / 'dragonhydra.service.in').read_text(encoding='utf-8')
    unit = template.replace('@PREFIX@', str(prefix)).replace('@STATE@', str(state)).replace('@PORT@', str(port))
    unit_path = prefix / 'dragonhydra.service'
    unit_path.write_text(unit, encoding='utf-8')
    unit_path.chmod(0o600)
    return {'prefix': str(prefix), 'state': str(state), 'unit': str(unit_path),
            'service_activated': False, 'dependencies_downloaded': False,
            'runtime': runtime, 'server_import_verified': True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle', type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument('--prefix')
    parser.add_argument('--state')
    parser.add_argument('--port', type=int, default=18743, choices=range(1024, 65536), metavar='PORT')
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    report = {'schema_version': 1, 'applied': False, 'service_activated': False, 'downloads': False,
              'status': 'requires_configuration'}
    try:
        bundle = args.bundle.resolve()
        manifest = verify_bundle(bundle)
        runtime = inspect_runtime()
        report.update(bundle_integrity=True, source_content_sha256=manifest['source_content_sha256'], runtime=runtime)
        if runtime['ready']:
            report['status'] = 'ready_not_installed'
            if args.apply:
                if not args.prefix or not args.state:
                    raise ValueError('EXPLICIT_PREFIX_AND_STATE_REQUIRED')
                report['installation'] = install(bundle, manifest, args.prefix, args.state, args.port)
                report.update(applied=True, status='installed_not_activated')
    except (ValueError, KeyError, TypeError, OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
        report['status'] = 'preflight_failed'
        report['error'] = {'type': type(error).__name__, 'code': str(error) if isinstance(error, ValueError) else 'INSPECT_LOCAL_DIAGNOSTICS'}
    print(json.dumps(report, sort_keys=True))
    return 0 if report['status'] in ('ready_not_installed', 'installed_not_activated') else 2


if __name__ == '__main__':
    print('Historical installer entry point disabled in CORE NEXT; use scripts/core_next/linux-server.sh with an explicit isolated installation profile.', file=sys.stderr)
    raise SystemExit(64)
