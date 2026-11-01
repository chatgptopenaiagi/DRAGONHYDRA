"""Assemble explicit GENESIS A9 asset provenance and checksums, without publishing.

This complements the existing release coordinator for a consolidation containing
independently versioned, earlier verified binaries. Unknown files fail closed.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from zipfile import ZipFile
import tarfile

S1='4a08f873429e338d30031be321a0c63ccfe196a7'
S2='46ba85c091230213189ffed679294b80019841a2'
DESKTOP='5821b4d54a199f73ccd943215117dcfa8e38ea4b'
JOOMLA='55997de0a3997a10d12c6271795289a5d147e1ab'
LINUX='2ca96e94213cc6f516b6963052ef68ff1948af94'
RUNTIME_CONTENT='886161d0a8c4f0bf3364fd6d0a9966630398bba6bfe27b84de9c5999a307acd4'

def digest(path):
    with path.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--assets',type=Path,required=True);p.add_argument('--source-sha',required=True);a=p.parse_args()
    assert re.fullmatch('[a-f0-9]{40}',a.source_sha)
    defs={}
    def item(name,platform,version,source,mode,dependencies,install,tests,limits,**extra):
        defs[name]=dict(platform=platform,version=version,source_commit=source,build_configuration=mode,dependencies=dependencies,installation=install,test_results=tests,known_limitations=limits,**extra)
    item('DRAGONHYDRA-GENESIS-A9-Workstation-win-x64-Setup.exe','Windows x64','0.4.1-dev.1',S1,'RepackageOnly; explicit verified Joomla frontend ZIP; unchanged A8 desktop and A6 server',['Windows10+ x64 declared; Windows11 x64 observed','.NET Framework4.8','WebView2 (bootstrapper online if absent)'],'Run Setup, retain matching data/service identity on upgrade; official launcher pairs corresponding local server',['10662 payload entries inspected','Full isolated current-host upgrade exit0:6guards','6genuine site/admin HTTP checks;760retained; pairing/config/ports preserved;3unrelated PIDs unchanged'],['Unsigned','No clean-machine/OS reboot or new native-client UI run'],component_sources={'joomla':JOOMLA,'desktop':DESKTOP,'server':{'embedded_source_commit':None,'scoped_content_sha256':RUNTIME_CONTENT}},signing='unsigned')
    item('DRAGONHYDRA-0.4.0-alpha.1-Desktop-win-x64.exe','Windows x64','0.4.0-alpha.1',DESKTOP,'Immutable existing Tauri2 release executable',['WebView2','Paired DRAGONHYDRA server'],'Use matching workstation launcher or local connection/pairing screen',['Current SHA equality','Earlier A8 native links, bare-launch pairing, navigation/exports/restart acceptance'],['Earlier native UI evidence not rerun for A9','Unsigned; standalone EXE does not install backend'],signing='unsigned',source_content_sha256='2c6b0607cf7d1638787f6858a29258eac1a8bd89b20c437afcba8e8ee9beeae4')
    for suffix in ('BUILD-INFO.json','NOTICES.txt','README.txt'):
        item('DRAGONHYDRA-0.4.0-alpha.1-Desktop-win-x64-'+suffix,'Windows desktop support','0.4.0-alpha.1',DESKTOP,'Unchanged adjacent support file',[],'Keep alongside standalone EXE',['Content SHA verified'],['Companion file, not executable'])
    item('DRAGONHYDRA-0.4.0-alpha.1-Android-arm64-development.apk','Android arm64-v8a','0.4.0-alpha.1+4',S1,'Flutter release-optimized; non-debuggable; SDK36',['Android API24+','Owner-provided trusted backend URL/pairing'],'Sideload through owner-authorized Android workflow; configure own endpoint',['Flutter analyze0issues;14testsPASS','APK identity/signature/ABI verified','Fresh emulator install Success; cold launch Statusok; Home rendered'],['Established AndroidDebug development certificate; not production publisher signed','Pairing BLOCKED by user-stopped UI; connected navigation/upgrade/persistence NOT_RUN','Observed emulator is API37 x86_64 with ARM64 translation, not physical ARM64 acceptance'],signing='development certificate SHA256 d77e623706f0146bc495904affe310cb492d67277ecf70b28455d1f5e138e419')
    item('pkg_dragonhydra-0.4.1-dev.2.zip','Joomla6 / PHP8.3+','0.4.1-dev.2',JOOMLA,'Native site/admin/API package + Cassiopeia child template',['Joomla6','PHP8.3+ curl','Associated Python API and protected matching bridge file'],'Joomla extension installer; workstation provisions endpoint/bridge; separate site login',['Primary existing Joomla6.2 upgrade/reapply idempotent','17frontend requirements;7isolated states;semantic menus7regressions','New installer-profile genuine site/admin/retained-match checks'],['Unsigned development extension','No arbitrary external proxy','Formal screen-reader/main-landmark audit pending'],signing='unsigned')
    item('DRAGONHYDRA-0.4.0-alpha.1-Server-win-x64.zip','Windows x64','0.4.0-alpha.1',None,'Existing immutable frozen A6 payload710files plus external startup/provenance docs',['Windows x64; Python runtime bundled'],'Extract all files; follow included README-STARTUP.txt; run DRAGONHYDRA-Server-x64/DRAGONHYDRA-Server.exe with private dedicated --state and --port',['All710payload files and ZIP members rehashed','Fresh6groupsPASS;owned-state restart5groupsPASS;760retained and XLSX preserved'],['Original snapshot did not embed Git SHA; scoped source content is authoritative','No Joomla/web stack in standalone server ZIP'],source_content_sha256=RUNTIME_CONTENT,source_compatibility='68source inputs/61product Python files byte-identical to current source',signing='unsigned')
    for name,mode in [('dragonhydra-0.4.0a1-py3-none-any.whl','uv_build0.12.7 wheel'),('dragonhydra-0.4.0a1.tar.gz','uv_build0.12.7 source distribution')]:
        item(name,'Python3.14','0.4.0a1',S2,mode,['Python>=3.14,<3.15','server extra; public pinned lock'],'Install wheel[server] in isolated venv; dragonhydra-server --state <private-dir> --port <unused-port> --init-bridge',['Fresh isolated install; pipcheck;CLI and API checks','Fresh runtime + owned restart; sdist rebuild verified (see RUNTIME-BUILD-REPORT)'],['No interpreter bundled','No new Linux runtime proof for this newly generated metadata wheel'],source_content_sha256=RUNTIME_CONTENT,signing='not digitally signed')
    item('dragonhydra-linux-dev-8f170de1559b.tar.gz','Linux server preparation / Python3.14','GENESIS A7 / Python0.4.0a1',LINUX,'Reused immutable verified A7 archive; not rebuilt or renamed',['Linux Python3.14 and matching server dependencies'],'Read preflight.py/install.sh; use new private prefix/state; explicit --apply',['Current archive hash +61product source files byte-identical','Earlier Docker Linux runtime12retained+7fresh and installer dependency gates10'],['No new A9 Linux run','No native WSL, desktop, DEB/RPM/AppImage, systemd/reboot acceptance','Contained historical wheel differs from new A9 wheel metadata'],source_content_sha256='8f170de1559b135cba73ecc5b12dda4d4cfdd94616136532e6e2a7649de15e3c',signing='not digitally signed')
    item('DRAGONHYDRA-GENESIS-A9-Source.zip','All supported source','GENESIS A9',a.source_sha,'git archive exact release commit',[],'Extract; follow platform build instructions and public dependency lock',['Git tree path/content equality','Archive privacy scan; no runtime state'],['Runtime binaries/dependencies downloaded separately'],signing='Git tag identity; no signing claim')
    metadata=('README-INSTALL.txt','ANDROID-BUILD-REPORT.json','WINDOWS-BUILD-REPORT.json','RUNTIME-BUILD-REPORT.json','JOOMLA-FRONTEND-REPORT.md','GENESIS-A9-RELEASE-NOTES.md','TEST-REPORT.json')
    for name in metadata:item(name,'Documentation/evidence','GENESIS A9',a.source_sha,'Sanitized report snapshot',[],'Read alongside release manifest',['Known-secret content scan'],['Build-time reports retain prepublication flags; remote receipt is separate'])
    actual={p.name for p in a.assets.iterdir() if p.is_file()}-{'RELEASE-MANIFEST.json','SHA256SUMS.txt'}
    assert actual==set(defs),f'Explicit asset set differs: missing={set(defs)-actual};unknown={actual-set(defs)}'
    manifest={'schema_version':1,'repository':'chatgptopenaiagi/DRAGONHYDRA','release':'DRAGONHYDRA GENESIS A9','tag':'genesis-a9-20261101','classification':'development prerelease','source_commit':a.source_sha,'assembled_at':datetime.now(timezone.utc).isoformat(),'version_policy':'Independent original component versions retained; milestone filename does not alter embedded versions. Null source SHA records original content-addressed snapshot honestly.','assets':[]}
    for name,info in sorted(defs.items()):
        path=a.assets/name;assert path.stat().st_size>0 and path.stat().st_size<2*1024**3
        if path.suffix in ('.zip','.apk','.whl'):
            with ZipFile(path) as z:assert z.testzip() is None and len(z.infolist())>0
        elif path.name.endswith('.tar.gz'):
            with tarfile.open(path) as z:assert len(z.getmembers())>0
        info.update(name=name,bytes=path.stat().st_size,sha256=digest(path),artifact_prepared_at=datetime.fromtimestamp(path.stat().st_mtime,timezone.utc).isoformat(),build_timestamp_utc=None,build_timestamp_note='Actual lane command/build timestamps are retained in associated platform report; artifact_prepared_at is not asserted as compiler time',download_url='https://github.com/chatgptopenaiagi/DRAGONHYDRA/releases/download/genesis-a9-20261101/'+name)
        manifest['assets'].append(info)
    (a.assets/'RELEASE-MANIFEST.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    lines=[digest(p)+'  '+p.name for p in sorted(a.assets.iterdir()) if p.is_file() and p.name!='SHA256SUMS.txt']
    (a.assets/'SHA256SUMS.txt').write_text('\n'.join(lines)+'\n',encoding='ascii')
    print(json.dumps({'passed':True,'payload_and_report_assets':len(defs),'download_assets':len(defs)+2,'source_commit':a.source_sha}))
if __name__=='__main__':main()
