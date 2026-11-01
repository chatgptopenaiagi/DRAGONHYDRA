"""Release-local known-secret scan; no native/browser input and no secret output.

Inspect the explicit asset directory, Git HEAD snapshot and fully extracted NSIS
payload. Known owner values are read only from existing protected local handoffs.
Archive members are recursively decompressed rather than scanning compressed bytes
alone. This is a known-value/privacy scan, not a claim of universal secret detection.
"""
import argparse
import base64
from datetime import datetime, timezone
import io
import json
from pathlib import Path
import subprocess
import sys
import tarfile
from urllib.parse import quote
from zipfile import ZipFile,is_zipfile

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tests/installation'))
from joomla_frontend_credentials import load_credentials

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--assets',type=Path,required=True);p.add_argument('--installer-extracted',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();assert not args.output.exists()
    values={load_credentials()['password']}
    states=[ROOT/'build/workstation/test-install/state data',ROOT/'build/workstation/test-install/genesis-a8/state data',ROOT/'build/workstation/test-install/provider-a2/state data',Path('C:/ProgramData/DRAGONHYDRA')]
    for state in states:
        cfg=json.loads((state/'workstation.json').read_text(encoding='utf-8-sig'))
        for key in ('root_password','db_password','core_db_password','admin_password'):
            if cfg.get(key):values.add(cfg[key])
        values.add(json.loads((state/'client/local-session.json').read_text(encoding='utf-8-sig'))['token'])
    patterns=set()
    for value in values:
        patterns.update((value.encode(),value.encode('utf-16le'),json.dumps(value)[1:-1].encode(),quote(value,safe='').encode(),base64.b64encode(value.encode())))
    report={'schema_version':1,'passed':False,'started_at':datetime.now(timezone.utc).isoformat(),'known_private_values_compared':len(values),'secrets_or_fingerprints_emitted':False,'ui_input_used':False,'files':0,'archive_members':0,'uncompressed_bytes_inspected':0,'matches':[],'scope':'Known values from four existing profiles and owner DPAPI login; explicit artifacts, recursive ZIP/tar content, full NSIS extraction, tracked HEAD files. Screenshots previously visually sanitized.'}
    def inspect(data,label,depth=0):
        assert depth<8,'Unexpected archive nesting'
        report['uncompressed_bytes_inspected']+=len(data)
        if any(pattern in data for pattern in patterns): report['matches'].append(label)
        if is_zipfile(io.BytesIO(data)):
            with ZipFile(io.BytesIO(data)) as z:
                for member in z.infolist():
                    if not member.is_dir():
                        assert member.file_size<512*1024*1024
                        report['archive_members']+=1;inspect(z.read(member),label+'!'+member.filename,depth+1)
        elif data[:2]==b'\x1f\x8b':
            with tarfile.open(fileobj=io.BytesIO(data),mode='r:gz') as z:
                for member in z:
                    if member.isfile():report['archive_members']+=1;inspect(z.extractfile(member).read(),label+'!'+member.name,depth+1)
    try:
        files=subprocess.check_output(['git','ls-files','-z'],cwd=ROOT).decode().split('\0')
        for name in filter(None,files):
            data=subprocess.check_output(['git','show','HEAD:'+name],cwd=ROOT);inspect(data,'git:'+name);report['files']+=1
        for directory in (args.assets,args.installer_extracted):
            assert directory.is_dir()
            for path in sorted(directory.rglob('*')):
                if path.is_file():inspect(path.read_bytes(),str(path.relative_to(ROOT)));report['files']+=1
        report['passed']=not report['matches']
    except Exception as error:
        report['failure_class']=type(error).__name__;report['raw_error_omitted']=True
    report['finished_at']=datetime.now(timezone.utc).isoformat();args.output.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report));return 0 if report['passed'] else 1
if __name__=='__main__':raise SystemExit(main())
