"""Allowlisted source-locked Joomla and public gateway release payloads.

This builder never starts or stops any service. Runtime/install verification is a
separate operation against isolated state. Root release coordination owns versions.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import re
import zipfile

STAMP = (2026,10,30,0,0,0)
GATEWAY_FILES = (
    'gateway.example.json','requirements.txt','requirements-lock.txt','requirements-verification.txt',
    'reverse-proxy/gateway.py','reverse-proxy/sports.html','reverse-proxy/site.js','reverse-proxy/site.css',
    'reverse-proxy/vps-nginx.conf.example','reverse-proxy/vps-nginx-https-ip.conf.example',
    'scripts/Start-PublicGateway.ps1','scripts/Stop-PublicGateway.ps1',
    'scripts/Install-Cloudflared.ps1','scripts/Start-QuickTunnel.ps1','scripts/Stop-QuickTunnel.ps1',
    'scripts/Start-DragonVpsTunnel.ps1','scripts/Register-DragonVpsTunnelTask.ps1',
    'vps/target.example.json','vps/render_vps.py','vps/install-gateway.sh',
    'tunnel/sshd-dragonhydra.conf.example','tunnel/authorized_keys.example',
    'tests/test_gateway.py','tests/browser_public.py',
)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def build_gateway(source_root, output, version, source_sha):
    source_root, output = Path(source_root).resolve(), Path(output).resolve()
    if not re.fullmatch(r'[0-9a-f]{40}',source_sha):
        raise ValueError('Expected the full source commit SHA')
    source = source_root/'deployment/public-access'
    info = {'schema_version':1,'version':version,'source_sha':source_sha,
            'api_namespace':'/dragon/api/v1','kernel_schema_version':1,
            'target':'Windows x64 gateway support; unexecuted Linux VPS configuration',
            'cloudflare':'Optional pinned download; no executable, token or running tunnel is distributed',
            'permanent_vps':'configuration_only_not_deployed'}
    entries = [(name,(source/name).read_bytes()) for name in GATEWAY_FILES]
    entries += [('README.md',(source/'PACKAGE-README.md').read_bytes()),
                ('vps/README.md',(source/'vps/PACKAGE-README.md').read_bytes()),
                ('build-info.json',(json.dumps(info,sort_keys=True,indent=2)+'\n').encode())]
    output.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
        for name,payload in sorted(entries):
            entry=zipfile.ZipInfo(name,STAMP)
            entry.compress_type=zipfile.ZIP_DEFLATED
            entry.external_attr=(0o100755 if name.endswith('.sh') else 0o100644)<<16
            archive.writestr(entry,payload)
    return {'filename':output.name,'bytes':output.stat().st_size,'sha256':digest(output),
            'version':version,'source_sha':source_sha,'role':'public_gateway_support',
            'built':True,'payload_files':len(entries),'api_namespace':'/dragon/api/v1',
            'signing':'unsigned archive; optional Cloudflare download checked separately'}


def build_joomla(source_root,output,source_sha):
    script=Path(source_root)/'scripts/build_joomla.py'
    spec=importlib.util.spec_from_file_location('release_component_builder',script)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.build(output,source_root=source_root,source_sha=source_sha)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('target',choices=('joomla','gateway'))
    parser.add_argument('--source-root',type=Path,required=True)
    parser.add_argument('--source-sha',required=True)
    parser.add_argument('--version',required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    result=build_gateway(args.source_root,args.output,args.version,args.source_sha) if args.target=='gateway' else build_joomla(args.source_root,args.output,args.source_sha)
    print(json.dumps(result,indent=2))


if __name__=='__main__':
    main()
