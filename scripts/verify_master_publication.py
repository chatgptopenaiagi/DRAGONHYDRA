"""Verify GENESIS master publication by metadata, public downloads and Git blobs.

Read-only against GitHub. Downloaded packages/receipts stay in a caller-owned fresh
directory. Reuses the release coordinator's streaming digest implementation.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import io
import json
from pathlib import Path
import shutil
import subprocess
import tarfile
from urllib.request import Request,urlopen
from zipfile import ZipFile
from release_coordinator import digest

REPO='chatgptopenaiagi/DRAGONHYDRA';TAG='genesis-a9-20261101'
GH=r'C:\Program Files\GitHub CLI\gh.exe'

def gh(path):
    r=subprocess.run([GH,'api',path],capture_output=True,text=True,encoding='utf-8');assert r.returncode==0,'GitHub API request failed';return json.loads(r.stdout)

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--assets',type=Path,required=True);p.add_argument('--source-sha',required=True);p.add_argument('--before',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--downloads',type=Path,required=True);a=p.parse_args()
    assert not a.output.exists() and not a.downloads.exists();a.downloads.mkdir(parents=True)
    report={'schema_version':1,'passed':False,'started_at':datetime.now(timezone.utc).isoformat(),'repository':REPO,'tag':TAG,'source_commit':a.source_sha,'checks':[],'downloads':[]}
    def check(name,ok,**evidence):report['checks'].append({'name':name,'status':'PASS' if ok else 'FAIL',**evidence});assert ok,name
    def download(url,target):
        with urlopen(Request(url,headers={'User-Agent':'DRAGONHYDRA-release-public-download-verification'}),timeout=60) as source,target.open('xb') as out:shutil.copyfileobj(source,out,1024*1024)
        return {'name':target.name,'bytes':target.stat().st_size,'sha256':digest(target)}
    try:
        release=gh(f'repos/{REPO}/releases/tags/{TAG}');report['release_url']=release['html_url'];report['release_id']=release['id'];report['published_at']=release['published_at']
        check('published_development_prerelease',not release['draft'] and release['prerelease'] and bool(release['published_at']))
        ref=gh(f'repos/{REPO}/git/ref/tags/{TAG}');obj=ref['object']
        if obj['type']=='tag':obj=gh(f'repos/{REPO}/git/tags/'+obj['sha'])['object']
        check('remote_tag_exact_source_commit',obj['type']=='commit' and obj['sha']==a.source_sha,remote_commit=obj['sha'])
        local={p.name:p for p in a.assets.iterdir() if p.is_file()};remote={v['name']:v for v in release['assets']}
        check('exact_asset_names_and_count',set(local)==set(remote),count=len(remote))
        for name,path in local.items():
            row=remote[name];assert row['size']==path.stat().st_size;assert row['digest']=='sha256:'+digest(path);assert row['state']=='uploaded'
        check('all_remote_asset_sizes_and_sha256_digests',True,count=len(local))
        def one(name):
            result=download(remote[name]['browser_download_url'],a.downloads/name);assert result['sha256']==digest(local[name]);assert result['bytes']==local[name].stat().st_size;return result
        with ThreadPoolExecutor(max_workers=4) as pool:
            for result in pool.map(one,sorted(local)):report['downloads'].append(result)
        check('all_anonymous_public_asset_downloads_rehashed',True,count=len(report['downloads']))
        # Both automatic GitHub source formats must expose the exact tagged tree.
        expected={}
        raw=subprocess.check_output(['git','ls-tree','-rz','--full-tree',a.source_sha])
        for row in raw.split(b'\0'):
            if not row:continue
            meta,name=row.split(b'\t',1);kind,sha=meta.split()[1:];assert kind==b'blob';expected[name.decode()]=sha.decode()
        def verify_members(members):
            assert set(members)==set(expected)
            # SHA1 blob ID includes Git's header; compare locally without subprocess per file.
            import hashlib
            for name,data in members.items():assert hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()==expected[name],name
        for kind in ('zipball','tarball'):
            target=a.downloads/('GITHUB-AUTOMATIC-SOURCE.'+('zip' if kind=='zipball' else 'tar.gz'))
            result=download(f'https://api.github.com/repos/{REPO}/{kind}/{TAG}',target)
            members={}
            if kind=='zipball':
                with ZipFile(target) as z:
                    for m in z.infolist():
                        if not m.is_dir():members[m.filename.split('/',1)[1]]=z.read(m)
            else:
                with tarfile.open(target) as z:
                    for m in z:
                        if m.isfile():members[m.name.split('/',1)[1]]=z.extractfile(m).read()
            verify_members(members);result['git_blob_equal_files']=len(members);report['downloads'].append(result)
        check('automatic_github_zip_and_tar_exact_tagged_source',True,files=len(expected))
        before=json.loads(a.before.read_text());after=gh(f'repos/{REPO}/releases?per_page=100');after_by_id={v['id']:v for v in after}
        historical_assets=0
        for old in before:
            current=after_by_id[old['id']];assert current['tag_name']==old['tag_name'];old_assets={v['id']:v for v in old['assets']};new_assets={v['id']:v for v in current['assets']};assert set(old_assets)==set(new_assets)
            for asset_id,old_asset in old_assets.items():
                for key in ('name','size','digest'):assert old_asset[key]==new_assets[asset_id][key]
                historical_assets+=1
        check('all_historical_release_assets_unchanged',True,releases=len(before),assets=historical_assets)
        report['assets']=[{k:v.get(k) for k in ('id','name','size','digest','browser_download_url')} for v in release['assets']];report['passed']=True
    except Exception as error:report['failure_class']=type(error).__name__;report['raw_exception_omitted']=True
    report['finished_at']=datetime.now(timezone.utc).isoformat();a.output.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'passed':report['passed'],'release_url':report.get('release_url'),'checks':report['checks'],'receipt':str(a.output)}));return 0 if report['passed'] else 1
if __name__=='__main__':raise SystemExit(main())
