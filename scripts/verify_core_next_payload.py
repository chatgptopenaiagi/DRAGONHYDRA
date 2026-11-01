"""Hash every manifest member, caching only ordinary ancestor observations.

An optional destination must be a new lab directory. Only allowlisted, verified
members are copied; NSIS plugin extras and private state are never inferred.
"""
from pathlib import Path, PurePosixPath
import argparse, hashlib, json, os, shutil

def verify(root, lab, destination=None, exclude_components=()):
    root, lab = Path(root).absolute(), Path(lab).absolute()
    observed = set()
    def ordinary(path, boundary):
        path = Path(path).absolute()
        if not path.is_relative_to(boundary) or path == boundary:
            raise ValueError('CORE_NEXT_PATH_OUTSIDE_LAB')
        for ancestor in [path, *path.parents]:
            if ancestor in observed:
                break
            if ancestor.exists() or ancestor.is_symlink():
                stat = ancestor.lstat()
                if ancestor.is_symlink() or getattr(stat, 'st_file_attributes', 0) & 0x400:
                    raise ValueError('CORE_NEXT_REPARSE_PATH_REJECTED')
            observed.add(ancestor)
        return path
    ordinary(root, lab)
    manifest_path = ordinary(root/'PAYLOAD-MANIFEST.json', lab)
    content = manifest_path.read_bytes()
    manifest = json.loads(content.decode('utf-8-sig'))
    entries, seen = manifest.get('files', []), set()
    if not entries:
        raise ValueError('CORE_NEXT_NONEMPTY_PAYLOAD_MANIFEST_REQUIRED')
    for entry in entries:
        name = entry['path']
        pure = PurePosixPath(name.replace('\\', '/'))
        if pure.is_absolute() or '..' in pure.parts or ':' in name or not isinstance(entry.get('bytes'), int) or entry['bytes'] < 0:
            raise ValueError('CORE_NEXT_INVALID_PAYLOAD_ENTRY')
        path = ordinary(root.joinpath(*pure.parts), root)
        key = str(path).casefold()
        if key in seen:
            raise ValueError('CORE_NEXT_DUPLICATE_PAYLOAD_ENTRY')
        seen.add(key)
        # Do not cache the file observation: every member has a fresh lstat/hash.
        stat = path.lstat()
        if getattr(stat, 'st_file_attributes', 0) & 0x400 or not path.is_file() or stat.st_size != entry['bytes'] or hashlib.sha256(path.read_bytes()).hexdigest() != entry.get('sha256'):
            raise ValueError('CORE_NEXT_PAYLOAD_HASH_MISMATCH: '+name)
    if destination is not None:
        destination = ordinary(Path(destination).absolute(), lab)
        if destination.exists() or root.is_relative_to(destination) or destination.is_relative_to(root):
            raise ValueError('CORE_NEXT_FRESH_NONOVERLAPPING_PAYLOAD_DESTINATION_REQUIRED')
        destination.mkdir(parents=True)
        for entry in entries:
            pure = PurePosixPath(entry['path'].replace('\\', '/'))
            if pure.parts[0] in exclude_components:
                continue
            target = destination.joinpath(*pure.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(root.joinpath(*pure.parts), target)
            if hashlib.sha256(target.read_bytes()).hexdigest() != entry['sha256']:
                raise ValueError('CORE_NEXT_PAYLOAD_CHANGED_DURING_COPY')
    return {'verified':True,'files':len(entries),'manifest_sha256':hashlib.sha256(content).hexdigest(),'destination':str(destination) if destination else None}

if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--root',required=True); parser.add_argument('--lab',required=True); parser.add_argument('--destination')
    parser.add_argument('--exclude-component',action='append',default=[])
    args=parser.parse_args()
    print(json.dumps(verify(args.root,args.lab,args.destination,args.exclude_component)))
