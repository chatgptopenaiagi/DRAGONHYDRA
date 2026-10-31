"""Assemble the frozen application and Linux wheels into a real Debian package.

The input Linux-preparation bundle is read-only. New build state and downloads
stay inside this project. Archive modes are explicit: Windows/DrvFS modes are
never copied into the installed product. No OS package or service is changed.
"""
from __future__ import annotations

import argparse
import base64
import csv
from datetime import datetime, timezone
from email.parser import BytesParser
import hashlib
from importlib import metadata
import io
import json
import os
from pathlib import Path, PurePosixPath
import platform
import runpy
import shutil
import stat
import subprocess
import sys
import tarfile
import zipfile

ROOT = Path(__file__).resolve().parents[2]
REQUIRED = {'fastapi': '0.162.0', 'uvicorn': '0.42.0', 'openpyxl': '3.1.5', 'tzdata': '2026.2'}
EPOCH = 1793404800  # 2026-10-31 UTC: explicit development build epoch.


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False)+'\n', encoding='utf-8')


def annotate_transform(site, source, transform):
    """Keep the immutable base and effective source identity separately."""
    effective = json.loads(json.dumps(source))
    entries = [item for item in effective['files'] if item['path'] == 'src/'+transform['target']]
    if len(entries) != 1 or entries[0]['sha256'] != transform['base_sha256']:
        raise ValueError('Frozen source manifest does not describe the transformed module')
    entries[0].update(sha256=transform['transformed_sha256'], bytes=(site/transform['target']).stat().st_size)
    digest = hashlib.sha256(json.dumps(effective['files'], sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()
    effective.update(base_source_content_sha256=source['source_content_sha256'], source_content_sha256=digest,
                     source_transforms=[transform])
    build_info = site/'dragonhydra/build_info.json'
    original = build_info.read_bytes()
    identity = json.loads(original)
    identity.update(base_source_content_sha256=source['source_content_sha256'], source_content_sha256=digest,
                    source_transforms=[transform], build_kind='frozen-linux-base-with-reviewed-packaging-patch')
    body = (json.dumps(identity, indent=2, sort_keys=True)+'\n').encode()
    record = site/'dragonhydra-0.4.0a1.dist-info/RECORD'
    rows = list(csv.reader(io.StringIO(record.read_text(), newline='')))
    matches = [row for row in rows if row and row[0] == 'dragonhydra/build_info.json']
    hashed = lambda payload: 'sha256='+base64.urlsafe_b64encode(hashlib.sha256(payload).digest()).decode().rstrip('=')
    if len(matches) != 1 or matches[0][1:] != [hashed(original), str(len(original))]:
        raise ValueError('Original build-info RECORD is inconsistent')
    matches[0][1:] = [hashed(body), str(len(body))]
    output = io.StringIO(newline='')
    csv.writer(output, lineterminator='\n').writerows(rows)
    build_info.write_bytes(body)
    record.write_text(output.getvalue(), encoding='utf-8', newline='')
    return effective


def checked_child(value, boundary, *, fresh=False):
    value, boundary = Path(value).resolve(), Path(boundary).resolve()
    if not value.is_relative_to(boundary) or value == boundary:
        raise ValueError('Output must be an owned child of '+str(boundary))
    if fresh and value.exists():
        raise ValueError('Output already exists; retain evidence and select another directory: '+str(value))
    return value


def debian_version(source_hash, revision):
    if (not isinstance(source_hash, str) or len(source_hash) != 64
            or any(c not in '0123456789abcdef' for c in source_hash)
            or type(revision) is not int or not 1 <= revision <= 999):
        raise ValueError('Invalid source identity or packaging sequence')
    # Preserve historical candidate names. New builds put the monotonic
    # sequence BEFORE the hash; a lower-sorting new hash must not downgrade an
    # installed package merely because its trailing Debian revision increased.
    if revision <= 6:
        if source_hash != '9f3d6e5ab1082a81c19308cdce3bea2e1efd3d31729227a027248644d56a86c4':
            raise ValueError('New source snapshots require packaging sequence7 or later')
        return '0.4.0~alpha.1+dev20261031.'+source_hash[:12]+'-'+str(revision)
    return '0.4.0~alpha.1+dev20261031.r'+str(revision)+'.'+source_hash[:12]+'-1'


def verify_bundle(bundle):
    manifest = json.loads((bundle/'MANIFEST.json').read_text())
    names = set()
    for item in manifest['files']:
        path = PurePosixPath(item['path'])
        if path.is_absolute() or '..' in path.parts or '\\' in str(path) or str(path) in names:
            raise ValueError('Unsafe frozen bundle path')
        names.add(str(path))
        target = bundle/path
        if target.is_symlink() or not target.resolve().is_relative_to(bundle.resolve()) or not target.is_file() or target.stat().st_size != item['bytes'] or sha(target) != item['sha256']:
            raise ValueError('Frozen input hash mismatch: '+str(path))
    source = json.loads((bundle/'SOURCE-MANIFEST.json').read_text())
    source_hash = hashlib.sha256(json.dumps(source['files'], sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()
    if source_hash != source['source_content_sha256'] or source_hash != manifest['source_content_sha256']:
        raise ValueError('Frozen source identity mismatch')
    wheel_name = PurePosixPath(manifest['wheel'])
    if wheel_name.is_absolute() or '..' in wheel_name.parts or '\\' in str(wheel_name) or str(wheel_name) not in names:
        raise ValueError('Application wheel is not a verified bundle member')
    wheel = bundle/wheel_name
    if not wheel.resolve().is_relative_to(bundle.resolve()) or not wheel.name.endswith('-py3-none-any.whl'):
        raise ValueError('The selected application wheel is not the vetted pure-Python artifact')
    with zipfile.ZipFile(wheel) as archive:
        identity = json.loads(archive.read('dragonhydra/build_info.json'))
        if identity.get('source_sha') is not None or identity.get('source_content_sha256') != source_hash or identity.get('version') != '0.4.0-alpha.1' or identity.get('api_namespace') != '/dragon/api/v1' or identity.get('schema_version') != 1:
            raise ValueError('Embedded application wheel identity mismatch')
    return manifest, source, wheel


def unpack_wheels(wheels, target):
    """Retain upstream dist-info/licenses, reject executable scripts and links."""
    inventory = []
    for wheel in sorted(wheels):
        with zipfile.ZipFile(wheel) as archive:
            metas = [n for n in archive.namelist() if n.endswith('.dist-info/METADATA')]
            if len(metas) != 1:
                raise ValueError('Invalid wheel metadata: '+wheel.name)
            info = BytesParser().parsebytes(archive.read(metas[0]))
            inventory.append({'filename': wheel.name, 'name': info['Name'], 'version': info['Version'],
                              'bytes': wheel.stat().st_size, 'sha256': sha(wheel),
                              'upstream': 'https://pypi.org/project/'+info['Name']+'/'+info['Version']+'/' if info['Name'] != 'dragonhydra' else 'frozen-project-wheel'})
            for entry in archive.infolist():
                name = PurePosixPath(entry.filename)
                if name.is_absolute() or '..' in name.parts or '\\' in entry.filename or stat.S_ISLNK(entry.external_attr >> 16):
                    raise ValueError('Unsafe wheel member: '+entry.filename)
                if entry.is_dir():
                    continue
                if any(part.endswith('.data') for part in name.parts) or entry.filename.startswith('bin/'):
                    raise ValueError('Unsupported wheel script/data relocation: '+entry.filename)
                if entry.file_size > 16*1024*1024:
                    raise ValueError('Unexpectedly large wheel member')
                payload = archive.read(entry)
                path = target/name
                path.parent.mkdir(parents=True, exist_ok=True)
                if path.exists() and path.read_bytes() != payload:
                    raise ValueError('Conflicting wheel member: '+entry.filename)
                path.write_bytes(payload)
    return inventory


def verify_dependencies(site):
    # Use the already installed pip's parser for build-time checks; pip itself is
    # neither copied into the product nor needed by the installed launcher.
    from pip._vendor.packaging.requirements import Requirement
    from pip._vendor.packaging.markers import default_environment
    from pip._vendor.packaging.utils import canonicalize_name
    distributions = {canonicalize_name(d.metadata['Name']): d for d in metadata.distributions(path=[str(site)])}
    for name, expected in REQUIRED.items():
        if name not in distributions or distributions[name].version != expected:
            raise ValueError('Pinned runtime dependency missing: '+name)
    for name, distribution in distributions.items():
        for raw in distribution.requires or []:
            requirement = Requirement(raw)
            extras = ('', 'server') if name == 'dragonhydra' else ('',)
            if requirement.marker and not any(requirement.marker.evaluate({**default_environment(), 'extra': extra}) for extra in extras):
                continue
            dependency = distributions.get(canonicalize_name(requirement.name))
            if dependency is None or dependency.version not in requirement.specifier:
                raise ValueError('Unsatisfied vendored dependency: '+name+' -> '+str(requirement))
    return {name: item.version for name, item in sorted(distributions.items())}


def tar_bytes(files, *, control=False):
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode='w:xz', format=tarfile.GNU_FORMAT, preset=6) as archive:
        directories = {'.'}
        for name in files:
            parent = PurePosixPath(name).parent
            while str(parent) != '.':
                directories.add(str(parent))
                parent = parent.parent
        for name in sorted(directories, key=lambda n: (n.count('/'), n)):
            item = tarfile.TarInfo('./' if name == '.' else './'+name)
            item.type, item.mode, item.uid, item.gid, item.mtime = tarfile.DIRTYPE, 0o755, 0, 0, EPOCH
            item.uname = item.gname = 'root'
            archive.addfile(item)
        for name, (body, mode) in sorted(files.items()):
            item = tarfile.TarInfo('./'+name)
            item.size, item.mode, item.uid, item.gid, item.mtime = len(body), mode, 0, 0, EPOCH
            item.uname = item.gname = 'root'
            archive.addfile(item, io.BytesIO(body))
    return buffer.getvalue()


def ar_member(name, body):
    fields = ((name+'/').ljust(16), str(EPOCH).ljust(12), '0'.ljust(6), '0'.ljust(6),
              '100644'.ljust(8), str(len(body)).ljust(10), '`\n')
    return ''.join(fields).encode('ascii')+body+(b'\n' if len(body)%2 else b'')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle', type=Path, required=True)
    parser.add_argument('--wheelhouse', type=Path, default=ROOT/'runtime/linux-native/wheels')
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=ROOT/'dist/linux/native-kernel-20261031')
    parser.add_argument('--revision', type=int, required=True)
    args = parser.parse_args()
    if platform.system() != 'Linux' or platform.machine() != 'x86_64' or sys.version_info[:2] != (3, 14):
        raise SystemExit('Build with the verified Ubuntu26.04 x86_64 Python3.14 environment')
    work = checked_child(args.work, ROOT/'build/linux/native-kernel-20261031', fresh=True)
    output = checked_child(args.output, ROOT/'dist/linux', fresh=False)
    wheelhouse = checked_child(args.wheelhouse, ROOT/'runtime/linux-native')
    bundle = Path(args.bundle).resolve()
    if not bundle.is_relative_to(ROOT/'build/linux'):
        raise ValueError('Frozen bundle must remain inside this project')
    manifest, source, app_wheel = verify_bundle(bundle)
    source_hash = manifest['source_content_sha256']
    if not 1 <= args.revision <= 999:
        raise ValueError('Use a bounded positive Debian packaging revision')
    version = debian_version(source_hash, args.revision)
    output.mkdir(parents=True, exist_ok=True)
    artifact = output/('dragonhydra-api_'+version+'_amd64.deb')
    if artifact.exists():
        raise ValueError('Artifact already exists; no replacement is authorized')
    work.mkdir(parents=True)
    report = {'schema_version': 1, 'started_at': datetime.now(timezone.utc).isoformat(),
              'status': 'building', 'source_sha': None, 'source_content_sha256': source_hash,
              'version': version, 'python': sys.version, 'target': 'Ubuntu26.04.1 Linux x86_64 / CPython3.14',
              'scope': 'API server component with vendored Linux dependencies; not a full desktop/Joomla/MariaDB workstation',
              'host_services_changed': False, 'system_install_tested': False, 'service_activation_tested': False}
    try:
        site = work/'payload/opt/dragonhydra/api/site-packages'
        site.mkdir(parents=True)
        wheels = list(wheelhouse.glob('*.whl'))
        if not wheels:
            raise ValueError('Download the pinned Linux runtime wheels first')
        inputs = unpack_wheels([*wheels, app_wheel], site)
        versions = verify_dependencies(site)
        here = Path(__file__).parent
        transform = runpy.run_path(str(here/'server_patch.py'))['apply_server_patch'](site)
        effective_source = annotate_transform(site, source, transform)
        report.update(base_source_content_sha256=source_hash,
                      source_content_sha256=effective_source['source_content_sha256'], source_transforms=[transform])
        for key in ('application_snapshot_sha256', 'linux_support_snapshot_sha256'):
            if key in source:
                report[key] = source[key]
        # Imports happen from the assembled target, with source/PYTHONPATH absent.
        probe = "import sys;sys.path.insert(0,sys.argv[1]);import fastapi,uvicorn,openpyxl,tzdata,pydantic_core,dragonhydra;print(dragonhydra.__file__)"
        imports = subprocess.run([sys.executable, '-I', '-S', '-B', '-c', probe, str(site)], capture_output=True, text=True, check=True)
        report['installed_module_probe'] = imports.stdout.strip()
        package_files = {}
        for path in sorted(site.rglob('*')):
            if path.is_file():
                if '__pycache__' in path.parts or path.suffix == '.pyc' or path.name in ('direct_url.json',):
                    raise ValueError('Unexpected generated/private runtime input')
                name = path.relative_to(work/'payload').as_posix()
                package_files[name] = (path.read_bytes(), 0o644)
        for source_file, installed_path, mode in (
            ('bootstrap.py', 'opt/dragonhydra/api/bootstrap.py', 0o644),
            ('managed_endpoint.py', 'opt/dragonhydra/api/managed_endpoint.py', 0o644),
            ('dragonhydra-server', 'opt/dragonhydra/api/bin/dragonhydra-server', 0o755),
            ('dragonhydra-api.service', 'usr/lib/systemd/system/dragonhydra-api.service', 0o644),
            ('api.env', 'etc/dragonhydra/api.env', 0o600),
            ('README.md', 'usr/share/doc/dragonhydra-api/README.md', 0o644)):
            package_files[installed_path] = ((here/source_file).read_bytes(), mode)
        package_files['usr/share/doc/dragonhydra-api/SOURCE-MANIFEST.json'] = ((bundle/'SOURCE-MANIFEST.json').read_bytes(), 0o644)
        package_files['usr/share/doc/dragonhydra-api/EFFECTIVE-SOURCE-MANIFEST.json'] = ((json.dumps(effective_source, indent=2)+'\n').encode(), 0o644)
        verified_members = {item['path'] for item in manifest['files']}
        for name in ('A4-ORIGIN-SOURCE-MANIFEST.json', 'LINUX-SUPPORT-ORIGIN-SOURCE-MANIFEST.json'):
            if name in verified_members:
                package_files['usr/share/doc/dragonhydra-api/'+name] = ((bundle/name).read_bytes(), 0o644)
        identity = {'schema_version': 1, 'component': 'dragonhydra-api', 'debian_version': version,
                    'application_version': '0.4.0-alpha.1', 'python_version': '0.4.0a1',
                    'source_sha': None, 'source_content_sha256': effective_source['source_content_sha256'],
                    'base_source_content_sha256': source_hash, 'source_transforms': [transform], 'architecture': 'amd64',
                    'python_compatibility': '>=3.14,<3.15', 'api_namespace': '/dragon/api/v1', 'schema_version_api': 1,
                    'builder_sha256': sha(__file__), 'dependencies': versions, 'inputs': inputs}
        for key in ('application_snapshot_sha256', 'linux_support_snapshot_sha256'):
            if key in source:
                identity[key] = source[key]
        identity['packaging_inputs'] = [{'path': name, 'bytes': (here/name).stat().st_size, 'sha256': sha(here/name)}
            for name in ('bootstrap.py', 'managed_endpoint.py', 'server_patch.py', 'dragonhydra-server', 'dragonhydra-api.service', 'api.env', 'preinst.in', 'postinst', 'prerm', 'postrm', 'README.md')]
        package_files['opt/dragonhydra/api/BUILD-IDENTITY.json'] = (json.dumps(identity, indent=2).encode()+b'\n', 0o644)
        control = (f'Package: dragonhydra-api\nVersion: {version}\nArchitecture: amd64\n'
                   'Maintainer: DRAGONHYDRA Developers <developers@dragonhydra.invalid>\nSection: net\nPriority: optional\n'
                   'Depends: python3 (>= 3.14), python3 (<< 3.15), libc6 (>= 2.17), libgcc-s1, ca-certificates, init-system-helpers\n'
                   f'Installed-Size: {(sum(len(v[0]) for v in package_files.values())+1023)//1024}\n'
                   'Homepage: https://github.com/chatgptopenaiagi/DRAGONHYDRA\n'
                   'Description: DRAGONHYDRA sports-intelligence API server component\n'
                   ' Includes the frozen application and pinned Linux Python libraries.\n'
                   ' Requires the distribution CPython3.14 runtime. Contains no desktop,\n'
                   ' Apache/PHP/Joomla/MariaDB stack or model weights.\n')
        md5sums = ''.join(hashlib.md5(body).hexdigest()+'  '+name+'\n' for name,(body,_) in sorted(package_files.items()))
        controls = {'control': (control.encode(), 0o644), 'md5sums': (md5sums.encode(), 0o644),
                    'conffiles': (b'/etc/dragonhydra/api.env\n', 0o644),
                    'postinst': ((here/'postinst').read_bytes(), 0o755),
                    'prerm': ((here/'prerm').read_bytes(), 0o755),
                    'postrm': ((here/'postrm').read_bytes(), 0o755)}
        preinst = (here/'preinst.in').read_text()
        if preinst.count('@@MANAGED_ENDPOINT@@') != 1:
            raise ValueError('The upgrade script must embed the reviewed endpoint helper exactly once')
        controls['preinst'] = (preinst.replace('@@MANAGED_ENDPOINT@@', (here/'managed_endpoint.py').read_text()).encode(), 0o755)
        package = b'!<arch>\n'+ar_member('debian-binary', b'2.0\n')+ar_member('control.tar.xz', tar_bytes(controls, control=True))+ar_member('data.tar.xz', tar_bytes(package_files))
        artifact.write_bytes(package)
        # The native Debian reader, not our own encoder, must accept the result.
        for command in (['dpkg-deb', '--info', str(artifact)], ['dpkg-deb', '--contents', str(artifact)]):
            result = subprocess.run(command, check=True, capture_output=True, text=True)
            (work/('dpkg-info.log' if command[1]=='--info' else 'dpkg-contents.log')).write_text(result.stdout)
        write_json(work/'INPUT-MANIFEST.json', {'schema_version': 1, 'files': inputs})
        write_json(work/'PAYLOAD-MANIFEST.json', {'schema_version': 1, 'files': [
            {'path': name, 'bytes': len(body), 'sha256': hashlib.sha256(body).hexdigest(), 'mode': oct(mode), 'uid': 0, 'gid': 0}
            for name,(body,mode) in sorted(package_files.items())]})
        report.update(status='built_native_format_verified', built=True, package_reader_verified=True,
                      artifact={'filename': artifact.name, 'bytes': artifact.stat().st_size, 'sha256': sha(artifact)},
                      payload_files=len(package_files), dependencies=versions, signing='unsigned development package')
    except Exception as exc:
        report.update(status='failed', error=type(exc).__name__+': '+str(exc))
        raise
    finally:
        report['finished_at'] = datetime.now(timezone.utc).isoformat()
        write_json(work/'BUILD-REPORT.json', report)
        print(json.dumps(report, indent=2), flush=True)


if __name__=='__main__':
    main()
