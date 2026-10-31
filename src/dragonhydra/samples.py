"""Copy deliberate bundled examples into a selected writable workspace."""
import argparse
import json
from pathlib import Path
import shutil


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, required=True)
    args = parser.parse_args()
    destination = args.directory.resolve()
    resources = Path(__file__).parent / 'resources'
    copied = []
    for folder in ('examples', 'data/raw'):
        for path in sorted((resources / folder).glob('*')):
            if not path.is_file():
                continue
            target = destination / folder / path.name
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists() and target.read_bytes() != path.read_bytes():
                raise SystemExit('Existing sample differs; select another empty destination.')
            shutil.copyfile(path, target)
            copied.append(str(target))
    print(json.dumps({'directory': str(destination), 'copied': copied, 'origin': 'bundled documented samples'}, indent=2))
