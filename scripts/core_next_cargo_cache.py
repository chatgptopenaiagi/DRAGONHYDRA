"""Seal/copy only proven lab Cargo dependencies; application outputs never reuse."""
from pathlib import Path
import argparse, hashlib, json, os, shutil, subprocess

LAB=Path(r'C:\xampp\DRAGONHYDRA-CORE-NEXT-LAB')
RUSTC=r'C:\Users\LOVE\.cargo\bin\rustc.exe'
INPUTS=('src-tauri/src/main.rs','src-tauri/src/client_state.rs','src-tauri/src/external_target.rs',
        'src-tauri/tauri.conf.json','src-tauri/Cargo.toml','src-tauri/Cargo.lock',
        'web/app.js','web/index.html','web/style.css','web/favicon.svg')
def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()
def ordinary(path):
    path=Path(path).absolute()
    if path==LAB or not path.is_relative_to(LAB):raise ValueError('CORE_NEXT_CARGO_CACHE_OUTSIDE_LAB')
    for parent in [path,*path.parents]:
        if parent.exists() and (parent.is_symlink() or getattr(parent.lstat(),'st_file_attributes',0)&0x400):raise ValueError('CORE_NEXT_CARGO_CACHE_REPARSE_REJECTED')
    return path
def own_application(path):
    return any(part.startswith(('dragonhydra-desktop','dragonhydra_desktop')) for part in Path(path).parts)
def rust_version():
    return subprocess.check_output([RUSTC,'--version'],text=True,timeout=15).strip()
def source_hash(desktop):
    rows=[{'path':name,'sha256':digest(Path(desktop)/name)} for name in INPUTS]
    return hashlib.sha256(json.dumps(rows,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
def seal(root,desktop,proof_path,manifest_path):
    root,proof_path,manifest_path=map(ordinary,(root,proof_path,manifest_path))
    if manifest_path.exists():raise ValueError('CORE_NEXT_FRESH_CARGO_CACHE_MANIFEST_REQUIRED')
    proof=json.loads(proof_path.read_text(encoding='utf-8-sig'))
    if proof.get('compilation')!='PASS' and proof.get('status')!='BUILT_METADATA_VERIFIED':raise ValueError('CORE_NEXT_SUCCESSFUL_CARGO_BUILD_PROOF_REQUIRED')
    binary=root/'x86_64-pc-windows-msvc/release/dragonhydra-desktop.exe'
    expected=next((r['sha256'] for r in proof.get('files',[]) if r.get('path')=='DRAGONHYDRA-Client.exe'),None)
    if not expected or digest(binary)!=expected:raise ValueError('CORE_NEXT_CARGO_CACHE_BINARY_PROOF_MISMATCH')
    if source_hash(desktop)!=proof.get('source_content_sha256'):raise ValueError('CORE_NEXT_CARGO_CACHE_SOURCE_PROOF_MISMATCH')
    files=[]
    for parent,dirs,names in os.walk(root,followlinks=False):
        for name in dirs+names:
            path=Path(parent)/name
            if path.is_symlink() or getattr(path.lstat(),'st_file_attributes',0)&0x400:raise ValueError('CORE_NEXT_CARGO_CACHE_REPARSE_REJECTED')
        for name in names:
            path=Path(parent)/name;relative=path.relative_to(root)
            if own_application(relative) or name in {'.cargo-lock','CACHEDIR.TAG'}:continue
            files.append(dict(path=relative.as_posix(),bytes=path.stat().st_size,sha256=digest(path)))
    if not files:raise ValueError('CORE_NEXT_EMPTY_CARGO_DEPENDENCY_CACHE')
    manifest=dict(schema_version=1,scope='Dependencies only; own application and build/fingerprint outputs excluded',
        root=str(root),rustc_version=rust_version(),target='x86_64-pc-windows-msvc',cargo_lock_sha256=digest(Path(desktop)/'src-tauri/Cargo.lock'),
        proven_source_sha=proof['source_sha'],proof_path=str(proof_path),proof_sha256=digest(proof_path),files=sorted(files,key=lambda r:r['path']))
    manifest_path.write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    return dict(manifest=str(manifest_path),files=len(files),application_reused=False)
def copy_cache(root,manifest_path,desktop,destination):
    root,manifest_path,destination=map(ordinary,(root,manifest_path,destination))
    manifest=json.loads(manifest_path.read_text(encoding='utf-8-sig'))
    if manifest.get('schema_version')!=1 or manifest.get('root')!=str(root) or manifest.get('target')!='x86_64-pc-windows-msvc':raise ValueError('CORE_NEXT_CARGO_CACHE_IDENTITY_MISMATCH')
    if manifest.get('rustc_version')!=rust_version() or manifest.get('cargo_lock_sha256')!=digest(Path(desktop)/'src-tauri/Cargo.lock'):raise ValueError('CORE_NEXT_CARGO_CACHE_TOOLCHAIN_OR_LOCK_CHANGED')
    if digest(ordinary(manifest['proof_path']))!=manifest['proof_sha256']:raise ValueError('CORE_NEXT_CARGO_CACHE_BUILD_PROOF_CHANGED')
    if destination.exists() or destination.is_relative_to(root) or root.is_relative_to(destination):raise ValueError('CORE_NEXT_FRESH_CARGO_CACHE_DESTINATION_REQUIRED')
    files=manifest.get('files',[]);seen=set()
    if not files:raise ValueError('CORE_NEXT_EMPTY_CARGO_DEPENDENCY_CACHE')
    for row in files:
        relative=Path(row['path'])
        if relative.is_absolute() or '..' in relative.parts or ':' in row['path'] or own_application(relative):raise ValueError('CORE_NEXT_CARGO_CACHE_APPLICATION_OR_ESCAPE_REJECTED')
        path=ordinary(root/relative)
        if str(path).casefold() in seen:raise ValueError('CORE_NEXT_DUPLICATE_CARGO_CACHE_ENTRY')
        seen.add(str(path).casefold())
        if not path.is_file() or path.stat().st_size!=row['bytes'] or digest(path)!=row['sha256']:raise ValueError('CORE_NEXT_CARGO_DEPENDENCY_HASH_MISMATCH')
    destination.mkdir(parents=True)
    for row in files:
        target=destination/row['path'];target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(root/row['path'],target)
        if digest(target)!=row['sha256']:raise ValueError('CORE_NEXT_CARGO_DEPENDENCY_COPY_MISMATCH')
    return dict(copied_files=len(files),application_reused=False,source_build=manifest['proven_source_sha'],destination=str(destination))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['seal','copy']);p.add_argument('--root',required=True);p.add_argument('--desktop',required=True);p.add_argument('--manifest',required=True);p.add_argument('--proof');p.add_argument('--destination');a=p.parse_args()
    print(json.dumps(seal(a.root,a.desktop,a.proof,a.manifest) if a.action=='seal' else copy_cache(a.root,a.manifest,a.desktop,a.destination)))
