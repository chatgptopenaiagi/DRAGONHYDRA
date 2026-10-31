"""Create one scoped release commit/export without changing the live Git index."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
import re
from pathlib import Path
import subprocess
import tarfile


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1])
    parser.add_argument('--tag',default='v0.4.0-alpha.1')
    parser.add_argument('--repair',action='store_true',help='Advance only this run-owned release branch with a repair commit')
    args=parser.parse_args();root=args.root.resolve();run=root/'build/release'/args.tag
    private=run/'private-evidence';private.mkdir(parents=True,exist_ok=True)
    state_path=run/'release-state.json'
    old_state=json.loads(state_path.read_text()) if state_path.exists() else None
    if old_state and old_state.get('source_sha') and not args.repair:
        raise SystemExit('Candidate is already frozen. Make an explicit new candidate for a source repair.')
    excluded={'__pycache__','node_modules','target','build','.dart_tool','.gradle','.kotlin','.cxx','gen'}
    selected=set()
    def add_tree(folder):
        for path in (root/folder).rglob('*'):
            rel=path.relative_to(root)
            if path.is_file() and not any(p in excluded for p in rel.parts) and path.name not in ('local.properties','key.properties','.flutter-plugins-dependencies') and path.suffix not in ('.pyc','.apk','.aab','.keystore','.jks','.sqlite3'):
                selected.add(rel.as_posix())
    for folder in ('src/dragonhydra','client/desktop','server/joomla','packaging/windows','packaging/release','packaging/genesis2','tests/installation','tests/ui','android/dragonhydra_mobile'):
        add_tree(folder)
    for path in (root/'scripts').iterdir():
        if path.is_file() and path.suffix in ('.ps1','.py') and path.name!='Verify-Joomla.ps1':selected.add(path.relative_to(root).as_posix())
    for path in (root/'tests').glob('test_*.py'):selected.add(path.relative_to(root).as_posix())
    for folder in ('deployment/public-access/reverse-proxy','deployment/public-access/tunnel'):
        for path in (root/folder).iterdir():
            if path.is_file() and path.suffix in ('.py','.js','.css','.html','.example'):selected.add(path.relative_to(root).as_posix())
    for path in (root/'deployment/public-access/scripts').glob('*.ps1'):
        if path.name!='Test-DragonApacheRecovery.ps1':selected.add(path.relative_to(root).as_posix())
    for name in ('gateway.example.json','requirements.txt','requirements-verification.txt','requirements-lock.txt','PACKAGE-README.md'):
        selected.add('deployment/public-access/'+name)
    for name in ('render_vps.py','install-gateway.sh','target.example.json','PACKAGE-README.md'):
        selected.add('deployment/public-access/vps/'+name)
    selected.add('deployment/public-access/tests/test_gateway.py')
    selected.add('deployment/public-access/tests/browser_public.py')
    selected.update(('.gitattributes','.gitignore','README.md','pyproject.toml','config/runtime/server-python314.lock.txt','docs/handover/INTEGRATED-BUILD-STATUS.md'))
    for name in ('openfootball-2025-26-en1.json','openfootball-2026-27-en1.json','football-data-2025-26-E0.csv'):
        selected.update(('data/raw/'+name,'data/raw/'+name+'.receipt.json'))
    files=sorted(selected)
    # No blanket add. Every selected source path is recorded before the mutation.
    (private/'source-file-allowlist.json').write_text(json.dumps(files,indent=2),encoding='utf-8')
    for name in files:
        path=root/name
        if not path.is_file():raise RuntimeError('Missing selected source: '+name)
        if path.stat().st_size>8*1024*1024:raise RuntimeError('Unexpected large source input: '+name)
        if path.suffix in ('.py','.json','.xml','.ps1','.dart','.md','.txt','.sh','.toml','.properties'):
            raw=path.read_bytes()
            if re.search(br'-----BEGIN (?:OPENSSH |RSA |EC )?PRIVATE KEY-----\r?\n[A-Za-z0-9+/=]{48,}', raw):
                raise RuntimeError('Private key found in selected source: '+name)
    env=os.environ.copy();env['GIT_INDEX_FILE']=str(private/('release-repair.index' if args.repair else 'release.index'))
    def git(*argv,input=None):
        result=subprocess.run(['git',*argv],cwd=root,env=env,input=input,text=True,capture_output=True,encoding='utf-8',errors='replace')
        if result.returncode:raise RuntimeError('Git operation failed: '+str(argv[:2])+'\n'+result.stderr[-2000:])
        return result.stdout.strip()
    parent=old_state['source_sha'] if args.repair else git('rev-parse','HEAD')
    git('read-tree',parent)
    for offset in range(0,len(files),40):git('add','-f','--',*files[offset:offset+40])
    git('update-index','--chmod=+x','--','deployment/public-access/vps/install-gateway.sh')
    diff=git('diff','--cached','--stat');(private/'scoped-source-diff.txt').write_text(diff,encoding='utf-8')
    names=git('diff','--cached','--name-only').splitlines()
    if not set(names)<=selected:raise RuntimeError('Temporary index contains unselected changes')
    tree=git('write-tree');sha=git('commit-tree',tree,'-p',parent,'-m',f'release: source-lock integrated {args.tag} prerelease')
    branch='release/'+args.tag
    if args.repair:
        if old_state.get('source_branch')!=branch or git('rev-parse','refs/heads/'+branch)!=parent:
            raise RuntimeError('Repair does not own the expected release branch head')
        git('update-ref','refs/heads/'+branch,sha,parent)
    else:
        git('branch',branch,sha)
    snapshot=run/'src'
    if snapshot.exists():raise RuntimeError('Snapshot already exists; do not overwrite another candidate')
    archive=private/'source.tar'
    with archive.open('wb') as stream:
        result=subprocess.run(['git','archive','--format=tar',sha],cwd=root,stdout=stream)
    if result.returncode:raise RuntimeError('Source archive failed')
    snapshot.mkdir()
    with tarfile.open(archive) as tar:tar.extractall(snapshot,filter='data')
    paths=[]
    for path in sorted(snapshot.rglob('*')):
        if path.is_file():paths.append({'path':path.relative_to(snapshot).as_posix(),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'bytes':path.stat().st_size})
    (run/'source-manifest.json').write_text(json.dumps({'source_sha':sha,'files':paths},indent=2),encoding='utf-8')
    matrix=json.loads((snapshot/'packaging/release/version.json').read_text())
    info={'version':matrix['product_version'],'python_version':matrix['python_version'],'source_sha':sha,'api_namespace':matrix['api_namespace'],'schema_version':matrix['schema_version']}
    work=run/'work';work.mkdir(exist_ok=True);(work/'build_info.json').write_text(json.dumps(info,indent=2)+'\n',encoding='utf-8')
    state={'schema_version':1,'tag':args.tag,'repository':matrix['repository'],'source_sha':sha,'source_parent':parent,'source_branch':branch,'source_root':str(snapshot),'created_at':datetime.now(timezone.utc).isoformat(),
           'title':f'DRAGONHYDRA {matrix["product_version"]} | Integrated prerelease','stages':{'freeze':{'status':'passed','command':['python','scripts/freeze_release.py','--tag',args.tag],'source_files':len(paths),'source_manifest':'source-manifest.json'}},'publication':{}}
    state_path.write_text(json.dumps(state,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'tag':args.tag,'source_sha':sha,'branch':branch,'source_root':str(snapshot),'files':len(paths)},indent=2))


if __name__=='__main__':main()
