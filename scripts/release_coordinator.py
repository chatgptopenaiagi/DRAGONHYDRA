"""Source-locked release stage ledger and sole GitHub publisher.

Mutable execution receipts never enter immutable release assets. Builds are
separate named commands; their successful outputs are invalidated on input drift.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time


def now():
    return datetime.now(timezone.utc).isoformat()


def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as data:
        for chunk in iter(lambda:data.read(1024*1024),b''):
            h.update(chunk)
    return h.hexdigest()


class Coordinator:
    def __init__(self, root, tag):
        self.root=Path(root).resolve()
        self.run=self.root/'build/release'/tag
        self.assets=self.root/'dist/releases'/tag/'assets'
        self.private=self.run/'private-evidence'
        self.private.mkdir(parents=True,exist_ok=True)
        self.path=self.run/'release-state.json'
        self.state=json.loads(self.path.read_text()) if self.path.exists() else {'schema_version':1,'tag':tag,'repository':'chatgptopenaiagi/DRAGONHYDRA','created_at':now(),'stages':{},'publication':{}}

    def save(self):
        temp=self.path.with_suffix('.tmp')
        temp.write_text(json.dumps(self.state,indent=2)+'\n',encoding='utf-8')
        os.replace(temp,self.path)

    def command(self, argv, cwd=None, capture=True):
        if argv and argv[0] in ('git','gh'):
            argv=[getattr(self,argv[0]+'_executable',argv[0]),*argv[1:]]
        result=subprocess.run(argv,cwd=cwd or self.root,text=True,encoding='utf-8',errors='replace',capture_output=capture)
        if result.returncode:
            raise RuntimeError(f'Command failed ({result.returncode}): {argv[0:3]}\n{(result.stderr or "")[-3000:]}')
        return result.stdout if capture else ''

    def gh(self,*args):
        return self.command(['gh',*args])

    def stage(self,name,argv,inputs,outputs,cwd=None):
        tracked={str(Path(p).resolve()):digest(p) for p in inputs}
        signature=hashlib.sha256(json.dumps({'sha':self.state.get('source_sha'),'argv':argv,'inputs':tracked},sort_keys=True).encode()).hexdigest()
        previous=self.state['stages'].get(name)
        if previous and previous.get('status')=='passed' and previous.get('signature')==signature:
            if all(Path(p).is_file() and digest(p)==h for p,h in previous.get('outputs',{}).items()):
                print(json.dumps({'stage':name,'status':'reused_verified'}));return
        record={'status':'running','started_at':now(),'command':argv,'cwd':str(cwd or self.root),'inputs':tracked,'signature':signature}
        self.state['stages'][name]=record;self.save()
        log=self.private/(name+'.log')
        tick=time.monotonic()
        with log.open('w',encoding='utf-8') as stream:
            result=subprocess.run(argv,cwd=cwd or self.root,stdout=stream,stderr=subprocess.STDOUT)
        record.update(finished_at=now(),duration_seconds=round(time.monotonic()-tick,3),exit_code=result.returncode,log=str(log))
        record['status']='passed' if result.returncode==0 else 'failed'
        if result.returncode==0:
            record['outputs']={str(Path(p).resolve()):digest(p) for p in outputs}
        self.save()
        if result.returncode:
            raise SystemExit(f'Stage {name} failed: exit {result.returncode}; see {log}')
        print(json.dumps({'stage':name,'status':'passed','duration_seconds':record['duration_seconds']}))

    def files(self):
        manifest=json.loads((self.assets/'ARTIFACT-MANIFEST.json').read_text())
        if manifest['source_sha']!=self.state['source_sha']:
            raise RuntimeError('Manifest source does not match frozen candidate')
        names=[]
        for artifact in manifest['artifacts']:
            if artifact['source_sha']!=self.state['source_sha']:
                raise RuntimeError('Artifact source differs from frozen candidate')
            name=artifact['filename']
            if Path(name).name!=name or '/' in name or '\\' in name:
                raise RuntimeError('Asset names must be simple relative filenames')
            path=self.assets/name
            if path.stat().st_size>=2*1024**3 or path.stat().st_size!=artifact['bytes'] or digest(path)!=artifact['sha256']:
                raise RuntimeError('Artifact integrity/size gate failed: '+name)
            checks=artifact['verification']
            if not checks.get('package_tested') or not checks.get('launch_tested'):
                raise RuntimeError('Unverified artifact: '+name)
            names.append(name)
        metadata=['RELEASE-NOTES.md','INSTALLATION.md','ARTIFACT-MANIFEST.json','BUILD-REPORT.json','TEST-REPORT.json','SHA256SUMS.txt']
        expected=set(names+metadata)
        actual={p.name for p in self.assets.iterdir() if p.is_file()}
        if actual!=expected:
            raise RuntimeError('Explicit asset set mismatch: '+str(actual^expected))
        sums={line.split('  ',1)[1]:line.split('  ',1)[0] for line in (self.assets/'SHA256SUMS.txt').read_text().splitlines() if line.strip()}
        if set(sums)!=expected-{'SHA256SUMS.txt'}:
            raise RuntimeError('Checksum coverage differs from explicit immutable assets')
        for name,value in sums.items():
            if digest(self.assets/name)!=value:
                raise RuntimeError('Final checksum mismatch: '+name)
        return [self.assets/name for name in names+metadata]

    def release(self):
        return json.loads(self.gh('api',f"repos/{self.state['repository']}/releases/tags/{self.state['tag']}"))

    def verify_remote(self,remote,files):
        if remote['tag_name']!=self.state['tag'] or not remote['prerelease']:
            raise RuntimeError('Wrong remote release identity/type')
        assets={a['name']:a for a in remote['assets']}
        if set(assets)!={p.name for p in files}:
            raise RuntimeError('Remote asset set differs from exact upload selection')
        for path in files:
            asset=assets[path.name]
            if asset['state']!='uploaded' or asset['size']!=path.stat().st_size:
                raise RuntimeError('Remote size/upload state mismatch: '+path.name)
            if asset.get('digest') and asset['digest']!='sha256:'+digest(path):
                raise RuntimeError('Remote digest mismatch: '+path.name)
        refs=self.command(['git','ls-remote','origin',f"refs/tags/{self.state['tag']}^{{}}"])
        if not refs.strip() or refs.split()[0]!=self.state['source_sha']:
            raise RuntimeError('Remote annotated tag does not peel to frozen source')
        return assets

    def publish(self, *, draft_only=False):
        files=self.files();repo=self.state['repository'];tag=self.state['tag']
        remote_tags=self.command(['git','ls-remote','origin',f'refs/tags/{tag}^{{}}'])
        if not remote_tags.strip() or remote_tags.split()[0]!=self.state['source_sha']:
            raise RuntimeError('Push and verify the exact annotated source tag before staging a draft')
        result=subprocess.run([getattr(self,'gh_executable','gh'),'api',f'repos/{repo}/releases/tags/{tag}'],capture_output=True,text=True)
        if result.returncode:
            if '404' not in result.stderr:
                raise RuntimeError('Unable to inspect release; do not infer absence')
            self.gh('release','create',tag,'--repo',repo,'--verify-tag','--draft','--prerelease','--latest=false','--title',self.state['title'],'--notes-file',str(self.assets/'RELEASE-NOTES.md'))
            remote=self.release()
            self.state['publication'].update(release_id=remote['id'],owned_draft=True,created_at=now());self.save()
        else:
            remote=json.loads(result.stdout)
            if remote['id']!=self.state['publication'].get('release_id') or not self.state['publication'].get('owned_draft'):
                raise RuntimeError('Existing release was not created by this release run')
        if not remote['draft']:
            self.verify_remote(remote,files);print(json.dumps({'status':'already_published_verified_metadata','url':remote['html_url']}));return
        present={a['name']:a for a in remote['assets']}
        for path in files:
            if path.name in present:
                asset=present[path.name]
                if asset.get('digest')!='sha256:'+digest(path) or asset['size']!=path.stat().st_size:
                    raise RuntimeError('Draft asset name conflict; no clobber permitted: '+path.name)
                continue
            self.gh('release','upload',tag,'--repo',repo,str(path))
            self.state['publication'].setdefault('uploaded',[]).append({'name':path.name,'sha256':digest(path),'at':now()});self.save()
        remote=self.release();self.verify_remote(remote,files)
        if remote['body'].replace('\r\n','\n').strip()!=(self.assets/'RELEASE-NOTES.md').read_text().replace('\r\n','\n').strip():
            raise RuntimeError('Draft notes differ from finalized immutable notes')
        self.state['publication']['draft_verified_at']=now();self.save()
        if draft_only:
            self.state['publication']['status']='OWNED_DRAFT_ASSETS_VERIFIED';self.save()
            print(json.dumps({'status':self.state['publication']['status'],'url':remote['html_url']}));return
        self.gh('release','edit',tag,'--repo',repo,'--draft=false','--prerelease','--latest=false')
        remote=self.release();self.verify_remote(remote,files)
        if remote['draft']:
            raise RuntimeError('Publication did not clear draft status')
        self.state['publication'].update(status='published_pending_download_verification',url=remote['html_url'],published_at=now());self.save()
        print(json.dumps({'status':self.state['publication']['status'],'url':remote['html_url']}))

    def downloads(self):
        files=self.files();remote=self.release();assets=self.verify_remote(remote,files)
        destination=self.run/'verification'/'downloads'
        destination.mkdir(parents=True,exist_ok=True)
        try:
            for path in files:
                target=destination/path.name
                if target.exists():
                    if digest(target)!=digest(path):
                        raise RuntimeError('Conflicting verification download; retain evidence')
                else:
                    self.gh('release','download',self.state['tag'],'--repo',self.state['repository'],'--pattern',path.name,'--dir',str(destination))
                if target.stat().st_size!=path.stat().st_size or digest(target)!=digest(path):
                    raise RuntimeError('Downloaded bytes mismatch: '+path.name)
            receipt={'status':'DOWNLOAD_VERIFIED','verified_at':now(),'source_sha':self.state['source_sha'],'url':remote['html_url'],'authenticated':True,
                     'artifacts':[{'filename':p.name,'bytes':p.stat().st_size,'sha256':digest(p),'download_url':assets[p.name]['browser_download_url']} for p in files]}
            (self.private/'download-verification.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
            self.state['publication'].update(status='DOWNLOAD_VERIFIED',download_verified_at=now());self.save()
            print(json.dumps({'status':'DOWNLOAD_VERIFIED','files':len(files),'url':remote['html_url']}))
        except Exception:
            self.state['publication']['status']='PUBLISHED_WITH_VERIFICATION_FAILURE';self.save();raise


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['status','run-stage','validate','publish','verify-downloads'])
    parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1])
    parser.add_argument('--tag',default='v0.4.0-alpha.1')
    parser.add_argument('--name')
    parser.add_argument('--cwd',type=Path)
    parser.add_argument('--input',action='append',default=[])
    parser.add_argument('--output',action='append',default=[])
    arguments=sys.argv[1:]
    split=arguments.index('--') if '--' in arguments else len(arguments)
    command=arguments[split+1:] if split<len(arguments) else []
    args=parser.parse_args(arguments[:split])
    c=Coordinator(args.root,args.tag)
    if args.action=='status':print(json.dumps(c.state,indent=2))
    elif args.action=='run-stage':
        if not args.name or not command:parser.error('run-stage requires --name and a command after --')
        c.stage(args.name,command,args.input,args.output,args.cwd)
    elif args.action=='validate':print(json.dumps({'status':'validated','files':[p.name for p in c.files()]}))
    elif args.action=='publish':c.publish()
    elif args.action=='verify-downloads':c.downloads()


if __name__=='__main__':main()
