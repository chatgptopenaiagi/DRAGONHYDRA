"""Build a project-local checkpoint recovery archive from a committed tree.

This packaging helper does not touch the live databases. Run after creating the
checkpoint tag and SQLite online backups, with the workspace as current directory.
"""
from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]
RELEASE = ROOT / 'release' / 'genesis2'
OUTPUT = RELEASE / 'DRAGONHYDRA-GENESIS2-RECOVERY.zip'


def main() -> None:
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    source = subprocess.check_output(['git', 'archive', '--format=zip', commit], cwd=ROOT)
    items: dict[str, bytes] = {}
    with zipfile.ZipFile(io.BytesIO(source)) as tree:
        for info in tree.infolist():
            if not info.is_dir():
                items['source/' + info.filename] = tree.read(info)
    datasets = ('football-data-2025-26-E0.csv', 'openfootball-2025-26-en1.json',
                'openfootball-2026-27-en1.json', 'tipsaudit-predictions-all.csv')
    for name in datasets:
        for filename in (name, name + '.receipt.json'):
            path = ROOT / 'data' / 'raw' / filename
            if path.is_symlink() or not path.is_file():
                raise RuntimeError(f'Missing regular source or receipt: {filename}')
            items['data/raw/' + filename] = path.read_bytes()
    for path in sorted((RELEASE / 'database').glob('*.sqlite3')):
        items['runtime/' + path.name] = path.read_bytes()
    for path in sorted((RELEASE / 'metadata').glob('*')):
        if path.is_file() and not path.is_symlink():
            items['metadata/' + path.name] = path.read_bytes()
    bundle = RELEASE / 'DRAGONHYDRA-source.bundle'
    items['DRAGONHYDRA-source.bundle'] = bundle.read_bytes()
    inventory = {
        'schema': 'dragonhydra-recovery-inventory/1',
        'git_commit': commit,
        'files': [{'path': name, 'bytes': len(content),
                   'sha256': hashlib.sha256(content).hexdigest()}
                  for name, content in sorted(items.items())],
        'excluded': ['Credentials and environment files', 'Caches, local virtual environments and build output',
                     'Separate DRAGON donor repositories and their unreviewed evidence (preserved locally)',
                     'The release manifest and outer archive checksum, which cannot include their own hashes'],
    }
    items['RECOVERY-INVENTORY.json'] = (json.dumps(inventory, indent=2) + '\n').encode()
    with zipfile.ZipFile(OUTPUT, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as out:
        for name, content in sorted(items.items()):
            out.writestr(name, content)
    with zipfile.ZipFile(OUTPUT) as check:
        error = check.testzip()
        if error:
            raise RuntimeError(f'Corrupt archive member: {error}')
        for entry in inventory['files']:
            content = check.read(entry['path'])
            if len(content) != entry['bytes'] or hashlib.sha256(content).hexdigest() != entry['sha256']:
                raise RuntimeError(f'Archive member hash mismatch: {entry["path"]}')
    print(f'{OUTPUT} | {OUTPUT.stat().st_size} bytes | {len(items)} entries | commit {commit}')


if __name__ == '__main__':
    main()
