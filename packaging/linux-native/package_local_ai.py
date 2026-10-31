"""Package the verified optional CPU llama-server, without weights or services.

Exact runtime hashes and safe SONAME links are input gates. The original runtime
and its identity stay unchanged. Debian scripts perform CPU checks only: no
service, configuration, credential or model installation is performed.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import subprocess
import tarfile
import time
import traceback

ROOT=Path(__file__).resolve().parents[2]
BASE=ROOT/'build/linux/local-ai-20261031'
RUNTIME=ROOT/'runtime/linux-local-ai/llama-2280f0f-cpu-r1'
PREFIX=Path('/opt/dragonhydra/local-ai')
NAME='dragonhydra-local-ai-runtime'
VERSION='0.7.0~dev+git2280f0f.cpu1-1'
IDENTITY_SHA='90511d97d651dcedd3b5b512ce2e108ce44d4fb682546510e6640c185d64e023'
LINKS_SHA='c22574b036c536d2aa6fe06191e7390d385ac8490f1db7bd5e8df5d0bb6a6a40'
FEATURES=('sse4_2','f16c','fma','bmi2','avx','avx2')
PREINST='''#!/bin/sh
set -eu
if [ -n "${DPKG_ROOT:-}" ] && [ "$DPKG_ROOT" != / ]; then exit 0; fi
case "${1:-}" in install|upgrade) ;; *) exit 0 ;; esac
if [ "$(uname -m)" != x86_64 ]; then echo "DRAGONHYDRA local AI requires Linux x86_64." >&2; exit 1; fi
seen=0
while IFS= read -r line; do
  case "$line" in flags*:*)
    seen=1
    flags=${line#*:}
    for feature in sse4_2 f16c fma bmi2 avx avx2; do
      case " $flags " in *" $feature "*) ;; *) echo "DRAGONHYDRA local AI requires CPU feature: $feature" >&2; exit 1 ;; esac
    done
    ;;
  esac
done < /proc/cpuinfo
if [ "$seen" -ne 1 ]; then echo "Unable to verify required Linux CPU flags." >&2; exit 1; fi
'''


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def json_bytes(value):
    return (json.dumps(value,indent=2,ensure_ascii=False)+'\n').encode()


def tar_bytes(files,links,epoch):
    """Explicit root-owned regular entries and hash-validated relative aliases."""
    output=io.BytesIO()
    with tarfile.open(fileobj=output,mode='w:xz',format=tarfile.GNU_FORMAT,preset=6) as archive:
        directories={'.'}
        for name in [*files,*links]:
            parent=PurePosixPath(name).parent
            while str(parent)!='.':directories.add(str(parent));parent=parent.parent
        for name in sorted(directories,key=lambda n:(n.count('/'),n)):
            item=tarfile.TarInfo('./' if name=='.' else './'+name);item.type=tarfile.DIRTYPE;item.mode=0o755
            item.uid=item.gid=0;item.uname=item.gname='root';item.mtime=epoch;archive.addfile(item)
        for name in sorted(set(files)|set(links)):
            assert not PurePosixPath(name).is_absolute() and '..' not in PurePosixPath(name).parts
            item=tarfile.TarInfo('./'+name);item.uid=item.gid=0;item.uname=item.gname='root';item.mtime=epoch
            if name in links:item.type=tarfile.SYMTYPE;item.linkname=links[name];item.mode=0o777;archive.addfile(item)
            else:
                body,mode=files[name];item.size=len(body);item.mode=mode;archive.addfile(item,io.BytesIO(body))
    return output.getvalue()


def finalize_public(work,output):
    """Finalize metadata after the independently executed API integration gate.

    Never repack software or rewrite its original private execution records.
    The installed-prefix tests and identical-code reference model/API proofs are
    explicitly separate, including their different network boundaries.
    """
    report=json.loads((work/'BUILD-REPORT.json').read_text())
    installed=json.loads((work/'INSTALL-AUDIT.json').read_text())
    offline=json.loads((BASE/'runtime-proof-r1/verification.json').read_text())
    api=json.loads((BASE/'integration-r1/run/verification.json').read_text())
    api_status=json.loads((BASE/'integration-r1/STATUS.json').read_text())
    assert report['passed'] and installed['passed'] and offline['passed'] and api['passed'] and api_status['passed']
    artifact=output/report['artifact']['filename'];assert sha(artifact)==report['artifact']['sha256'] and artifact.stat().st_size==report['artifact']['bytes']
    assert api['runtime_integrity']['manifest_sha256']==IDENTITY_SHA and api['runtime_integrity']['alias_manifest_sha256']==LINKS_SHA
    assert api['accepted']['kind']=='local_llm' and api['accepted']['mode']=='constrained_source_fact_selection'
    assert api['restored']['public_state_equal'] and api['restored']['temporary_dropin_absent'] and api['restored']['deterministic_fallback_code']=='AI_NOT_CONFIGURED'
    for name,key in (('package_local_ai.py','package_script_sha256'),('build_deb.py','archive_helper_sha256')):
        assert sha(work/'packaging-source'/name)==report['input_provenance'][key]
    link_manifest=json.loads((BASE/'runtime-link-manifest.json').read_text())
    original=json.loads((RUNTIME/'BUILD-IDENTITY.json').read_text())
    assert sha(RUNTIME/'BUILD-IDENTITY.json')==IDENTITY_SHA and sha(BASE/'runtime-link-manifest.json')==LINKS_SHA
    prefix='opt/dragonhydra/local-ai'
    entries=json.loads((work/'PAYLOAD-MANIFEST.json').read_text())['files']
    identity_path=work/'extracted'/prefix/'BUILD-IDENTITY.json'
    profile_path=work/'extracted'/prefix/'profiles/qwen3-4b-q4_k_m.json'
    payload_identity=json.loads(identity_path.read_text());profile=json.loads(profile_path.read_text())
    software={**report['artifact'],'role':'Optional Linux CPU local-inference runtime component','component_version':VERSION,
        'upstream_version':'0.7.0-dev','upstream_commit':payload_identity['upstream_commit'],
        'upstream_source_content_sha256':payload_identity['upstream_selected_source_content_sha256'],
        'product_release_commit':None,'target_os':'Ubuntu26.04.1 x86_64/WSL2','architecture':'amd64',
        'required_cpu_features':list(FEATURES),'dependencies':['libc6>=2.43','libstdc++6>=15.2','libgcc-s1','libgomp1'],
        'signing':'unsigned development package','weights_bundled':False,'service_autostart':False,
        'upstream_runtime_identity_sha256':IDENTITY_SHA,'upstream_link_manifest_sha256':LINKS_SHA,
        'sanitized_packaged_identity_sha256':sha(identity_path),
        'BUILT':True,'EXTRACTED':True,'INSTALLED':True,'LAUNCH_TESTED':True,'CLEAN_MACHINE_TESTED':False,
        'INSTALLED_PREFIX_MODEL_INFERENCE_TESTED':False,'IDENTICAL_REFERENCE_RUNTIME_OFFLINE_INFERENCE_TESTED':True,
        'R7_API_INTEGRATION_WITH_IDENTICAL_REFERENCE_RUNTIME_TESTED':True,'REBOOT_TESTED':False,
        'compatibility':{'application_effective_source_content_sha256':'4a2b97baec4fc278bc405a99a1d970f66e030be77b63d5f043f0faf295b39bc0',
                         'application_origin_sha256':'8b3e7e0e440b9f4d090517237724999bcd824d86f460663e65d940c9c1d20fd5',
                         'kernel_api_namespace':'/dragon/api/v1','runtime_inference_interface':'llama.cpp /completion with JSON schema'}}
    manifest={'schema_version':1,'status':'OPTIONAL_RUNTIME_INSTALLED_AND_IDENTICAL_REFERENCE_MODEL_API_VERIFIED',
        'published':False,'artifacts':[software],'omitted_components':['Model weights','Sports API server','Joomla/PHP/Apache/MariaDB','Desktop client','Linux complete workstation','RPM','GPU runtime']}
    native=[{k:c[k] for k in ('name','exit_code','seconds')} for c in report['commands'] if c['name']=='native-dpkg-install-once']
    assert len(native)==1 and native[0]['exit_code']==0
    build_report={'schema_version':1,'scope':report['scope'],'version':VERSION,'artifact':report['artifact'],
        'upstream_version':'0.7.0-dev','upstream_commit':payload_identity['upstream_commit'],
        'upstream_source_content_sha256':payload_identity['upstream_selected_source_content_sha256'],
        'build_inputs':report['input_provenance'],'payload_regular_files':len([i for i in entries if i['kind']=='regular']),
        'payload_relative_links':len(link_manifest['links']),'model_weights_included':False,'cache_home_scratch_excluded':True,
        'metadata_sanitization':{'input_build_identity_sha256':IDENTITY_SHA,'packaged_identity_sha256':sha(identity_path),
                                 'qualified_change':'Build metadata sanitized; all eight ELF files and original dedicated notices retain exact tested bytes.'},
        'native_install_preflight':report['install_preflight'],'native_install_commands':native,
        'signing':'unsigned development package','reproducible_procedure':True,'byte_identical_rebuild_tested':False,
        'metadata_finalizer_sha256':sha(__file__),
        'evidence':['build/linux/local-ai-20261031/build-r1','build/linux/local-ai-20261031/package-r1/retry-2']}
    tests={'schema_version':1,'verified_at':datetime.now(timezone.utc).isoformat(),'passed':True,
        'scope':'Optional runtime package, installed CLI/loader checks, identical-code reference inference and installed R7 API pairing; no complete workstation or clean-machine claim.',
        'package_checks':{'passed':True,'groups':len(report['checks']),'regular_files':47,'relative_links':12,'native_install_commands':native,
                          'version_help_actual_execution':True,'private_library_closure_verified':True,'no_service_or_model_started_by_installation':True},
        'installed_payload_audit':{'passed':True,'checks':len(installed['checks']),'regular_files':47,'relative_links':12,'all_root_owned_modes_hashes_verified':True},
        'reference_offline_inference':{'passed':True,'checks':len(offline['checks']),'exact_same_elf_library_bytes':True,
            'private_network_namespace':True,'interfaces':['lo'],'external_routes':[],'external_probe_errno':101,
            'cpu_compute_threads':4,'slots':1,'context_tokens':2048,'generated_tokens':offline['generated_tokens'],
            'load_ready_seconds':offline['load_ready_seconds'],'completion_seconds':offline['completion_seconds'],
            'peak_observed_rss_kib':offline['memory']['peak_observed_rss_kib'],'key_storage':'Sealed anonymous memfd0600; no plaintext disk key or key argv',
            'owned_runner_exit_code':offline['runner_exit_code'],'owned_runner_reaped':offline['runner_reaped'],'key_closed':offline['anonymous_key_closed']},
        'reference_installed_r7_api_integration':{'passed':True,'checks':len(api['checks']),'command_exit_code':api_status['command_exit_code'],
            'runtime_location':'Verified project reference runtime; installed-prefix generation was not repeated because all ELF/library bytes are identical.',
            'network_isolation':'Normal host network namespace with authenticated loopback; distinct from the offline namespace proof.',
            'worker_identity':'Actual systemd DynamicUser','worker_uid':api['memory_configuration']['worker_uid'],
            'operation':'HTTP202 typed local_explanation job','job_id':api['accepted']['job_id'],'status':'succeeded',
            'result_kind':api['accepted']['kind'],'result_mode':api['accepted']['mode'],
            'generated_tokens':api['accepted']['runtime']['tokens_predicted'],'queue_to_terminal_seconds':api_status['actual_job']['queue_to_terminal_seconds'],
            'evidence_id':api['accepted']['evidence_id'],'model_package_sha256':api['accepted']['package_sha256'],
            'retained_records':api['restored']['records'],'public_state_unchanged':api['restored']['public_state_equal'],
            'temporary_dropin_removed':api['restored']['temporary_dropin_absent'],'original_unconfigured_settings_restored':not api['restored']['settings']['configured'],
            'fallback_restored_code':api['restored']['deterministic_fallback_code'],'service_active_after_restore':api['restored']['service']['ActiveState']=='active',
            'runner_exit_code':'Not serialized in this API-phase report; separate offline runner exit0 is recorded.'},
        'proof_reuse':{'model_not_rerun_during_package_tests':True,'basis':'Exact same eight ELF hashes and twelve alias targets; native extracted/installed closure tests executed separately.'},
        'retained_first_attempts':[{'path':'build/linux/local-ai-20261031/build-r1/BUILD-REPORT.initial.json','cause':'Strict preflight rejected unused standard FetchContent guard after successful configure; exact CPU cache/source revalidated before one compile.'},
            {'path':'build/linux/local-ai-20261031/package-r1/BUILD-REPORT.json','cause':'Notice preparation referenced a header absent from actual upstream; stopped before artifact/install. Fixed by enumerating verified vendor manifest, no runtime code change.'}],
        'not_run':['Model generation from the installed /opt prefix','Clean machine or reboot','Optional package removal/reinstall','GUI/full Linux workstation','GPU profile or larger model'],
        'evidence_paths':['build/linux/local-ai-20261031/runtime-proof-r1/verification.json','build/linux/local-ai-20261031/integration-r1/run/verification.json',
            'build/linux/local-ai-20261031/package-r1/retry-2/BUILD-REPORT.json','build/linux/local-ai-20261031/package-r1/retry-2/INSTALL-AUDIT.json']}
    installation=(work/'extracted'/'usr/share/doc'/NAME/'README.md').read_text()
    installation+='''
Observed installation: native dpkg installation completed once (exit0); installed
version/help and every payload/link/mode/hash passed. The API was independently
paired with the identical reference runtime, accepted a real retained-evidence
job and then restored its original760 records/settings. That phase used the
normal host namespace; the eight-check offline inference proof separately used
a private loopback-only namespace. No model was rerun from this installed prefix.
The optional component is currently dormant; installation starts no service.
'''
    notes=f'''# Choose your download

`{artifact.name}` installs only the optional Linux CPU llama.cpp runtime.
It was built, extracted, installed and CLI/loader-tested on Ubuntu26.04.1 x86_64.
It requires the declared CPU features and system libraries. It contains no Qwen
weights, sports server, database, Joomla or desktop client and starts no service.

Read INSTALLATION.md and verify SHA256SUMS.txt. The Qwen profile pins an official
GGUF revision/hash; obtain weights separately. This is an unsigned development
component, not a new published DRAGONHYDRA release or complete workstation.

Actual model and R7 DynamicUser/API proofs used the identical reference ELF/library
bytes. Installed-prefix generation was not repeated. The offline namespace proof
and host-namespace API proof are reported separately. Restored model configuration
is unconfigured; match browsing remains available with deterministic fallback.
'''
    public={'ARTIFACT-MANIFEST.json':json_bytes(manifest),'BUILD-REPORT.json':json_bytes(build_report),
        'TEST-REPORT.json':json_bytes(tests),'MODEL-PROFILE.json':json_bytes(profile),
        'PAYLOAD-MANIFEST.json':(work/'PAYLOAD-MANIFEST.json').read_bytes(),
        'RUNTIME-LINKS.json':json_bytes({'schema_version':1,'upstream_link_manifest_sha256':LINKS_SHA,'links':link_manifest['links']}),
        'INSTALLATION.md':installation.encode(),'RELEASE-NOTES.md':notes.encode()}
    assert all(not (output/name).exists() for name in [*public,'SHA256SUMS.txt']),'Keep prior finalized metadata rather than overwriting it'
    for name,body in public.items():
        assert b'/mnt/c/' not in body and b'/home/love/' not in body and b'C:\\Users' not in body,'Unsanitized public metadata'
        (output/name).write_bytes(body)
    names=sorted([artifact.name,*public]);checksums=''.join(sha(output/name)+'  '+name+'\n' for name in names)
    (output/'SHA256SUMS.txt').write_text(checksums)
    receipt={'schema_version':1,'finalized_at':datetime.now(timezone.utc).isoformat(),'software_unchanged':sha(artifact)==report['artifact']['sha256'],
             'artifact':report['artifact'],'public_checksum_entries':len(names),'api_integration_verified_with_identical_reference_runtime':True,
             'public_files':[{'filename':name,'bytes':(output/name).stat().st_size,'sha256':sha(output/name)} for name in names]}
    (work/'PUBLIC-FINALIZATION.json').write_bytes(json_bytes(receipt));print(json.dumps(receipt,indent=2),flush=True)
    return 0


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work',type=Path,default=BASE/'package-r1')
    parser.add_argument('--output',type=Path,default=ROOT/'dist/linux/local-ai-20261031')
    parser.add_argument('--install-test',action='store_true',help='Install only after exact absent-prefix/package and installed-dependency preflight')
    parser.add_argument('--finalize-only',action='store_true',help='Write public metadata after saved package/install/API gates; never rebuild/reinstall')
    args=parser.parse_args();work=args.work.resolve();output=args.output.resolve()
    if args.finalize_only:
        if not work.is_relative_to(BASE) or work==BASE or not output.is_relative_to(ROOT/'dist/linux'):
            parser.error('Use the owned completed component build and distribution paths.')
        return finalize_public(work,output)
    if (platform.system()!='Linux' or platform.machine()!='x86_64' or work.exists()
            or not work.is_relative_to(BASE) or work==BASE or not output.is_relative_to(ROOT/'dist/linux')):
        parser.error('Use fresh project-owned native build paths.')
    if args.install_test and (os.geteuid()!=0 or os.readlink('/proc/self/ns/user')!=os.readlink('/proc/1/ns/user')):
        parser.error('Actual dpkg installation requires native host root, not mapped namespace root.')
    work.mkdir(parents=True);output.mkdir(parents=True,exist_ok=True)
    artifact=output/(NAME+'_'+VERSION+'_amd64.deb')
    if artifact.exists():parser.error('Retain existing artifact; replacement is not authorized.')
    report={'schema_version':1,'started_at':datetime.now(timezone.utc).isoformat(),'passed':False,
            'scope':'Optional native CPU inference-runtime package only; no GGUF, API server, Joomla, database, desktop or service autostart.',
            'commands':[],'checks':[],'BUILT':False,'EXTRACTED':False,'INSTALLED':False,'LAUNCH_TESTED':False,
            'CLEAN_MACHINE_TESTED':False,'model_rerun':False,'application_api_integration':'pending',
            'signing':'unsigned development Debian package','upstream_runtime_identity_sha256':IDENTITY_SHA,'version':VERSION}
    began=time.monotonic()
    def run(name,argv,timeout=60,allowed=(0,)):
        start=time.monotonic();result=subprocess.run(list(map(str,argv)),capture_output=True,text=True,timeout=timeout,
            env={**os.environ,'PATH':'/usr/sbin:/usr/bin:/sbin:/bin','LD_LIBRARY_PATH':''})
        (work/(name+'.stdout.log')).write_text(result.stdout);(work/(name+'.stderr.log')).write_text(result.stderr)
        report['commands'].append({'name':name,'argv':list(map(str,argv)),'exit_code':result.returncode,'seconds':round(time.monotonic()-start,3)})
        if result.returncode not in allowed:raise RuntimeError(name+' failed exit'+str(result.returncode))
        return result
    def check(name,**details):report['checks'].append({'name':name,'passed':True,**details});print(json.dumps({'passed':name,**details}),flush=True)
    try:
        identity_path=RUNTIME/'BUILD-IDENTITY.json';assert sha(identity_path)==IDENTITY_SHA
        link_path=BASE/'runtime-link-manifest.json';assert sha(link_path)==LINKS_SHA
        identity=json.loads(identity_path.read_text());manifest=json.loads(link_path.read_text());assert manifest['passed'] and manifest['links_count']==12
        source=json.loads((BASE/'build-r1/SOURCE-MANIFEST.json').read_text());source_files={i['path']:i for i in source['files']}
        offline=json.loads((BASE/'runtime-proof-r1/verification.json').read_text());assert offline['passed'] and offline['runner_reaped'] and offline['anonymous_key_closed']
        origin=json.loads((BASE/'MODEL-ORIGIN.json').read_text());assert origin['verified_local_file_matches_official_lfs_sha256'] and origin['sha256']==offline['model']['sha256']
        helper_path=Path(__file__).with_name('build_deb.py');helper_sha=sha(helper_path)
        spec=importlib.util.spec_from_file_location('dragonhydra_debian_archive_helpers',helper_path);helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
        prefix=PREFIX.relative_to('/').as_posix();files={};links={}
        for item in identity['runtime_files']:
            path=RUNTIME/item['path'];assert not path.is_symlink() and path.stat().st_size==item['bytes'] and sha(path)==item['sha256']
            files[prefix+'/'+item['path']]=(path.read_bytes(),0o755 if item['path']=='bin/llama-server' else 0o644)
        for item in manifest['links']:
            path=RUNTIME/item['path'];assert path.is_symlink() and os.readlink(path)==item['target'] and sha(path.resolve(strict=True))==item['resolved_sha256']
            assert path.resolve().is_relative_to(RUNTIME) and not PurePosixPath(item['target']).is_absolute() and '..' not in PurePosixPath(item['target']).parts
            links[prefix+'/'+item['path']]=item['target']
        # Preserve the actual small vendored source subtree, including inline
        # notices. Enumerate verified manifest entries, never guessed filenames.
        # These are documentation, not compiled/runtime additions or an audit.
        notice_inputs=[]
        notice_sources=sorted(name for name in source_files if name.startswith('vendor/'))
        assert notice_sources and len(notice_sources)<=100
        for name in notice_sources:
            item=source_files[name];path=BASE/'build-r1/source'/name
            assert path.is_file() and sha(path)==item['sha256'] and path.stat().st_size==item['bytes']
            files[prefix+'/notices/upstream-vendor/'+name]=(path.read_bytes(),0o644);notice_inputs.append(item)
        model_profile={key:origin[key] for key in ('repository','revision','filename','bytes','sha256','pinned_artifact_reference','gguf_format','quantization','chat_template_bytes','chat_template_sha256','verified_context_tokens','verified_compute_threads','verified_parallel_slots','verified_gpu_layers','observed_peak_rss_kib','kv_and_working_memory_measured_separately','benchmark_scope')}
        model_profile.update(schema_version=1,weights_bundled=False,automatic_download=False,credential_bundled=False,
                             runtime_contract='/completion with JSON schema; constrained supplied-fact selection')
        files[prefix+'/profiles/qwen3-4b-q4_k_m.json']=(json_bytes(model_profile),0o644)
        package_identity={'schema_version':1,'component':NAME,'component_version':VERSION,'architecture':'amd64',
            'upstream_build_identity_sha256':IDENTITY_SHA,'upstream_link_manifest_sha256':LINKS_SHA,
            'upstream_version':'0.7.0-dev','upstream_commit':source['commit'],'upstream_selected_source_content_sha256':source['content_sha256'],
            'compiler':'GNU15.2.0','tested_os':'Ubuntu26.04.1 x86_64/WSL2','required_cpu_flags':list(FEATURES),
            'os_dependencies':['libc6>=2.43','libstdc++6>=15.2','libgcc-s1','libgomp1'],
            'runtime_files':identity['runtime_files'],'relative_soname_links':manifest['links'],
            'supplemental_notice_sources':notice_inputs,'build_profile':'CPU only; GPU/UI/network-fetch/subprocess paths disabled',
            'offline_runtime_proof_sha256':sha(BASE/'runtime-proof-r1/verification.json'),
            'source_path':'<verified-upstream-source>','build_path':'<project-controlled-build>',
            'model_weights_included':False,'service_autostart':False,'signing':'unsigned development package'}
        files[prefix+'/BUILD-IDENTITY.json']=(json_bytes(package_identity),0o644)
        documentation=f'''# DRAGONHYDRA optional local-AI CPU runtime

Package `{NAME}` version `{VERSION}` contains llama-server and its seven private
libraries. It does not contain model weights, the sports API, Joomla, MariaDB,
desktop client, credentials, or a managed service. Installation starts nothing.

Tested target: Ubuntu26.04.1 x86_64/WSL2, GLIBC2.43, current GNU runtime libraries,
AVX/AVX2, FMA, F16C, SSE4.2 and BMI2. Other Linux versions/CPUs are unverified.
The pre-install script rejects missing CPU flags. Dependencies must already be
available; this package does not download or upgrade them.

```sh
sudo dpkg --install ./{artifact.name}
/opt/dragonhydra/local-ai/bin/llama-server --version
```

The complete runtime is under `/opt/dragonhydra/local-ai`; keep its SONAME links
and companion libraries. Standard OS libstdc++, libgcc, libgomp, libc/libm and the
ELF loader remain system dependencies. No developer Python, Node or GPU driver
is required by this CPU runtime. Normal package removal removes these binaries;
the package never owns or removes user model/data/configuration paths.

The supplied profile `profiles/qwen3-4b-q4_k_m.json` pins the existing verified
Qwen3-4B Q4_K_M GGUF to an official repository revision and SHA256. Obtain that
model separately and verify its hash; automatic acquisition is not implemented
by this runtime-only component. No key or machine-specific model path is bundled.
Use a protected API key file or the product's configured local-model integration.
Loopback-only invocation with the tested bounded CPU profile is:

```sh
/opt/dragonhydra/local-ai/bin/llama-server --model /path/to/verified/model.gguf \\
  --host 127.0.0.1 --port 18749 --offline --ctx-size 2048 \\
  --threads 4 --threads-batch 4 --parallel 1 --n-gpu-layers 0 \\
  --api-key-file /path/to/protected/key-file
```

The reference runtime passed eight network-isolated checks with one retained
football evidence package: 24.138s load, 27 generated tokens in15.518s, peak RSS
4539148KiB. This is one source-fact selection, not a general benchmark or a
promise of novel analysis. The model may select only a supplied fact and E1;
deterministic services retain probability arithmetic. KV/working memory were
not separately measured. This package reuses that exact ELF/library proof;
new extracted/installed binary and loader checks are reported separately.

Upstream dedicated notices and the actual vendored source notices are retained.
This unsigned development component is not a complete workstation installer.
'''
        files['usr/share/doc/'+NAME+'/README.md']=(documentation.encode(),0o644)
        controls={'control':(f'Package: {NAME}\nVersion: {VERSION}\nArchitecture: amd64\nMaintainer: DRAGONHYDRA Developers <developers@dragonhydra.invalid>\nSection: science\nPriority: optional\nDepends: libc6 (>= 2.43), libstdc++6 (>= 15.2), libgcc-s1, libgomp1\nInstalled-Size: {(sum(len(v[0]) for v in files.values())+1023)//1024}\nDescription: Optional DRAGONHYDRA CPU local-inference runtime\n Includes llama-server and private native libraries, without model weights.\n Requires AVX2/FMA/F16C/SSE4.2/BMI2; tested on Ubuntu26.04.1 only.\n No service or model starts during package installation.\n'.encode(),0o644),
                  'md5sums':(''.join(hashlib.md5(body).hexdigest()+'  '+name+'\n' for name,(body,_) in sorted(files.items())).encode(),0o644),
                  'preinst':(PREINST.encode(),0o755)}
        body=b'!<arch>\n'+helper.ar_member('debian-binary',b'2.0\n')+helper.ar_member('control.tar.xz',tar_bytes(controls,{},helper.EPOCH))+helper.ar_member('data.tar.xz',tar_bytes(files,links,helper.EPOCH))
        artifact.write_bytes(body);report['BUILT']=True
        report['artifact']={'filename':artifact.name,'bytes':len(body),'sha256':sha(artifact)}
        report['input_provenance']={'runtime_identity_sha256':IDENTITY_SHA,'link_manifest_sha256':LINKS_SHA,'archive_helper_sha256':helper_sha,
                                    'model_origin_sha256':sha(BASE/'MODEL-ORIGIN.json'),'package_script_sha256':sha(__file__),
                                    'supplemental_notice_sources':notice_inputs}
        payload=[{'path':name,'bytes':len(body),'sha256':hashlib.sha256(body).hexdigest(),'mode':oct(mode),'uid':0,'gid':0,'kind':'regular'} for name,(body,mode) in sorted(files.items())]
        payload.extend({'path':name,'target':target,'kind':'symlink','mode':'0o777','uid':0,'gid':0} for name,target in sorted(links.items()))
        (work/'PAYLOAD-MANIFEST.json').write_bytes(json_bytes({'schema_version':1,'files':payload}))
        run('dpkg-info',['dpkg-deb','--info',artifact]);run('dpkg-contents',['dpkg-deb','--contents',artifact])
        # Re-read actual package bytes through Debian's native tar extraction.
        native=subprocess.run(['dpkg-deb','--fsys-tarfile',str(artifact)],capture_output=True,check=True)
        with tarfile.open(fileobj=io.BytesIO(native.stdout),mode='r:') as archive:
            measured={m.name.removeprefix('./'):m for m in archive if not m.isdir()}
            assert set(measured)==set(files)|set(links)
            for name,item in measured.items():
                assert item.uid==item.gid==0
                if name in links:assert item.issym() and item.linkname==links[name] and item.mode==0o777
                else:assert item.isfile() and item.mode==files[name][1] and archive.extractfile(item).read()==files[name][0]
        check('Actual Debian bytes have exact allowlist, root modes, preserved aliases and no model/cache/credentials',regular_files=len(files),links=len(links))
        extracted=work/'extracted';run('extract',['dpkg-deb','--extract',artifact,extracted])
        control_dir=work/'control';run('controls',['dpkg-deb','--control',artifact,control_dir]);run('preinst-syntax',['/bin/sh','-n',control_dir/'preinst'])
        report['EXTRACTED']=True
        def validate_runtime(name,prefix,native_modes=False):
            for relative,(expected_body,mode) in files.items():
                if not relative.startswith(str(PREFIX).lstrip('/')+'/'):continue
                path=prefix/relative.removeprefix(str(PREFIX).lstrip('/')+'/')
                assert path.read_bytes()==expected_body and not path.is_symlink()
                if native_modes:assert path.stat().st_uid==path.stat().st_gid==0 and path.stat().st_mode&0o777==mode
            for relative,target in links.items():
                path=prefix/relative.removeprefix(str(PREFIX).lstrip('/')+'/');assert path.is_symlink() and os.readlink(path)==target and path.resolve().is_relative_to(prefix)
            version=run(name+'-version',[prefix/'bin/llama-server','--version']).stdout
            # Native version is printed on stderr in this upstream build.
            if not version:version=(work/(name+'-version.stderr.log')).read_text()
            assert '2280f0fd163b03d4331d49e08460f66502e35854' in version
            run(name+'-help',[prefix/'bin/llama-server','--help'])
            dependencies=run(name+'-ldd',['ldd',prefix/'bin/llama-server']).stdout
            assert 'not found' not in dependencies
            for line in dependencies.splitlines():
                if any(token in line for token in ('libllama','libggml','libmtmd')):
                    assert str(prefix/'bin') in line,'Private library resolved outside tested prefix'
            dynamic=run(name+'-runpath',['readelf','-d',prefix/'bin/llama-server']).stdout
            assert '$ORIGIN' in dynamic
            report['LAUNCH_TESTED']=True
        validate_runtime('extracted',extracted/str(PREFIX).lstrip('/'))
        check('Extracted complete runtime executes version/help and resolves all private libraries in its own prefix')
        assert sha(identity_path)==IDENTITY_SHA and sha(link_path)==LINKS_SHA and sha(helper_path)==helper_sha
        if args.install_test:
            status=run('preflight-package',['dpkg-query','-W','-f=${Status}',NAME],allowed=(0,1))
            assert status.returncode==1 and not PREFIX.exists() and not PREFIX.is_symlink(),'Optional product prefix/package already exists; refusing replacement'
            versions=run('preflight-dependencies',['dpkg-query','-W','-f=${Package} ${Version}\n','libc6','libstdc++6','libgcc-s1','libgomp1']).stdout
            version_map=dict(line.split(' ',1) for line in versions.splitlines())
            run('check-libc-version',['dpkg','--compare-versions',version_map['libc6'],'ge','2.43'])
            run('check-libstdcxx-version',['dpkg','--compare-versions',version_map['libstdc++6'],'ge','15.2'])
            report['install_preflight']={'package_absent':True,'prefix_absent':True,'dependencies_already_installed':version_map,'no_dependency_download':True}
            run('native-dpkg-install-once',['dpkg','--install',artifact],timeout=90)
            report['INSTALLED']=True
            validate_runtime('installed',PREFIX,native_modes=True)
            run('installed-package-version',['dpkg-query','-W','-f=${Status}\n${Version}',NAME])
            check('Actual isolated optional component installs once and all native root-owned ELF/aliases/notices verify; no service started')
        report['offline_model_proof_reused']={'passed':True,'checks':len(offline['checks']),'proof_sha256':sha(BASE/'runtime-proof-r1/verification.json'),
                                              'binary_sha256':identity['binary']['sha256'],'model_sha256':origin['sha256'],
                                              'scope':'Exact unmodified ELF/library bytes; source-fact selection proof only. No model weights bundled or inference rerun.'}
        report['model_profile']=model_profile
        report['passed']=True
    except Exception as error:
        report['error']={'type':type(error).__name__,'message':str(error),'line':traceback.extract_tb(error.__traceback__)[-1].lineno}
        (work/'traceback.log').write_text(traceback.format_exc())
    finally:
        report.update(finished_at=datetime.now(timezone.utc).isoformat(),seconds=round(time.monotonic()-began,3))
        (work/'BUILD-REPORT.json').write_bytes(json_bytes(report))
        print(json.dumps({'passed':report['passed'],'artifact':report.get('artifact'),'BUILT':report['BUILT'],'EXTRACTED':report['EXTRACTED'],
                          'INSTALLED':report['INSTALLED'],'error':report.get('error'),'evidence':(work/'BUILD-REPORT.json').relative_to(ROOT).as_posix()}),flush=True)
    return 0 if report['passed'] else 1


if __name__=='__main__':
    raise SystemExit(main())
