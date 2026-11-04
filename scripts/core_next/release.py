"""CORE NEXT manifest/acceptance adapter for the existing release Coordinator.

No default tag, no remote mutation on prepare/validate/status/history/verify.
stage-draft and publish are explicit commands for the parent-authorized release.
"""
from __future__ import annotations
import argparse
from email.parser import Parser
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tarfile
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
from release_coordinator import Coordinator, digest, now

GIT = r'C:\Program Files\Git\cmd\git.exe'


def ordinary_ancestors(path):
    """Reject links before resolving ownership or creating release state."""
    path = Path(os.path.abspath(path))
    for item in (path, *path.parents):
        if item.exists() or item.is_symlink():
            stat = item.lstat()
            require(not item.is_symlink() and not getattr(stat, 'st_file_attributes', 0) & 0x400,
                    'Linked release path is not permitted')
    return path


def canonical_lab(root, git=GIT):
    """A registered worktree uses its canonical clone's LAB, never a guessed sibling."""
    root = ordinary_ancestors(root)
    env = {k: v for k, v in os.environ.items()
           if k not in {'GIT_DIR', 'GIT_COMMON_DIR', 'GIT_WORK_TREE', 'GIT_INDEX_FILE'}}
    def query(*args):
        try:
            return subprocess.check_output([git, '--no-optional-locks', '-C', str(root), *args],
                                           env=env, stderr=subprocess.DEVNULL, timeout=15).decode('utf-8').strip()
        except (OSError, subprocess.SubprocessError) as error:
            raise RuntimeError('Cannot establish registered Git worktree ownership') from error
    top = ordinary_ancestors(query('rev-parse', '--path-format=absolute', '--show-toplevel'))
    require(top == root, 'Release source must be the registered worktree root')
    common = ordinary_ancestors(query('rev-parse', '--path-format=absolute', '--git-common-dir'))
    require(common.name == '.git' and common.is_dir(), 'Canonical non-bare Git common directory required')
    registered = [ordinary_ancestors(value[len('worktree '):])
                  for value in query('worktree', 'list', '--porcelain', '-z').split('\0')
                  if value.startswith('worktree ')]
    require(root in registered and common.parent in registered, 'Unregistered release source rejected')
    return ordinary_ancestors(common.parent.parent / (common.parent.name + '-LAB'))

REQUIRED = frozenset({'workstation','desktop','joomla','server','wheel','sdist','source'})
OPTIONAL = frozenset({'android','linux'})
METADATA = ('RELEASE-NOTES.md','INSTALLATION.md','ARTIFACT-MANIFEST.json','BUILD-REPORT.json','TEST-REPORT.json','SHA256SUMS.txt')
PRIMARY_CHECKS = ('fresh_install','behavior','control_center','isolation','restart','repair','uninstall')
PRIVATE_NAMES = {'configuration.php','joomla-bridge.json','local-session.json','workstation.json','.env'}
PRIVATE_SUFFIXES = {'.sqlite','.sqlite3','.db','.jks','.keystore','.pem','.pfx','.p12'}


def require(condition,message):
    if not condition:
        raise RuntimeError(message)


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def field(document,path):
    for key in path.split('.'):
        document=document[key]
    return document


def write_new(path,document):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('x',encoding='utf-8') as stream:
        json.dump(document,stream,indent=2,ensure_ascii=False);stream.write('\n')


def safe_name(name):
    require(isinstance(name,str) and Path(name).name==name and not any(v in name for v in ('/','\\','\r','\n','*','?','[',']')), 'Simple explicit asset filename required')
    require(name not in PRIVATE_NAMES and Path(name).suffix.lower() not in PRIVATE_SUFFIXES,'Private state is not a release asset')
    return name


def archive_members(names):
    for name in names:
        parts=Path(name.replace('\\','/')).parts
        require(not name.startswith(('/','\\')) and '..' not in parts and not re.match(r'^[A-Za-z]:',name),'Archive path escape')
        require(Path(name).name.lower() not in PRIVATE_NAMES and Path(name).suffix.lower() not in PRIVATE_SUFFIXES,'Private state/key found in archive')
        require(not any(part.lower() in {'private-evidence','snapshots','.git','__pycache__'} for part in parts),'Private/generated archive directory')


def refs(text):
    result={}
    for line in text.splitlines():
        if not line.strip(): continue
        bits=line.split()
        require(len(bits)==2 and re.fullmatch('[a-f0-9]{40}',bits[0]),'Invalid recorded Git reference')
        result[bits[1]]=bits[0]
    return result


class CoreNextRelease(Coordinator):
    def __init__(self,args):
        # Reuse publisher/ledger logic while keeping all state outside source.
        self.root=ROOT
        self.lab=args.lab.resolve()
        require(self.lab==canonical_lab(ROOT).resolve(),'Unexpected isolated lab root')
        self.assets=self.local(args.assets)
        require(self.assets.is_relative_to(self.lab/'dist'),'Release assets must stay under lab/dist')
        matrix=read(ROOT/'packaging/release/version.json')
        require(args.tag==matrix['tag'] and matrix['prerelease'] is True,'Only the explicit CORE NEXT prerelease tag is permitted')
        require(re.fullmatch('[a-f0-9]{40}',args.source_commit),'Full frozen source commit required')
        self.matrix=matrix
        self.run=self.lab/'release'/args.tag
        self.private=self.run/'private-evidence';self.private.mkdir(parents=True,exist_ok=True)
        self.path=self.run/'release-state.json'
        identity={'tag':args.tag,'source_sha':args.source_commit,'repository':matrix['repository']}
        self.state=read(self.path) if self.path.exists() else {**identity,'schema_version':1,'created_at':now(),'title':'DRAGONHYDRA CORE NEXT '+matrix['product_version']+' | Development prerelease','stages':{},'publication':{}}
        require(all(self.state.get(k)==v for k,v in identity.items()),'Release run identity is immutable; use a new tag/run for different source')
        self.git_executable=r'C:\Program Files\Git\cmd\git.exe'
        self.gh_executable=r'C:\Program Files\GitHub CLI\gh.exe'
        frozen=json.loads(self.command(['git','show',args.source_commit+':packaging/release/version.json']))
        require(frozen==matrix,'Frozen Git commit does not contain this CORE NEXT version matrix')

    def local(self,path):
        value=Path(path).resolve()
        require(value!=self.lab and value.is_relative_to(self.lab),'Release inputs/state must remain in the explicit lab')
        return value

    def witness(self,spec,source=True):
        path=self.local(spec['path'])
        require(path.is_file(),'Acceptance/build witness is missing: '+path.name)
        actual=digest(path)
        require(not spec.get('sha256') or spec['sha256']==actual,'Witness changed: '+path.name)
        doc=read(path)
        if source:
            require(field(doc,spec.get('source_field','source_commit'))==self.state['source_sha'],'Witness source differs from frozen candidate: '+path.name)
        return doc,{'name':path.name,'sha256':actual,'scope':spec.get('scope','Scope must be read in the referenced witness')}

    def source_zip(self,name):
        path=self.assets/safe_name(name)
        require(not path.exists(),'Source ZIP already exists; it is never replaced')
        self.assets.mkdir(parents=True,exist_ok=True)
        with path.open('xb') as stream:
            process=subprocess.run([self.git_executable,'archive','--format=zip','--prefix=DRAGONHYDRA-CORE-NEXT/',self.state['source_sha']],cwd=self.root,stdout=stream,stderr=subprocess.PIPE)
        require(process.returncode==0,'Exact Git source export failed; retain failed output for inspection')
        return path

    def inspect(self,path,kind):
        source=self.state['source_sha'];version=self.matrix['product_version'];python_version=self.matrix['python_version']
        if kind in {'workstation','desktop'}:
            spec=importlib.util.spec_from_file_location('existing_windows_payload_tools',ROOT/'packaging/windows/workstation/web/prepare_payload.py')
            helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
            observed=helper.windows_file_version(path)
            require(tuple(observed[:3])==(0,5,0),'EXE metadata is not CORE NEXT; renaming an old binary is prohibited')
            return {'windows_file_version':'.'.join(map(str,observed))}
        if kind in {'source','wheel','joomla','server','android'}:
            with ZipFile(path) as archive:
                require(archive.testzip() is None,'ZIP integrity failure')
                archive_members(archive.namelist())
                if kind=='source':
                    expected={}
                    raw=subprocess.check_output([self.git_executable,'ls-tree','-rz','--full-tree',source],cwd=self.root)
                    for entry in raw.split(b'\0'):
                        if not entry:continue
                        meta,name=entry.split(b'\t',1);mode,obj,sha=meta.split();require(obj==b'blob','Source archive must contain Git blobs only');expected[name.decode()]=sha.decode()
                    members={m.filename.split('/',1)[1]:archive.read(m) for m in archive.infolist() if not m.is_dir()}
                    require(set(members)==set(expected),'Source ZIP paths differ from exact frozen commit')
                    import hashlib
                    require(all(hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()==expected[name] for name,data in members.items()),'Source ZIP content differs from Git blobs')
                    return {'exact_git_blob_files':len(members)}
                if kind=='wheel':
                    names=archive.namelist();meta=Parser().parsestr(archive.read(next(n for n in names if n.endswith('.dist-info/METADATA'))).decode())
                    require(meta['Name']=='dragonhydra' and meta['Version']==python_version,'Wheel package/version mismatch')
                    info=json.loads(archive.read('dragonhydra/build_info.json'))
                    require(info['source_sha']==source and info['python_version']==python_version,'Wheel embedded identity mismatch')
                    return {'python_version':python_version,'embedded_source_sha':source}
                if kind=='joomla':
                    import xml.etree.ElementTree as ET
                    require(ET.fromstring(archive.read('pkg_dragonhydra.xml')).findtext('version')==version,'Joomla package version mismatch')
                    with ZipFile(io.BytesIO(archive.read('constituents/com_dragonhydra.zip'))) as component:
                        archive_members(component.namelist())
                        require(ET.fromstring(component.read('dragonhydra.xml')).findtext('version')==version,'Joomla component version mismatch')
                        require(json.loads(component.read('admin/build-info.json'))['source_sha']==source,'Joomla embedded source mismatch')
                    return {'joomla_version':version,'embedded_source_sha':source}
                if kind=='server':
                    infos=[]
                    for name in archive.namelist():
                        if name.lower().endswith('build-info.json'):
                            try:infos.append(json.loads(archive.read(name)))
                            except (ValueError,UnicodeError):pass
                    require(any(v.get('source_sha')==source and v.get('version') in {version,python_version} for v in infos),'Server ZIP lacks current embedded source/version proof')
                    return {'embedded_source_sha':source}
                return {'zip_integrity':True,'runtime_acceptance':'See explicit Android receipt; archive check is not device acceptance'}
        if kind in {'sdist','linux'}:
            with tarfile.open(path) as archive:
                archive_members([m.name for m in archive.getmembers()])
                require(not any(m.issym() or m.islnk() for m in archive),'Linked archive members are not permitted')
                if kind=='sdist':
                    member=next(m for m in archive if m.name.endswith('/src/dragonhydra/build_info.json'))
                    info=json.load(archive.extractfile(member))
                    require(info['source_sha']==source and info['python_version']==python_version,'sdist embedded identity mismatch')
                    return {'python_version':python_version,'embedded_source_sha':source}
            return {'tar_integrity':True,'runtime_acceptance':'See explicit preparation/runtime scope; no automatic native Linux claim'}
        raise RuntimeError('Unknown artifact kind')

    def prepare(self,spec_path):
        spec_path=self.local(spec_path);spec=read(spec_path)
        require(spec['source_commit']==self.state['source_sha'] and spec['tag']==self.state['tag'],'Asset specification identity mismatch')
        kinds=[a['kind'] for a in spec['artifacts']]
        require(REQUIRED<=set(kinds) and set(kinds)<=REQUIRED|OPTIONAL and len(kinds)==len(set(kinds)),'Explicit required artifact kinds are missing/duplicated')
        self.assets.mkdir(parents=True,exist_ok=True)
        require(not (self.assets/'ARTIFACT-MANIFEST.json').exists(),'Immutable manifest already prepared; do not overwrite it')
        old_hashes={a['sha256'] for a in read(ROOT/'BASELINE-LOCK.json')['artifacts']}
        artifacts=[];private_bindings=[]
        for raw in spec['artifacts']:
            name=safe_name(raw['filename']);path=self.assets/name;kind=raw['kind']
            if kind=='source' and not path.exists():self.source_zip(name)
            require(path.is_file() and 0<path.stat().st_size<2*1024**3,'Missing/oversized artifact: '+name)
            require(digest(path) not in old_hashes,'Old release artifact bytes cannot be renamed as CORE NEXT: '+name)
            require(raw['version'] in {self.matrix['product_version'],self.matrix['python_version']},'Actual component version must identify CORE NEXT')
            require(raw.get('target') and isinstance(raw.get('build_configuration'),dict) and raw.get('acceptance_scope'),'Target/build configuration/acceptance scope are required')
            proof=self.inspect(path,kind)
            if kind=='source':
                witness={'name':'git archive / exact Git blob verification','sha256':digest(path),'scope':'Exact frozen Git source content, independently checked by this tool'}
                private_build=None
            else:
                build,witness=self.witness(raw['build_receipt'])
                require(field(build,raw['build_receipt'].get('version_field','version'))==raw['version'],'Build receipt version mismatch: '+name)
                require(field(build,raw['build_receipt'].get('artifact_sha256_field','artifact_sha256'))==digest(path),'Build receipt does not bind exact artifact bytes: '+name)
                private_build={**raw['build_receipt'],'sha256':witness['sha256']}
            public_acceptance=[]
            private_acceptance=[]
            for acceptance in raw.get('acceptance',[]):
                doc,record=self.witness(acceptance)
                require(acceptance.get('checks') and all(field(doc,key) is True for key in acceptance['checks']),'Declared acceptance checks did not pass: '+name)
                public_acceptance.append(record)
                private_acceptance.append({**acceptance,'sha256':record['sha256']})
            artifacts.append({'kind':kind,'filename':name,'version':raw['version'],'source_sha':self.state['source_sha'],
                'target':raw['target'],'bytes':path.stat().st_size,'sha256':digest(path),
                'build_configuration':raw['build_configuration'],'dependencies':raw.get('dependencies',[]),
                'acceptance_scope':raw['acceptance_scope'],'build_witness':witness,'acceptance':public_acceptance,
                'inspection':proof,'verification':raw.get('verification',{}),'known_limitations':raw.get('known_limitations',[])})
            private_bindings.append({'filename':name,'build':private_build,'acceptance':private_acceptance})
        for name in ('RELEASE-NOTES.md','INSTALLATION.md','BUILD-REPORT.json','TEST-REPORT.json'):
            require((self.assets/name).is_file(),'Required reviewed report missing: '+name)
        manifest={'schema_version':'dragonhydra.release-candidate/1','legacy_manifest_schema_version':1,
            'product':'DRAGONHYDRA CORE NEXT','version':self.matrix['product_version'],
            'source_sha':self.state['source_sha'],'tag':self.state['tag'],'classification':'development prerelease',
            'source_commit':self.state['source_sha'],'release_type':'development-prerelease',
            'artifacts':artifacts,'omitted_platforms':{kind:'NOT_RUN / not included' for kind in OPTIONAL-set(kinds)},
            'tested_capabilities':spec.get('tested_capabilities',[]),
            'new_capabilities':spec.get('new_capabilities',[]),
            'improved_capabilities':spec.get('improved_capabilities',[]),
            'verification_improvements':spec.get('verification_improvements',[]),
            'known_limitations':spec.get('known_limitations',[]),
            'publication':{'state':'NOT_YET_PUBLISHED','scope':'State when this immutable manifest was assembled; release-state.json holds subsequent observations'}}
        write_new(self.assets/'ARTIFACT-MANIFEST.json',manifest)
        sums=''.join(digest(p)+'  '+p.name+'\n' for p in sorted(self.assets.iterdir()) if p.is_file() and p.name!='SHA256SUMS.txt')
        with (self.assets/'SHA256SUMS.txt').open('x',encoding='ascii') as stream:stream.write(sums)
        expected={v['filename'] for v in artifacts}|set(METADATA)
        require({p.name for p in self.assets.iterdir() if p.is_file()}==expected,'Unexpected asset file; explicit allowlist refused it')
        self.state.update(specification_path=str(spec_path),specification_sha256=digest(spec_path),
            primary_acceptance=str(self.local(spec['primary_acceptance'])),privacy_receipt=str(self.local(spec['privacy_receipt'])),
            artifact_bindings=private_bindings,manifest_sha256=digest(self.assets/'ARTIFACT-MANIFEST.json'))
        self.save()
        return manifest

    def primary_gate(self,manifest):
        path=self.local(self.state['primary_acceptance']);doc=read(path)
        primary=next(v for v in manifest['artifacts'] if v['kind']=='workstation')
        require(doc.get('passed') is True and doc.get('source_commit')==self.state['source_sha'] and doc.get('artifact_sha256')==primary['sha256'],'Primary acceptance source/hash/pass mismatch')
        require(all(doc.get(key,{}).get('passed') is True for key in PRIMARY_CHECKS),'All primary fresh-install/control/isolation/restart/repair/uninstall gates must pass')
        require(re.fullmatch('core-next-[a-f0-9]{32}',doc['fresh_install'].get('installation_id','')),'Fresh acceptance must name the owned CORE NEXT profile')
        for key in PRIMARY_CHECKS:
            evidence=doc[key].get('evidence',[])
            require(evidence,'Primary acceptance needs hashed real-file evidence: '+key)
            for item in evidence:
                proof=self.local(item['path']);require(proof.is_file() and digest(proof)==item['sha256'],'Primary evidence hash mismatch: '+key)
        return digest(path)

    def files(self):
        require(self.state.get('manifest_sha256')==digest(self.assets/'ARTIFACT-MANIFEST.json'),'Prepared manifest changed')
        manifest=read(self.assets/'ARTIFACT-MANIFEST.json')
        require(manifest['source_sha']==self.state['source_sha'],'Manifest source mismatch')
        expected={safe_name(a['filename']) for a in manifest['artifacts']}|set(METADATA)
        require({p.name for p in self.assets.iterdir() if p.is_file()}==expected,'Exact asset allowlist changed')
        sums={line.split('  ',1)[1]:line.split('  ',1)[0] for line in (self.assets/'SHA256SUMS.txt').read_text().splitlines() if line.strip()}
        require(set(sums)==expected-{'SHA256SUMS.txt'},'Checksum set mismatch')
        for name,expected_hash in sums.items():require(digest(self.assets/name)==expected_hash,'Asset checksum drift: '+name)
        for artifact in manifest['artifacts']:
            path=self.assets/artifact['filename']
            require(path.stat().st_size==artifact['bytes'] and digest(path)==artifact['sha256'],'Artifact content changed')
        for binding in self.state['artifact_bindings']:
            if binding['build']:self.witness(binding['build'])
            for acceptance in binding['acceptance']:self.witness(acceptance)
        self.primary_gate(manifest)
        privacy=read(self.local(self.state['privacy_receipt']))
        require(privacy.get('passed') is True and privacy.get('source_commit')==self.state['source_sha'],'Final privacy receipt missing/fails/source mismatch')
        require(privacy.get('artifact_sha256')=={name:digest(self.assets/name) for name in sorted(expected)},'Privacy receipt must bind every exact final asset')
        return [self.assets/name for name in sorted(expected)]

    def reconcile_history_branch(self, baseline, recorded, current):
        """Accept one frozen, pre-mission fact; never authorize a ref movement.

        The policy comes from the candidate Git commit, not an editable LAB
        override. Its exact local witnesses preserve the failed old gate and
        establish that the accepted tip predates this release mission. No
        ancestry test can authorize a newer tip, including a fast-forward.
        """
        policy=json.loads(self.command(['git','show',self.state['source_sha']+':packaging/release/history-reconciliation.json']))
        require(policy.get('schema_version')=='core-next.history-reconciliation/1'
                and policy.get('scope')=='EXACT_PREMISSION_REF_ONLY'
                and policy.get('repository')==self.state['repository'], 'History reconciliation policy identity mismatch')
        ref=policy.get('ref')
        require(ref=='refs/heads/continuity/genesis-20261031-a6', 'Only the reviewed continuity reference may be reconciled')
        legacy,accepted=policy.get('legacy_tip'),policy.get('accepted_tip')
        require(all(isinstance(v,str) and re.fullmatch('[a-f0-9]{40}',v) for v in (legacy,accepted))
                and legacy!=accepted and recorded.get(ref)==legacy, 'History reconciliation legacy tip mismatch')
        # Enforce even if the branch rewinds to the old baseline: this exception
        # names exactly one current tip, not a choice between old and new tips.
        require(current.get(ref)==accepted, 'Reconciled reference differs from the exact pre-mission tip')
        proofs=policy.get('proofs',{})
        require(set(proofs)=={'legacy_baseline','premission_audit','unaccepted_addendum'}, 'Exact history proof set required')
        paths={};evidence={}
        for name,spec in proofs.items():
            relative=spec.get('path')
            require(isinstance(relative,str) and not Path(relative).is_absolute()
                    and '..' not in Path(relative).parts and '\\' not in relative and ':' not in relative,
                    'History proof must use an ordinary LAB-relative path')
            path=ordinary_ancestors(self.lab/relative)
            require(path.is_relative_to(self.lab) and path.is_file(), 'History reconciliation proof missing')
            require(re.fullmatch('[a-f0-9]{64}',str(spec.get('sha256','')))
                    and digest(path)==spec['sha256'], 'History reconciliation proof hash mismatch')
            paths[name]=path;evidence[name]={'path':relative,'sha256':spec['sha256']}
        require(paths['legacy_baseline']==baseline and refs(baseline.read_text(encoding='utf-8-sig'))==recorded,
                'History reconciliation must retain the original branches baseline')
        audit=read(paths['premission_audit'])
        require(audit.get('status')=='PASS' and audit.get('repository',{}).get('full_name')==policy['repository']
                and audit.get('finished_at',{}).get('utc')==proofs['premission_audit'].get('observed_at'),
                'Pre-mission audit identity/time mismatch')
        branches=[v for v in audit.get('branches',[]) if v.get('ref')==ref]
        require(len(branches)==1 and branches[0].get('sha')==accepted, 'Pre-mission audit does not prove the accepted tip')
        addendum=read(paths['unaccepted_addendum'])
        require(addendum.get('coordinator_expected_baseline')==legacy
                and addendum.get('actual_tip_at_mission_start')==accepted and addendum.get('current_tip')==accepted
                and addendum.get('expected_is_ancestor_of_actual') is True
                and addendum.get('refs_moved_by_this_mission') is False
                and addendum.get('status')=='HISTORY_EVIDENCE_RECORDED_GATE_NOT_ACCEPTED'
                and addendum.get('publication_allowed') is False,
                'Historical unaccepted addendum mismatch')
        adjusted=dict(recorded);adjusted[ref]=accepted
        return adjusted,{'ref':ref,'legacy_tip':legacy,'accepted_tip':accepted,
                         'scope':'EXACT_PREMISSION_REF_ONLY','proofs':evidence,
                         'future_tip_movement_allowed':False,'refs_moved':False}

    def history(self):
        before=read(self.lab/'evidence/releases-before.json')
        after=json.loads(self.gh('api',f"repos/{self.state['repository']}/releases?per_page=100"))
        byid={v['id']:v for v in after};asset_count=0
        for old in before:
            require(old['id'] in byid,'Historical release removed')
            current=byid[old['id']]
            for key in ('tag_name','draft','prerelease'):require(current[key]==old[key],'Historical release classification changed')
            older={a['id']:a for a in old['assets']};newer={a['id']:a for a in current['assets']}
            require(set(older)==set(newer),'Historical asset ID set changed')
            for ident,asset in older.items():
                require(all(newer[ident].get(key)==asset.get(key) for key in ('name','size','digest')),'Historical asset name/size/digest changed');asset_count+=1
        reconciliation=None
        for name,flag in (('tags-before.txt','--tags'),('branches-before.txt','--heads')):
            baseline=self.lab/'evidence'/name
            old=refs(baseline.read_text(encoding='utf-8-sig'))
            current=refs(self.command(['git','ls-remote',flag,'origin']))
            if name=='branches-before.txt':
                old,reconciliation=self.reconcile_history_branch(baseline,old,current)
            require(all(current.get(key)==value for key,value in old.items()),'Historical '+name+' refs changed')
        stable=[v for v in before if not v['draft'] and not v['prerelease']]
        if stable:
            expected=max(stable,key=lambda v:v['published_at'])['id']
            latest=json.loads(self.gh('api',f"repos/{self.state['repository']}/releases/latest"))
            require(latest['id']==expected,'Stable/latest channel changed')
        return {'passed':True,'historical_releases':len(before),'historical_assets':asset_count,
                'historical_tags_preserved':True,'other_historical_branches_preserved':True,
                'history_reconciliation':reconciliation,'stable_latest_preserved':True}

    def verify_remote(self,remote,files):
        require(all(a.get('digest') for a in remote['assets']),'Remote SHA256 digests are required')
        return super().verify_remote(remote,files)

    def publish(self,*,draft_only=False):
        self.history()
        return super().publish(draft_only=draft_only)

    def downloads(self):
        super().downloads()
        evidence=self.history()
        evidence.update(source_sha=self.state['source_sha'],tag=self.state['tag'],verified_at=now(),status='PUBLICATION_AND_DOWNLOADS_VERIFIED')
        write_new(self.private/('preservation-verification-'+now().replace(':','').replace('.','')+'.json'),evidence)
        self.state['publication']['status']='PUBLICATION_AND_DOWNLOADS_VERIFIED';self.save()
        return evidence


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['prepare','validate','status','history','stage-draft','publish','verify'])
    parser.add_argument('--lab',type=Path,required=True);parser.add_argument('--assets',type=Path,required=True)
    parser.add_argument('--tag',required=True);parser.add_argument('--source-commit',required=True)
    parser.add_argument('--spec',type=Path)
    args=parser.parse_args();release=CoreNextRelease(args)
    if args.action=='prepare':require(args.spec is not None,'prepare requires reviewed --spec');print(json.dumps(release.prepare(args.spec),indent=2))
    elif args.action=='validate':print(json.dumps({'passed':True,'files':[p.name for p in release.files()]}))
    elif args.action=='status':print(json.dumps(release.state,indent=2))
    elif args.action=='history':print(json.dumps(release.history(),indent=2))
    elif args.action=='stage-draft':release.publish(draft_only=True)
    elif args.action=='publish':release.publish()
    elif args.action=='verify':print(json.dumps(release.downloads(),indent=2))


if __name__=='__main__':main()
