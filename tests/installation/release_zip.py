"""Package the complete onedir payload; never rename one EXE into an archive."""
import argparse
from pathlib import Path
import zipfile

parser=argparse.ArgumentParser()
parser.add_argument('--source',required=True,type=Path)
parser.add_argument('--output',required=True,type=Path)
args=parser.parse_args()
source=args.source.resolve()
if not (source/'DRAGONHYDRA-Server.exe').is_file():
    raise SystemExit('A complete server onedir source is required')
if args.output.exists():
    raise SystemExit('Refusing to replace an existing release archive')
args.output.parent.mkdir(parents=True,exist_ok=True)
with zipfile.ZipFile(args.output,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
    for path in sorted(source.rglob('*')):
        if path.is_symlink():
            raise SystemExit('Release payload contains a symlink')
        if path.is_file():
            archive.write(path,Path(source.name)/path.relative_to(source))
print(str(args.output))
