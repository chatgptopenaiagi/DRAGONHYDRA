"""Read-only metadata for the exact installed R7 service's network context.

No service/environment secrets are read, no service controls are invoked and
no provider request is performed by the metadata stage.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

ROOT = Path(__file__).resolve().parents[2]
UNIT = 'dragonhydra-api.service'
CHILD = r'''
import json,os,ssl,stat
from pathlib import Path
def error(exc):
    return {'type':type(exc).__name__,'errno':getattr(exc,'errno',None),'message':str(exc)}
def item(name):
    p=Path(name); result={'path':name}
    try:
        s=p.stat();result.update(mode=oct(stat.S_IMODE(s.st_mode)),uid=s.st_uid,gid=s.st_gid,resolved=str(p.resolve()))
        if p.is_file():
            fd=os.open(p,os.O_RDONLY);os.close(fd);result['readable']=True
        elif p.is_dir():
            result['searchable']=os.access(p,os.X_OK)
    except OSError as exc: result['error']=error(exc)
    return result
v=ssl.get_default_verify_paths()
paths=['/etc/resolv.conf','/mnt/wsl/resolv.conf','/etc/nsswitch.conf','/etc/hosts','/etc/ssl/certs/ca-certificates.crt']
paths+= [x for x in (v.cafile,v.capath,v.openssl_cafile,v.openssl_capath) if x and x not in paths]
report={'uid':os.getuid(),'euid':os.geteuid(),'gid':os.getgid(),'groups':os.getgroups(),
 'namespaces':{name:os.readlink('/proc/self/ns/'+name) for name in ('mnt','net','user','cgroup')},
 'profile':Path('/proc/self/attr/current').read_text().strip(),
 'paths':[item(name) for name in paths],
 'environment_presence_only':{'http_proxy':('http_proxy' in os.environ or 'HTTP_PROXY' in os.environ),
 'https_proxy':('https_proxy' in os.environ or 'HTTPS_PROXY' in os.environ),
 'no_proxy':('no_proxy' in os.environ or 'NO_PROXY' in os.environ),
 'ssl_cert_file':('SSL_CERT_FILE' in os.environ),'ssl_cert_dir':('SSL_CERT_DIR' in os.environ)}}
try:
    ctx=ssl.create_default_context()
    report['default_ssl_context']={'check_hostname':ctx.check_hostname,'verify_mode':int(ctx.verify_mode),'cert_store_stats':ctx.cert_store_stats()}
except (OSError,ssl.SSLError) as exc:report['default_ssl_context_error']=error(exc)
print(json.dumps(report))
'''
HTTP = r'''
import hashlib,json,os,sys,time
from urllib.request import Request,build_opener
from urllib.error import HTTPError,URLError
sys.path.insert(0,'/opt/dragonhydra/api/site-packages')
from dragonhydra.connectors.core import SafeRedirect,validate_url
url='https://www.football-data.co.uk/mmz4281/2526/E0.csv'
validate_url(url)
report={'url':url,'uid':os.geteuid(),'gid':os.getegid(),'timeout_seconds':8,'maximum_body_bytes':1024,
 'opener':'build_opener(SafeRedirect()), same as installed Transport; default proxy/TLS behavior retained',
 'user_agent':'DRAGONHYDRA/0.4 public-dataset-adapter',
 'extra_header':'Range: bytes=0-1023','provider_get_requests':1}
begun=time.monotonic()
try:
    request=Request(url,headers={'User-Agent':report['user_agent'],'Range':'bytes=0-1023'})
    try:response=build_opener(SafeRedirect()).open(request,timeout=8)
    except HTTPError as exc:response=exc
    with response:
        payload=response.read(1024)
        report.update(http_status=response.getcode(),resolved_url=response.geturl(),bytes_read=len(payload),
                      prefix_sha256=hashlib.sha256(payload).hexdigest(),content_type=response.headers.get_content_type())
except BaseException as exc:
    chain=[]
    current=exc
    for _ in range(5):
        chain.append({'type':type(current).__name__,'errno':getattr(current,'errno',None),
                      'message':str(current),'verify_code':getattr(current,'verify_code',None),
                      'verify_message':getattr(current,'verify_message',None)})
        nested=getattr(current,'reason',None) if isinstance(current,URLError) else None
        current=nested if isinstance(nested,BaseException) else current.__cause__
        if current is None:break
    report['underlying_exception_chain']=chain
report['seconds']=round(time.monotonic()-begun,3)
print(json.dumps(report))
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work', required=True, type=Path)
    parser.add_argument('--http-prefix', action='store_true', help='At most2GET prefix probes after metadata: same public URL as root and service-context credentials')
    args = parser.parse_args()
    work = args.work.resolve()
    if os.getuid() != 0 or work.exists() or not work.is_relative_to(ROOT/'build/linux/native-kernel-20261031/service-network-probe-7'):
        raise SystemExit('Linux root and fresh exact owned evidence required')
    work.mkdir(parents=True)
    (work/'harness-source.py').write_bytes(Path(__file__).read_bytes())
    report = {'passed': False,'commands':[],'provider_get_requests':0,
              'scope':'Read-only exact-service network/mount/UID metadata; diagnostic child is not placed in service cgroup and does not inherit its seccomp filter or environment',
              'harness_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    def run(name,argv,timeout=20):
        begun=time.monotonic()
        child=subprocess.run(argv,capture_output=True,text=True,timeout=timeout)
        (work/(name+'.stdout.log')).write_text(child.stdout)
        (work/(name+'.stderr.log')).write_text(child.stderr)
        report['commands'].append({'name':name,'argv':argv,'exit_code':child.returncode,'seconds':round(time.monotonic()-begun,3)})
        if child.returncode:raise RuntimeError(name+' failed; inspect bounded log')
        return child.stdout
    try:
        identity=json.loads(Path('/opt/dragonhydra/api/BUILD-IDENTITY.json').read_text())
        if identity['source_content_sha256']!='4a2b97baec4fc278bc405a99a1d970f66e030be77b63d5f043f0faf295b39bc0':
            raise RuntimeError('Exact installed R7 identity differs')
        props=['MainPID','ActiveState','FragmentPath','ExecStart','DynamicUser','PrivateNetwork','PrivateUsers',
               'RestrictAddressFamilies','IPAddressDeny','IPAddressAllow','NetworkNamespacePath','RestrictNetworkInterfaces',
               'SocketBindAllow','SocketBindDeny','PrivateMounts','ProtectSystem','ProtectHome','AppArmorProfile',
               'SELinuxContext','NoNewPrivileges','SystemCallFilter','SystemCallErrorNumber','ControlGroup']
        raw=run('unit-effective-properties',['systemctl','show',UNIT]+[arg for name in props for arg in ('-p',name)])
        unit=dict(line.split('=',1) for line in raw.splitlines() if '=' in line)
        if (unit.get('ActiveState')!='active' or unit.get('FragmentPath')!='/usr/lib/systemd/system/'+UNIT or unit.get('DynamicUser')!='yes'
            or '/opt/dragonhydra/api/bin/dragonhydra-server' not in unit.get('ExecStart','') or '--state /var/lib/dragonhydra-api' not in unit.get('ExecStart','')):
            raise RuntimeError('Exact owned active unit guard failed')
        pid=int(unit['MainPID']);status=Path('/proc/'+str(pid)+'/status').read_text()
        selected={line.split(':',1)[0]:line.split(':',1)[1].strip() for line in status.splitlines()
                  if line.split(':',1)[0] in ('Uid','Gid','Groups','CapEff','CapBnd','NoNewPrivs','Seccomp','Seccomp_filters')}
        uid=int(selected['Uid'].split()[1]);gid=int(selected['Gid'].split()[1]);groups=selected['Groups'].split()
        report['actual_service']={'unit':unit,'process_status':selected,'profile':Path('/proc/'+str(pid)+'/attr/current').read_text().strip(),
            'namespaces':{name:os.readlink('/proc/'+str(pid)+'/ns/'+name) for name in ('mnt','net','user','cgroup')}}
        tools={name:shutil.which(name) for name in ('nsenter','setpriv')}
        if tools!={'nsenter':'/usr/bin/nsenter','setpriv':'/usr/bin/setpriv'}:raise RuntimeError('Expected existing native namespace/credential tools unavailable')
        for name,flags in (('nsenter',('--target','--mount','--net')),('setpriv',('--reuid','--regid','--groups','--clear-groups','--no-new-privs'))):
            help_text=run(name+'-existing-help',[tools[name],'--help'])
            if not all(flag in help_text for flag in flags):raise RuntimeError('Required existing tool flags not verified')
        root=json.loads(run('root-metadata',['/usr/bin/python3','-I','-B','-c',CHILD]))
        credentials=['--groups',','.join(groups)] if groups else ['--clear-groups']
        argv=['/usr/bin/nsenter','--target',str(pid),'--mount','--net','--','/usr/bin/setpriv','--reuid',str(uid),'--regid',str(gid),
              *credentials,'--no-new-privs','/usr/bin/python3','-I','-B','-c',CHILD]
        service=json.loads(run('service-context-metadata',argv))
        report['root_metadata']=root;report['service_context_metadata']=service
        if service['euid']!=uid or service['gid']!=gid or any(service['namespaces'][name]!=report['actual_service']['namespaces'][name] for name in ('mnt','net')):
            raise RuntimeError('Diagnostic child did not match exact service credentials/mount/net namespaces')
        report['matched']={'uid':True,'gid':True,'mount_namespace':True,'network_namespace':True,
                           'service_cgroup':False,'service_seccomp_filter':False,'service_environment_read':False}
        if args.http_prefix:
            permission_denials=[item for item in service['paths'] if item.get('error',{}).get('errno') in (1,13)]
            if permission_denials or service.get('default_ssl_context_error'):
                report['http_skipped_for_metadata_cause']={'permission_denials':permission_denials,
                    'ssl_context_error':service.get('default_ssl_context_error')}
            else:
                report['provider_get_requests']=2
                report['root_http']=json.loads(run('root-http-prefix',['/usr/bin/python3','-I','-B','-c',HTTP]))
                service_http_argv=argv[:-1]+[HTTP]
                report['service_context_http']=json.loads(run('service-http-prefix',service_http_argv))
        report['passed']=True
    except BaseException as error:
        report['error']={'type':type(error).__name__,'message':str(error)}
    (work/'verification.json').write_text(json.dumps(report,indent=2)+'\n')
    keys=('passed','error','root_http','service_context_http','http_skipped_for_metadata_cause','matched') if args.http_prefix else ('passed','error','actual_service','root_metadata','service_context_metadata','matched')
    print(json.dumps({key:report.get(key) for key in keys},indent=2))
    return 0 if report['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
