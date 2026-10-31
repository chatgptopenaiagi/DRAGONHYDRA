"""Package and verify the exact tested optional Linux AI administrator helper.

The four-file ZIP contains source/support only. Native verification is read-only:
no model service, API configuration, credential or database operation is applied.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import sqlite3
import stat
import subprocess
import time
import traceback
import zipfile

ROOT = Path(__file__).resolve().parents[2]
NAME = 'DRAGONHYDRA-0.4.1-dev.1-Linux-LocalAI-Setup.zip'
HELPER_SHA = 'b81fc2d0d48b84cb930fec42f5ff49745859c06850c1e249c2245b2f34b8b0c9'
PROFILE_SHA = '9514c3b1279821d7a9690c5a6fa7d74d401d1ade0628c515ac7c1fdc664875ff'
PROOF_SHA = '2a7c67fa6313c1afaea79137d607759cba0c8c53353a75b4b490eed3e90bb7f4'
API_VERSION = '0.4.0~alpha.1+dev20261031.r8.ac7e694e9e38-1'
API_SOURCE = '1116ee30e64527c61207b6e753b71f69e37082549f76cf5e33e923d513c81158'
ALLOWLIST = {'configure_local_ai.py', 'INSTALLATION.md', 'MODEL-PROFILE.json', 'SOURCE-IDENTITY.json'}
BASE = ROOT/'build/linux/local-ai-20261031/configuration-r2'


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as source:
        for block in iter(lambda: source.read(1024*1024), b''): digest.update(block)
    return digest.hexdigest()


def encoded(value):
    return (json.dumps(value, indent=2, sort_keys=True,
                       default=lambda blob: {'bytes_hex': blob.hex()})+'\n').encode()


def installation():
    return '''# Optional Linux local-AI setup

This four-file source/support archive configures an existing DRAGONHYDRA Linux
API and separately installed CPU inference runtime. It is not a native installer,
complete workstation, model download, server package or desktop application.
No repository checkout or third-party Python module is required.

## Prerequisites

Tested: Ubuntu 26.04.1 x86-64, native systemd 259.5, OS /usr/bin/python3 3.14.4.
WSL2 was the test environment; enabled services do not keep a WSL instance alive.
There is no Linux graphical-client or continuous VPS-hosting claim.

Install the DRAGONHYDRA API and optional runtime DEBs separately, using their
own installation instructions. This archive accepts only these exact API pairs:

| API Debian version | Effective source SHA-256 |
|---|---|
| 0.4.0~alpha.1+dev20261031.r7.c77ddb3667f2-1 | 4a2b97baec4fc278bc405a99a1d970f66e030be77b63d5f043f0faf295b39bc0 |
| 0.4.0~alpha.1+dev20261031.r8.ac7e694e9e38-1 | 1116ee30e64527c61207b6e753b71f69e37082549f76cf5e33e923d513c81158 |

Required runtime: dragonhydra-local-ai-runtime
0.7.0~dev+git2280f0f.cpu1-1 amd64, installed at /opt/dragonhydra/local-ai.
Its DEB SHA-256 is a2f5e3a1e2e52f180479c572c3c27e5efd5934488062e754edc1535e5f33fe5a.
Required OS libraries: libc6 >= 2.43, libstdc++6 >= 15.2, libgcc-s1, libgomp1.
Required CPU flags: sse4_2, f16c, fma, bmi2, avx, avx2.
Have at least 6 GiB MemAvailable plus storage for the separate 2,497,280,256-byte
GGUF. The tested profile uses CPU only: 4 compute/batch threads, context 2048,
one parallel slot and zero GPU layers. Observed peak RSS was about 4.33 GiB;
memory and latency vary. The API does not wait for the optional model to load.

Use your existing readable Qwen3-4B-Q4_K_M.gguf or obtain it separately from the
pinned official artifact reference in MODEL-PROFILE.json. This archive performs
no download. Required SHA-256:
7485fe6f11af29433bc51cab58009521f205840f5b4ae3a32fa7f92e8534fdf5.
Choose an absolute readable path outside /home, /root and /run/user, which are
hidden by the model service's ProtectHome setting. Paths containing spaces work.
Do not change global permissions to make an unsuitable model path usable.

## Run from the extracted directory

Extract all four files to an administrator-controlled directory. On Linux,
verify the downloaded archive against the accompanying SHA256SUMS.txt first.
The following use OS Python with isolated imports; substitute your model path.

```sh
/usr/bin/python3 -I -B ./configure_local_ai.py --help
sudo /usr/bin/python3 -I -B ./configure_local_ai.py enable --model '/absolute/model directory/Qwen3-4B-Q4_K_M.gguf' --port 18765 --preflight
sudo /usr/bin/python3 -I -B ./configure_local_ai.py enable --model '/absolute/model directory/Qwen3-4B-Q4_K_M.gguf' --port 18765
sudo /usr/bin/python3 -I -B ./configure_local_ai.py status
sudo /usr/bin/python3 -I -B ./configure_local_ai.py disable
```

Preflight is read-only. Enable validates the exact API/runtime/profile, GGUF
hash, available RAM, loopback port and ownership before applying changes. A busy
port or foreign configuration is an error; no listener is killed or replaced.
Enable creates/reuses a random key without asking for or printing it, configures
dragonhydra-local-ai.service and adds only an optional API EnvironmentFile
drop-in. It restarts the owned API if already running. It preserves its base unit,
API environment, database, pairing and evidence. An absent optional env-file
does not block the core API; model errors have a labelled deterministic fallback.
Do not repeatedly restart services to bypass their configured failure budget.

The runtime listens only on 127.0.0.1:18765 and requires authentication. The
model service uses DynamicUser and systemd LoadCredential. Configuration lives
under /etc/dragonhydra/local-ai (root0700); key and api.env are root0600 local
PLAINTEXT, not an encrypted vault. Exclude them from diagnostics, releases and
ordinary/unprotected backups. Handle recovery only through a separately secured
administrator backup. Key rotation is not implemented. Never paste key contents
into command arguments, logs or support reports.

Disable stops/disables only the owned model service, removes its API drop-in,
and restarts an already-running API with its original configuration. It retains
the protected key/profile/ownership files, runtime and model weights for later
re-enable; the same key is reused. No API Requires/Wants dependency on AI is
created. Product paths remain /opt/dragonhydra, /etc/dragonhydra and
/var/lib/dragonhydra-api. No Joomla, Windows service or other model is managed.

## Observed verification and limits

The included helper's 37 focused regressions passed. Its R8 native integration
passed seven groups: real authenticated model fact selection, model restart/key
reuse, unavailable-model fallback, missing-env core startup, and exact restoration
of 760 retained matches and private configuration. That service test used the
installed runtime; this archive's final-byte test executes only help and a
read-only preflight from outside the repository. Older R7 native proof is
historical and used the prior helper revision. See TEST-REPORT.json accompanying
the ZIP for separated scopes. No service changes are needed to verify this ZIP.

Output is constrained selection of a supplied, evidence-linked source fact. It
does not establish new sports analysis or numerical predictions. Those arithmetic
and eligibility decisions remain deterministic. The hosted API test used the
normal host network namespace with llama.cpp --offline; it was not air-gapped.
A separate earlier runtime test used an isolated network namespace. These are
different verification claims. This archive is unsigned development support.
'''.encode()


def native_snapshot(payload):
    protected = {}
    paths = ['/usr/lib/systemd/system/dragonhydra-api.service', '/etc/dragonhydra/api.env',
             '/var/lib/dragonhydra-api/local-session.json', '/var/lib/dragonhydra-api/managed-port.json',
             '/etc/dragonhydra/local-ai/key', '/etc/dragonhydra/local-ai/api.env',
             '/etc/dragonhydra/local-ai/ownership.json', '/etc/dragonhydra/local-ai/configure.lock',
             '/etc/systemd/system/dragonhydra-local-ai.service',
             '/etc/systemd/system/dragonhydra-api.service.d/60-dragonhydra-local-ai.conf']
    for name in paths:
        path = Path(name)
        if not path.exists(): protected[name] = None; continue
        item = path.lstat()
        if not stat.S_ISREG(item.st_mode): raise RuntimeError('Unexpected protected path type')
        protected[name] = {'sha256': sha(path), 'mode': stat.S_IMODE(item.st_mode), 'uid': item.st_uid, 'gid': item.st_gid}
        if name.endswith('configure.lock'): protected[name]['inode'] = item.st_ino
    tables = {}
    with sqlite3.connect('file:/var/lib/dragonhydra-api/core.sqlite3?mode=ro', uri=True) as db:
        for name, in db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"):
            if not re.fullmatch('[A-Za-z_][A-Za-z0-9_]*', name): raise RuntimeError('Unsafe table identifier')
            width = len(db.execute('PRAGMA table_info("'+name+'")').fetchall())
            rows = db.execute('SELECT * FROM "'+name+'" ORDER BY '+','.join(map(str, range(1,width+1)))).fetchall()
            tables[name] = {'rows': len(rows), 'sha256': hashlib.sha256(encoded(rows)).hexdigest()}
    installed = {}
    for entry in payload['files']:
        relative = PurePosixPath(entry['path'])
        if relative.is_absolute() or '..' in relative.parts: raise RuntimeError('Unsafe payload entry')
        path = Path('/')/str(relative)
        if path.is_symlink(): raise RuntimeError('Unexpected API payload symlink')
        installed[str(relative)] = sha(path)
        if installed[str(relative)] != entry['sha256']: raise RuntimeError('Installed R8 payload drift')
    model = subprocess.check_output(['/usr/bin/systemctl','show','dragonhydra-local-ai.service','-p','ActiveState','-p','UnitFileState','-p','MainPID'], text=True)
    model = dict(line.split('=',1) for line in model.splitlines())
    if model != {'ActiveState':'inactive','UnitFileState':'disabled','MainPID':'0'}: raise RuntimeError('Optional model is not owned-disabled')
    raw = {str(path.relative_to('/var/lib/dragonhydra-api')):sha(path) for path in sorted(Path('/var/lib/dragonhydra-api/raw').rglob('*')) if path.is_file()}
    return {'protected':protected,'tables':tables,'api_payload':installed,'raw':raw,'model':model}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--model', type=Path, required=True, help='Existing model used only for native read-only preflight')
    args=parser.parse_args()
    work,out=args.work.resolve(),args.out.resolve()
    if (platform.system()!='Linux' or os.getuid()!=0 or work.exists() or out.exists()
            or work!=ROOT/'build/linux/local-ai-setup-20261031/run-r1'
            or out!=ROOT/'dist/linux/local-ai-setup-20261031'):
        raise SystemExit('Native root and fresh exact project-owned output directories required')
    work.mkdir(parents=True);out.mkdir(parents=True)
    report={'passed':False,'started_at':datetime.now(timezone.utc).isoformat(),'commands':[],'checks':[]}
    def check(name):report['checks'].append({'name':name,'passed':True});print(json.dumps({'passed':name}),flush=True)
    def run(name,argv,cwd):
        env=os.environ.copy();env['PYTHONPATH']='';env.pop('PYTHONHOME',None)
        begun=time.monotonic();result=subprocess.run(list(map(str,argv)),cwd=cwd,env=env,capture_output=True,text=True,timeout=150)
        (work/(name+'.stdout.log')).write_text(result.stdout);(work/(name+'.stderr.log')).write_text(result.stderr)
        report['commands'].append({'name':name,'argv':list(map(str,argv)),'cwd':str(cwd),'exit_code':result.returncode,'seconds':round(time.monotonic()-begun,3),'PYTHONPATH':'','isolated_python':True})
        if result.returncode:raise RuntimeError(name+' failed with exit'+str(result.returncode))
        return result.stdout
    try:
        helper=ROOT/'packaging/linux-native/configure_local_ai.py'
        profile=Path('/opt/dragonhydra/local-ai/profiles/qwen3-4b-q4_k_m.json')
        proof_path=BASE/'actual-r1/verification.json'
        if sha(helper)!=HELPER_SHA or sha(profile)!=PROFILE_SHA or sha(proof_path)!=PROOF_SHA:raise RuntimeError('Tested source/profile/proof hash changed')
        proof=json.loads(proof_path.read_text());prior=json.loads((BASE/'unit-tests-final-command.json').read_text())
        if (not proof['passed'] or len(proof['checks'])!=7 or prior['exit_code'] or prior['helper_sha256']!=HELPER_SHA
                or proof['api_identity']!={'debian_version':API_VERSION,'source_content_sha256':API_SOURCE}):raise RuntimeError('Prior exact-source verification failed')
        payload=json.loads((ROOT/'dist/linux/native-kernel-20261031/r8/PAYLOAD-MANIFEST.json').read_text())
        before=native_snapshot(payload);(work/'before.json').write_bytes(encoded(before))
        identity={'schema_version':1,'product_version':'0.4.1-dev.1','kind':'Optional administrator source/support helper; not installer',
                  'helper_sha256':HELPER_SHA,'model_profile_sha256':PROFILE_SHA,'source_commit':None,
                  'source_binding':'Exact tested helper content hash; not a clean committed release',
                  'tested_api_identity':proof['api_identity'],'runtime_debian_version':'0.7.0~dev+git2280f0f.cpu1-1',
                  'runtime_identity_sha256':'8cbab7eda95de3fcdb6414503f4b66a0e2d1a2d3296ef11e3f97107316b386c4',
                  'included_files':sorted(ALLOWLIST),'weights_bundled':False,'credentials_bundled':False,'runtime_bundled':False}
        files={'configure_local_ai.py':helper.read_bytes(),'INSTALLATION.md':installation(),'MODEL-PROFILE.json':profile.read_bytes(),'SOURCE-IDENTITY.json':encoded(identity)}
        archive=out/NAME
        with zipfile.ZipFile(archive,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as package:
            for name,body in sorted(files.items()):
                item=zipfile.ZipInfo(name,date_time=(2026,10,31,0,0,0));item.create_system=3;item.external_attr=(stat.S_IFREG|0o644)<<16;item.compress_type=zipfile.ZIP_DEFLATED
                package.writestr(item,body)
        final_hash=sha(archive);extracted=work/'extracted';extracted.mkdir()
        with zipfile.ZipFile(archive) as package:
            entries=package.infolist()
            if len(entries)!=4 or {entry.filename for entry in entries}!=ALLOWLIST or package.testzip() is not None:raise RuntimeError('Archive allowlist/CRC mismatch')
            for entry in entries:
                relative=PurePosixPath(entry.filename)
                if relative.is_absolute() or '..' in relative.parts or stat.S_IFMT(entry.external_attr>>16)!=stat.S_IFREG or stat.S_IMODE(entry.external_attr>>16)!=0o644:raise RuntimeError('Unsafe archive member')
                if package.read(entry)!=files[entry.filename]:raise RuntimeError('Final archive payload differs')
                (extracted/entry.filename).write_bytes(package.read(entry))
        check('Final ZIP four-file allowlist, regular0644 modes, CRC and exact source/profile bytes')
        run('extracted-help',['/usr/bin/python3','-I','-B',extracted/'configure_local_ai.py','--help'],extracted)
        check('Extracted helper --help runs with OS isolated Python outside repository imports')
        preflight=json.loads(run('extracted-read-only-preflight',['/usr/bin/python3','-I','-B',extracted/'configure_local_ai.py','enable','--model',args.model,'--port','18765','--preflight'],extracted))
        if (not preflight['ok'] or preflight['changed'] or preflight['already_enabled'] or preflight['api_version']!=API_VERSION or preflight['api_effective_sha256']!=API_SOURCE):raise RuntimeError('Extracted read-only preflight result differs')
        check('Extracted helper actual R8/model/runtime preflight succeeds with changed=false')
        after=native_snapshot(payload);(work/'after.json').write_bytes(encoded(after))
        if before!=after or sha(archive)!=final_hash:raise RuntimeError('Read-only verification modified native state or final ZIP bytes')
        check('All installed API payloads and all database/raw/protected state unchanged; model remains disabled')
        report['passed']=True;report['artifact']={'filename':NAME,'bytes':archive.stat().st_size,'sha256':final_hash}
        public_build={'schema_version':1,'status':'BUILT_AND_FINAL_ZIP_TESTED','product_version':'0.4.1-dev.1','builder_sha256':sha(__file__),
                      'artifact':report['artifact'],'helper_sha256':HELPER_SHA,'profile_sha256':PROFILE_SHA,'allowlist':sorted(ALLOWLIST),
                      'zip_regular_mode':'0644','source_commit':None,'signing':'Unsigned development source/support archive','published':False}
        public_tests={'schema_version':1,'artifact_sha256':final_hash,'final_archive_checks':report['checks'],'commands':[{'name':c['name'],'exit_code':c['exit_code'],'seconds':c['seconds'],'isolated_python':True,'PYTHONPATH':''} for c in report['commands']],
                      'reused_exact_helper_regressions':{'unique_cases':37,'seconds':29.595,'exit_code':0,'helper_sha256':HELPER_SHA,'rerun_for_archive':False},
                      'reused_native_r8_integration':{'groups':7,'passed':True,'proof_sha256':PROOF_SHA,'api_identity':proof['api_identity'],'rerun_for_archive':False,'scope':'Host-loopback installed-runtime typed fact selection; no whole-host airgap claim'},
                      'preservation':{'all_database_tables_unchanged':True,'raw_and_pairing_unchanged':True,'protected_optional_configuration_unchanged':True,'api_payload_files_unchanged':len(before['api_payload']),'retained_matches':760,'model_disabled':True},
                      'not_run':['Archive enable/disable was not repeated; exact helper native7 proof reused','Clean-machine Linux installation','Native Linux desktop journey','Whole-host airgap for hosted API']}
        manifest={'schema_version':1,'artifacts':[{**report['artifact'],'role':'Optional Linux administrator setup source/support archive','version':'0.4.1-dev.1','platform':'Ubuntu26.04.1 x86_64 / OS Python3.14.4 / systemd259.5','signing':'Unsigned development archive','BUILT':True,'PACKAGE_TESTED':True,'INSTALLER':False,'MODEL_BUNDLED':False,'RUNTIME_BUNDLED':False,'PUBLISHED':False,'prerequisites':['Exact R7/R8 native API','Exact separately installed CPU runtime DEB','Separate pinned Qwen3-4B-Q4_K_M GGUF','6GiB MemAvailable','Required CPU flags and OS libraries listed in INSTALLATION.md']} ]}
        for name,value in [('ASSET-MANIFEST.json',manifest),('BUILD-REPORT.json',public_build),('TEST-REPORT.json',public_tests)]: (out/name).write_bytes(encoded(value))
        (out/'INSTALLATION.md').write_bytes(files['INSTALLATION.md'])
        checksum_names=[NAME,'ASSET-MANIFEST.json','BUILD-REPORT.json','TEST-REPORT.json','INSTALLATION.md']
        (out/'SHA256SUMS.txt').write_text(''.join(sha(out/name)+'  '+name+'\n' for name in checksum_names))
    except BaseException as error:
        report['passed']=False
        report['error']={'type':type(error).__name__,'message':str(error)};(work/'error.log').write_text(traceback.format_exc())
    finally:
        report['finished_at']=datetime.now(timezone.utc).isoformat();(work/'verification.json').write_bytes(encoded(report))
    print(json.dumps({'passed':report['passed'],'artifact':report.get('artifact'),'error':report.get('error')},indent=2),flush=True)
    return 0 if report['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
