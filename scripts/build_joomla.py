"""Build the reproducible Joomla extension package; never modifies a Joomla site."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path
import zipfile
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'server' / 'joomla'
STAMP = (2026, 10, 30, 0, 0, 0)


def archive(entries):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as out:
        for name, payload in sorted(entries):
            entry = zipfile.ZipInfo(name, STAMP)
            entry.compress_type = zipfile.ZIP_DEFLATED
            entry.external_attr = 0o100644 << 16
            out.writestr(entry, payload)
    return stream.getvalue()


def build(destination=None, *, source_root=None, source_sha=None):
    source = Path(source_root) / 'server' / 'joomla' if source_root else SOURCE
    component = source / 'com_dragonhydra'
    package_xml = ET.parse(source / 'pkg_dragonhydra.xml')
    component_xml = ET.parse(component / 'dragonhydra.xml')
    version = package_xml.getroot().findtext('version')
    if not version or component_xml.getroot().findtext('version') != version:
        raise ValueError('Joomla package and component versions must agree')
    if source_sha is not None and (len(source_sha) != 40 or any(c not in '0123456789abcdef' for c in source_sha)):
        raise ValueError('Release source must be a full lowercase Git commit SHA')
    allowed = {'.php', '.xml', '.ini', '.sql', '.css', '.js', '.json', '.svg'}
    entries = [(path.relative_to(component).as_posix(), path.read_bytes())
               for path in component.rglob('*') if path.is_file() and path.suffix in allowed]
    template = source / 'tpl_cassiopeia_dragonhydra'
    template_xml = ET.parse(template / 'templateDetails.xml')
    if template_xml.getroot().findtext('version') != version:
        raise ValueError('Joomla package, component and child-template versions must agree')
    template_entries = [(path.relative_to(template).as_posix(), path.read_bytes())
                        for path in template.rglob('*') if path.is_file() and path.suffix in allowed]
    if source_sha:
        info = {'schema_version': 1, 'version': version, 'source_sha': source_sha,
                'api_namespace': '/dragon/api/v1', 'kernel_schema_version': 1}
        entries.append(('admin/build-info.json', (json.dumps(info, sort_keys=True, indent=2)+'\n').encode()))
        files = component_xml.getroot().find('administration/files')
        ET.SubElement(files, 'filename').text = 'build-info.json'
        entries = [(name, ET.tostring(component_xml.getroot(), encoding='utf-8', xml_declaration=True) if name=='dragonhydra.xml' else data)
                   for name,data in entries]
    payload = archive([('pkg_dragonhydra.xml', (source / 'pkg_dragonhydra.xml').read_bytes()),
                       ('constituents/tpl_cassiopeia_dragonhydra.zip', archive(template_entries)),
                       ('constituents/com_dragonhydra.zip', archive(entries))])
    destination = Path(destination) if destination else ROOT / 'dist' / ('pkg_dragonhydra-'+version+'.zip')
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(payload)
    receipt = {'artifact': str(destination.resolve()), 'bytes': len(payload),
               'sha256': hashlib.sha256(payload).hexdigest(), 'version': version, 'source_sha': source_sha,
               'target': 'Joomla 6 sports workspace and administrator component with Cassiopeia child template; PHP >=8.3 with curl',
               'signing': 'unsigned development extension', 'built': True,
               'installed': False, 'installation_test': 'not run by package builder',
               'payload_files': len(entries), 'child_template_files': len(template_entries),
               'frontend_setup': 'Idempotent supported Joomla Menu/table migration; original articles/menu records retained; sample module assignments excluded only on managed Home items',
               'uninstall_policy': 'Retain all kernel databases, evidence, credentials and models'}
    destination.with_suffix('.manifest.json').write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')
    return receipt


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--source-root', type=Path)
    parser.add_argument('--source-sha')
    args = parser.parse_args()
    print(json.dumps(build(args.output, source_root=args.source_root, source_sha=args.source_sha), indent=2))
