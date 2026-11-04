# Vendored audited test support; original body SHA256 47d5ffc472bbb0675ab8942c77fccb14e9a780e8f40acff2e397fe5e1c197f0b.
# Original LAB evidence is immutable. Only this provenance header and disabled direct entry differ.
"""Pinned dev5 disposable-only acceptance. Only its external driver owns service/Setup actions; prepared, never implicit execution."""
import argparse
from contextlib import closing
from datetime import datetime,timezone
import hashlib
from html.parser import HTMLParser
import http.cookiejar
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import time
import traceback
import uuid
from urllib.parse import urlencode,urljoin,urlsplit,parse_qs
from urllib.request import Request,build_opener,ProxyHandler,HTTPCookieProcessor,HTTPRedirectHandler
from urllib.error import HTTPError

LAB=Path('C:/xampp/DRAGONHYDRA-CORE-NEXT-LAB')
FRESH='core-next-b447d99ab9524197af09c235077685de'
SOURCE='ed78fab282599a181d4254ab65a2fc2eaa5b7f50'
SETUP='8d5a790ac54b4cca3c51d08746db80a5551c211474bcdead7dc86a44b3a8e553'
VERSION='0.5.0-dev.5'
TARGET='de2c0fb3d3215eb157292f0941def2d44aa520a79db77dc73e40d13f88014aea'
KEY='core-next-dev5-disposable-b447d99a-ed78fab'
PORTS={FRESH:{'api':18860,'web':18861,'database':18862}}
OPERATION=LAB/'continuation-20261102/disposable-dev5-lifecycle-r1'
PROFILE=LAB/'profiles'/FRESH/'installation-profile.json'
EXPECTED_SETUP=LAB/'dist/workstation-dev5-r1/DRAGONHYDRA-CORE-NEXT-0.5.0-dev.5-Workstation-win-x64-Setup.exe'
SCHEMA='dev5.disposable-acceptance/1'
PROFILE_HELPER_SHA256='4ff8676621b3e3662cc10d4de91345cf09d132215bf78f0b8a5c597e9cd7e27b'
PHASES={
    'read-fresh':('fresh',None),
    'workflow':('workflow','read-fresh'),
    'backup-readback':('readback','workflow'),
    'restart-readback':('readback','backup-readback'),
    'repair-readback':('readback','restart-readback'),
    'uninstalled-readback':('uninstalled','repair-readback'),
    'reinstall-readback':('readback','uninstalled-readback'),
    'final-uninstalled-readback':('uninstalled','reinstall-readback'),
}
PWSH='C:/Program Files/PowerShell/7/pwsh.exe'
PHP_PRESENTATION=r'''
try {
    $input=json_decode(stream_get_contents(STDIN),true,32,JSON_THROW_ON_ERROR);
    if(!extension_loaded('pdo_mysql')){throw new RuntimeException('PDO_DRIVER_UNAVAILABLE');}
    require $input['configuration'];
    $configuration=new JConfig();
    if((string)$configuration->host!==('127.0.0.1:'.$input['port'])
        || (string)$configuration->db!==$input['schema']
        || (string)$configuration->user!==$input['user']
        || !preg_match('/^[A-Za-z][A-Za-z0-9_]{0,30}$/D',(string)$configuration->dbprefix)
        || !preg_match('/^[A-Za-z_][A-Za-z0-9_]{0,63}$/D',(string)$configuration->db)){
        throw new RuntimeException('JOOMLA_DATABASE_BINDING_MISMATCH');
    }
    $prefix=(string)$configuration->dbprefix;
    $pdo=new PDO('mysql:host=127.0.0.1;port='.$input['port'].';dbname='.$configuration->db.';charset=utf8mb4',
        $configuration->user,$configuration->password,
        [PDO::ATTR_ERRMODE=>PDO::ERRMODE_EXCEPTION,PDO::ATTR_EMULATE_PREPARES=>false,
         PDO::ATTR_DEFAULT_FETCH_MODE=>PDO::FETCH_ASSOC,PDO::ATTR_TIMEOUT=>5]);
    $pdo->exec('SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ');
    $pdo->exec('START TRANSACTION WITH CONSISTENT SNAPSHOT, READ ONLY');
    $quote=static fn(string $table):string=>chr(96).$prefix.$table.chr(96);
    $tables=['menu','modules','modules_menu','template_styles','content'];
    $engine=$pdo->prepare('SELECT ENGINE FROM information_schema.TABLES WHERE TABLE_SCHEMA=? AND TABLE_NAME=?');
    foreach($tables as $table){
        $engine->execute([$configuration->db,$prefix.$table]);
        if(strtoupper((string)$engine->fetchColumn())!=='INNODB'){throw new RuntimeException('INNODB_SNAPSHOT_REQUIRED');}
    }
    $queries=[
        'site_menus'=>'SELECT * FROM '.$quote('menu').' WHERE client_id=0 ORDER BY id',
        'site_modules'=>'SELECT * FROM '.$quote('modules').' WHERE client_id=0 ORDER BY id',
        'site_module_assignments'=>'SELECT mm.* FROM '.$quote('modules_menu').' mm JOIN '.$quote('modules').' m ON m.id=mm.moduleid WHERE m.client_id=0 ORDER BY mm.moduleid,mm.menuid',
        'site_template_styles'=>'SELECT * FROM '.$quote('template_styles').' WHERE client_id=0 ORDER BY id',
        'articles'=>'SELECT * FROM '.$quote('content').' ORDER BY id',
        'administrator_component_menu_semantics'=>"SELECT title,alias,link,type,published,access,language,client_id FROM ".$quote('menu')." WHERE client_id=1 AND link LIKE 'index.php?option=com_dragonhydra%' ORDER BY title,alias,link"
    ];
    $omit=['checked_out','checked_out_time','hits','lft','rgt'];
    $jsonColumns=['params','metadata','attribs','images','urls'];
    $fingerprints=[];
    foreach($queries as $name=>$sql){
        $statement=$pdo->query($sql);$hash=hash_init('sha256');$count=0;
        while($row=$statement->fetch()){
            if(++$count>50000){throw new RuntimeException('PRESENTATION_ROW_BOUND');}
            foreach($omit as $column){unset($row[$column]);}
            foreach($jsonColumns as $column){
                if(isset($row[$column])&&is_string($row[$column])){
                    $value=json_decode($row[$column],true);
                    if(is_array($value)){
                        $normalize=function(&$node)use(&$normalize){if(!is_array($node)){return;}
                            foreach($node as &$item){$normalize($item);}unset($item);
                            if(!array_is_list($node)){ksort($node,SORT_STRING);}};
                        $normalize($value);$row[$column]=$value;
                    }
                }
            }
            ksort($row,SORT_STRING);
            hash_update($hash,json_encode($row,JSON_UNESCAPED_SLASHES|JSON_UNESCAPED_UNICODE|JSON_THROW_ON_ERROR)."\n");
        }
        $fingerprints[$name]=['rows'=>$count,'sha256'=>hash_final($hash)];
    }
    $pdo->exec('ROLLBACK');
    echo json_encode(['passed'=>true,'schema_version'=>'joomla.presentation-fingerprint/1',
        'read_only'=>true,'consistent_snapshot'=>true,'table_prefix'=>$prefix,'fingerprints'=>$fingerprints,
        'excluded_volatile_columns'=>$omit,'scope'=>'Site menus/modules/assignments/styles/articles; administrator component menu semantics exclude regenerated IDs. No content or credential values returned.'],JSON_THROW_ON_ERROR);
} catch(Throwable $error) {
    if(isset($pdo)&&$pdo->inTransaction()){$pdo->rollBack();}
    echo '{"passed":false,"code":"JOOMLA_READONLY_FINGERPRINT_FAILED"}';exit(7);
}
'''

class GateError(Exception):pass
def gate(value,code):
    if not value:raise GateError(code)
def utc():return datetime.now(timezone.utc).isoformat()
def sha(raw):return hashlib.sha256(raw).hexdigest()
def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()
def digest(path):return sha(Path(path).read_bytes())

def guard_profile(path,profile):
    gate(Path(path)==PROFILE and isinstance(profile,dict),'PINNED_DISPOSABLE_PROFILE_REQUIRED')
    root=LAB/'profiles'/FRESH;suffix=FRESH[-12:]
    expected={'schema_version':1,'product':'DRAGONHYDRA CORE NEXT','edition':'CORE NEXT','installation_id':FRESH,
        'environment_id':'candidate','lab_root':str(LAB),'install_root':str(root/'application'),'state_root':str(root/'state'),
        'browser_user_data':str(root/'browser'),'service_name':'DragonhydraCoreNextcandidate'+suffix,
        'cookie_name':'dhcn_'+suffix,'joomla_session_suffix':FRESH,'source_commit':SOURCE,'version':VERSION,
        'build_id':'package-dev5-r1','copy_credentials':False,'provider_schedules':'disabled','api_namespace':'/dragon/api/v1','kernel_schema_version':1}
    for key,value in expected.items():
        actual=profile.get(key)
        if key.endswith('_root') or key=='browser_user_data':gate(isinstance(actual,str) and Path(actual)==Path(value),'PROFILE_PATH_BINDING_MISMATCH')
        else:gate(type(actual) is type(value) and actual==value,'PROFILE_IDENTITY_SOURCE_VERSION_MISMATCH')
    gate(profile.get('ports')==PORTS[FRESH] and all(type(v) is int for v in profile['ports'].values()),'PROFILE_PORTS_MISMATCH')
    gate(profile.get('database')=={'admin_schema':'dhcn_admin_'+suffix,'admin_user':'dhcn_admin_'+suffix,
        'core_schema':'dhcn_core_'+suffix,'core_user':'dhcn_core_'+suffix},'PROFILE_DATABASE_BINDING_MISMATCH')

def guard_phase(output,mode,previous):
    path=Path(output);base=OPERATION/'acceptance'
    gate(path.parent==base and path.name in PHASES,'PINNED_ACCEPTANCE_OUTPUT_REQUIRED')
    expected_mode,prior=PHASES[path.name];gate(mode==expected_mode,'PHASE_MODE_MISMATCH')
    if prior is None:gate(previous is None,'FIRST_PHASE_CANNOT_HAVE_PREDECESSOR')
    else:gate(previous is not None and Path(previous)==base/prior/'verification.json','EXACT_PREDECESSOR_RECEIPT_REQUIRED')
    return path.name

def guard_reference(reference,mode,expected_phase):
    if expected_phase is None:gate(reference is None,'UNEXPECTED_REFERENCE');return
    gate(isinstance(reference,dict) and reference.get('passed') is True,'SUCCESSFUL_PREDECESSOR_REQUIRED')
    gate(reference.get('schema_version')==SCHEMA and reference.get('installation_id')==FRESH
        and reference.get('expected_source')==SOURCE and reference.get('version')==VERSION
        and reference.get('setup_sha256')==SETUP and reference.get('helper_sha256')==digest(Path(__file__))
        and reference.get('phase')==PHASES[expected_phase][0] and reference.get('phase_name')==expected_phase,'PREDECESSOR_BINDING_MISMATCH')
    gate(isinstance(reference.get('snapshot'),dict) and isinstance(reference.get('joomla_presentation') or reference.get('historical_joomla_presentation'),dict),'PREDECESSOR_PRESERVATION_EVIDENCE_REQUIRED')
    if mode!='workflow':
        workflow=reference.get('workflow');gate(isinstance(workflow,dict) and workflow.get('match_id')==TARGET
            and workflow.get('forecast_key')==KEY and isinstance(workflow.get('record_ids'),dict)
            and bool(re.fullmatch('[a-f0-9]{32}',str(workflow.get('forecast_job_id',''))))
            and bool(re.fullmatch('[a-f0-9]{32}',str(workflow.get('evaluation_job_id','')))),'PREDECESSOR_WORKFLOW_REQUIRED')

def guard_configuration(profile,cfg):
    gate(isinstance(cfg,dict),'PROFILE_NOT_ACTIVE')
    for key in ('installation_id','product','edition','environment_id','install_root','state_root','service_name','browser_user_data','cookie_name','joomla_session_suffix'):
        gate(cfg.get(key)==profile.get(key),'ACTIVE_CONFIG_PROFILE_MISMATCH')
    gate(cfg.get('source_commit')==SOURCE and cfg.get('version')==VERSION,'ACTIVE_RELEASE_MISMATCH')
    gate(all(type(cfg.get(k+'_port')) is int and cfg[k+'_port']==v for k,v in PORTS[FRESH].items()),'ACTIVE_PORTS_MISMATCH')
    gate(isinstance(cfg.get('owner_sid'),str) and bool(re.fullmatch(r'S-1-5-(?:[0-9]+-)*[0-9]+',cfg['owner_sid'])),'OWNER_SID_UNVERIFIED')

def guard_activation(profile,cfg,metadata,installed):
    guard_configuration(profile,cfg)
    gate(isinstance(metadata,dict) and isinstance(installed,dict),'PROFILE_NOT_ACTIVE')
    gate(metadata.get('source_sha')==SOURCE and metadata.get('version')==VERSION,'ACTIVE_RELEASE_MISMATCH')
    gate(installed.get('installation_id')==FRESH and installed.get('product')=='DRAGONHYDRA CORE NEXT'
        and installed.get('service_name')==profile['service_name'] and Path(installed.get('install_root',''))==Path(profile['install_root'])
        and Path(installed.get('state_root',''))==Path(profile['state_root']) and Path(installed.get('profile_path',''))==PROFILE,'ACTIVE_INSTALL_RECEIPT_MISMATCH')

def authorize_api(method,path,mode,predecessor_verified):
    if method=='POST':
        gate(mode=='workflow' and predecessor_verified and path in ('/matches/'+TARGET+'/forecasts','/matches/'+TARGET+'/evaluations'),'CLASS_C_ACTION_NOT_AUTHORIZED_IN_MODE')
        return
    gate(method=='GET' and (path in ('/health/ready','/system','/modules','/modules?scope=all','/matches/'+TARGET+'/cognition-history')
        or re.fullmatch(r'/matches\?limit=200&offset=[0-9]{1,5}',path) or re.fullmatch(r'/jobs/[a-f0-9]{32}',path)),'API_OPERATION_OUTSIDE_READ_ALLOWLIST')

def guard_service_identity(item,profile,now=None):
    identity=item.get('service_identity') if isinstance(item,dict) else None
    gate(isinstance(identity,dict),'SERVICE_IDENTITY_UNAVAILABLE')
    gate(set(identity)=={'service_name','installation_id','source_commit','build_id','observed_at','evidence_expires_at','verification_scope'}
        and item.get('id')=='runtime_supervisor' and item.get('runtime_state')=='READY'
        and identity==item.get('observation',{}).get('service_identity'),'SERVICE_IDENTITY_CONTRACT_MISMATCH')
    return guard_identity_payload(identity,profile,now)

def guard_identity_payload(identity,profile,now=None):
    for key in ('service_name','installation_id','source_commit','build_id'):gate(identity.get(key)==profile.get(key),'SERVICE_IDENTITY_FOREIGN_BINDING')
    gate(identity['verification_scope']=='BOUND_SUPERVISOR_SERVICE_IDENTITY_ONLY'
        and isinstance(identity['service_name'],str) and re.fullmatch(r'Dragonhydra[A-Za-z0-9_-]{0,60}',identity['service_name']),'SERVICE_IDENTITY_SCOPE_MISMATCH')
    clocks=[]
    for key in ('observed_at','evidence_expires_at'):
        value=identity.get(key);gate(isinstance(value,str) and bool(re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z',value)),'SERVICE_IDENTITY_CLOCK_INVALID')
        try:clocks.append(datetime.fromisoformat(value.replace('Z','+00:00')))
        except ValueError:raise GateError('SERVICE_IDENTITY_CLOCK_INVALID') from None
    now=now or datetime.now(timezone.utc)
    gate(now.utcoffset() is not None and clocks[0]<=now<clocks[1] and 0<(clocks[1]-clocks[0]).total_seconds()<=90,'SERVICE_IDENTITY_NOT_FRESH')
    return identity

def rendered_service_identity(html,profile):
    class Panel(HTMLParser):
        def __init__(self):super().__init__(convert_charrefs=True);self.active=False;self.part=None;self.label='';self.value='';self.rows={};self.panels=[];self.text=[]
        def handle_starttag(self,tag,attrs):
            if tag=='dl' and 'data-service-identity' in dict(attrs):self.active=True;self.rows={}
            if self.active and tag in ('dt','dd'):self.part=tag;self.value=''
        def handle_data(self,value):
            self.text.append(value)
            if self.active and self.part:self.value+=value
        def handle_endtag(self,tag):
            if self.active and tag=='dt':self.label=self.value.strip();self.part=None
            if self.active and tag=='dd':self.rows[self.label]=self.value.strip();self.part=None
            if self.active and tag=='dl':self.panels.append(self.rows);self.active=False
    parser=Panel();parser.feed(html)
    labels={'Running service':'service_name','Installation':'installation_id','Source commit':'source_commit',
        'Build identity':'build_id','Observed (UTC)':'observed_at','Evidence expires (UTC)':'evidence_expires_at'}
    gate(len(parser.panels)==1 and set(parser.panels[0])==set(labels),'JOOMLA_TYPED_SERVICE_PANEL_MISSING')
    scope='BOUND_SUPERVISOR_SERVICE_IDENTITY_ONLY';gate(scope in ''.join(parser.text),'JOOMLA_SERVICE_SCOPE_MISSING')
    value={key:parser.panels[0][label] for label,key in labels.items()};value['verification_scope']=scope
    return guard_identity_payload(value,profile)
def ordinary(value,exists=True):
    path=Path(value)
    gate(path.is_absolute() and '..' not in path.parts,'ABSOLUTE_LAB_PATH_REQUIRED')
    gate(path.resolve().is_relative_to(LAB.resolve()) and path.resolve()!=LAB.resolve(),'PATH_OUTSIDE_LAB')
    for part in (path,*path.parents):gate(not part.is_symlink() and not getattr(part,'is_junction',lambda:False)(),'REPARSE_PATH_REJECTED')
    gate(not exists or path.exists(),'REQUIRED_PATH_MISSING')
    return path
def read(path):
    path=ordinary(path);gate(path.stat().st_size<16*1024*1024,'JSON_BOUND_EXCEEDED')
    return json.loads(path.read_text(encoding='utf-8-sig'))

class Forms(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True);self.forms=[];self.current=None;self.links=[];self.pre=[];self.in_pre=False;self.cards=[]
    def handle_starttag(self,tag,attrs):
        a=dict(attrs)
        if tag=='form':self.current={'attrs':a,'inputs':[]};self.forms.append(self.current)
        if tag=='input' and self.current is not None:self.current['inputs'].append(a)
        if tag=='a' and a.get('href'):self.links.append(a['href'])
        if tag=='pre':self.in_pre=True;self.pre.append('')
        if a.get('data-module-id'):self.cards.append(a['data-module-id'])
    def handle_endtag(self,tag):
        if tag=='form':self.current=None
        if tag=='pre':self.in_pre=False
    def handle_data(self,value):
        if self.in_pre:self.pre[-1]+=value
def login_form(html,origin):
    parser=Forms();parser.feed(html)
    forms=[f for f in parser.forms if any(i.get('type','').lower()=='password' for i in f['inputs'])]
    gate(len(forms)==1,'JOOMLA_LOGIN_FORM_NOT_UNIQUE');form=forms[0]
    action=urljoin(origin+'/administrator/',form['attrs'].get('action',''))
    gate(action==origin+'/administrator/index.php','LOGIN_ACTION_ORIGIN_MISMATCH')
    user=[i['name'] for i in form['inputs'] if i.get('name') and ('username' in i['name'].lower())]
    password=[i['name'] for i in form['inputs'] if i.get('type','').lower()=='password' and i.get('name')]
    hidden={i['name']:i.get('value','') for i in form['inputs'] if i.get('type','').lower()=='hidden' and i.get('name')}
    gate(len(user)==1 and len(password)==1,'LOGIN_FIELDS_NOT_IDENTIFIED')
    gate(sum(bool(re.fullmatch('[a-f0-9]{32}',k)) and v=='1' for k,v in hidden.items())==1,'LOGIN_CSRF_FIELD_UNVERIFIED')
    return action,hidden,user[0],password[0]
class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):raise GateError('API_REDIRECT_REJECTED')
class WebRedirect(HTTPRedirectHandler):
    def __init__(self,origin):self.origin=origin
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        gate(newurl.startswith(self.origin+'/administrator/'),'JOOMLA_REDIRECT_ORIGIN_REJECTED')
        return super().redirect_request(req,fp,code,msg,headers,newurl)

class Acceptance:
    def __init__(self,args):
        self.args=args;self.stage='target_binding';self.checks=[];self.requests=[];self.responses=[];self.token=None
        self.phase='workflow' if args.workflow else 'readback' if args.readback else 'uninstalled' if args.uninstalled else 'fresh'
        self.previous=args.previous if args.workflow else args.readback or args.uninstalled
        gate(args.workflow or args.previous is None,'PREVIOUS_ONLY_FOR_WORKFLOW')
        self.phase_name=guard_phase(args.output,self.phase,self.previous)
        self.profile_path=ordinary(args.profile);self.profile=read(self.profile_path);self.id=self.profile.get('installation_id')
        guard_profile(self.profile_path,self.profile)
        self.reference=read(self.previous) if self.previous else None
        guard_reference(self.reference,self.phase,PHASES[self.phase_name][1]);self.predecessor_verified=self.reference is not None
        configure(args.expected_source,args.setup_sha256,args.expected_version,args.fresh_installation_id)
        self.setup=ordinary(args.setup);gate(self.setup==EXPECTED_SETUP and digest(self.setup)==SETUP,'SETUP_PATH_OR_HASH_MISMATCH')
        self.install=ordinary(self.profile['install_root'],not bool(args.uninstalled));self.state=ordinary(self.profile['state_root'])
        self.cfg=read(self.state/'workstation.json')
        guard_configuration(self.profile,self.cfg)
        if not args.uninstalled:guard_activation(self.profile,self.cfg,read(self.install/'WORKSTATION-BUILD.json'),read(self.install/'workstation-installed.json'))
        self.output=ordinary(args.output,False);gate(not self.output.exists(),'FRESH_OUTPUT_REQUIRED');self.output.mkdir(parents=True)
        self.api='http://127.0.0.1:'+str(PORTS[self.id]['api'])+'/dragon/api/v1';self.web='http://127.0.0.1:'+str(PORTS[self.id]['web'])
        self.api_opener=build_opener(ProxyHandler({}),NoRedirect())
        self.jar=http.cookiejar.CookieJar();self.web_opener=build_opener(ProxyHandler({}),HTTPCookieProcessor(self.jar),WebRedirect(self.web))
        self.private=self.output/'private';self.private.mkdir()
        acl=subprocess.run(['icacls',str(self.private),'/inheritance:r','/grant:r','*S-1-5-18:(OI)(CI)F','*S-1-5-32-544:(OI)(CI)F','*'+self.cfg['owner_sid']+':(OI)(CI)F'],capture_output=True)
        gate(acl.returncode==0,'PRIVATE_BACKUP_ACL_FAILED')
        self.mode='workflow' if args.workflow else self.reference.get('mode','fresh') if self.reference else 'fresh'
    def save(self,passed=False):
        report={'schema_version':SCHEMA,'passed':passed,'expected_source':SOURCE,'setup_sha256':SETUP,'version':VERSION,
            'mode':self.mode,'phase':self.phase,'phase_name':self.phase_name,
            'installation_id':self.id,'profile_path':str(self.profile_path),'service_name':self.profile['service_name'],
            'ports':PORTS[self.id],'checks':self.checks,'observed_at':utc(),'helper_sha256':digest(Path(__file__)),
            'requests':self.requests,'service_or_installer_actions':False,'credentials_or_cookie_values_logged':False,
            'raw_html_saved':False,'provider_import_sync_or_local_ai_inference_requested':False,
            'deterministic_statistical_forecast_requested':bool(self.args.workflow),
            'windows_live_sql_restore':'NOT_RUN: no supported scoped restore controller is implemented; no destructive restore is attempted',
            'sqlite_backup_scope':'Consistent online backup in ACL-restricted private subdirectory; never raw copied live storage'}
        if self.previous:report['predecessor_receipt']={'path':str(self.previous),'sha256':digest(self.previous),'phase':self.reference['phase']}
        if hasattr(self,'snapshot'):report['snapshot']=self.snapshot
        if hasattr(self,'workflow'):report['workflow']=self.workflow
        if hasattr(self,'service_identity'):report['service_identity']=self.service_identity
        if hasattr(self,'joomla_presentation'):report['joomla_presentation']=self.joomla_presentation
        if hasattr(self,'sqlite_snapshot'):report['sqlite_consistent_snapshot']=self.sqlite_snapshot
        if self.args.uninstalled and hasattr(self,'historical_joomla_presentation'):
            report['historical_joomla_presentation']=self.historical_joomla_presentation
            report['post_uninstall_joomla_database_query']='NOT_RUN: owning MariaDB was removed; prior fingerprint retained as historical evidence only'
        temporary=self.output/('verification.'+uuid.uuid4().hex+'.tmp')
        with temporary.open('x',encoding='utf-8') as stream:json.dump(report,stream,indent=2);stream.write('\n');stream.flush();os.fsync(stream.fileno())
        os.replace(temporary,self.output/'verification.json')
    def check(self,name,**evidence):
        self.checks.append({'name':name,'status':'PASS','observed_at':utc(),**evidence});self.save();print(json.dumps({'check':name,'status':'PASS'}),flush=True)
    def ownership(self,uninstalled=False):
        helper=Path('C:/xampp/DRAGONHYDRA-CORE-NEXT/packaging/windows/workstation/CoreNextProfile.ps1')
        gate(digest(helper)==PROFILE_HELPER_SHA256,'PROFILE_INSPECTION_HELPER_CHANGED')
        script=r'''$ErrorActionPreference='Stop';$v=[Console]::In.ReadToEnd()|ConvertFrom-Json;. $v.helper;$p=Read-CoreNextProfile $v.profile -CheckService
$s=Get-CimInstance Win32_Service -Filter ("Name='"+$p.service_name+"'")
if($v.uninstalled){if($s){throw 'SERVICE_STILL_PRESENT'};foreach($port in @($p.ports.api,$p.ports.web,$p.ports.database)){if(@(Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue).Count){throw 'OWNED_PORT_STILL_LISTENING'}};@{service_absent=$true;listeners_absent=$true}|ConvertTo-Json -Compress;exit}
if(-not$s -or $s.State -cne 'Running' -or $s.ProcessId -le 0 -or $s.StartName -ine 'NT AUTHORITY\LocalService'){throw 'OWNED_SERVICE_NOT_RUNNING'}
$roles=@();foreach($kind in @('api','web','database')){$port=$p.ports.$kind;$ls=@(Get-NetTCPConnection -State Listen -LocalPort $port);if($ls.Count -ne 1 -or $ls[0].LocalAddress -cne '127.0.0.1'){throw 'OWNED_LOOPBACK_LISTENER_REQUIRED'};$child=[int]$ls[0].OwningProcess;$next=$child;$bound=$false;for($i=0;$i -lt 10 -and $next -gt 0;$i++){if($next -eq $s.ProcessId){$bound=$true;break};$proc=Get-CimInstance Win32_Process -Filter ('ProcessId='+$next);if(-not$proc){break};$next=[int]$proc.ParentProcessId};if(-not$bound){throw 'LISTENER_NOT_OWNED'};$roles+=@{role=$kind;port=$port;pid=$child}}
@{service_pid=[int]$s.ProcessId;account=$s.StartName;listeners=$roles;owned=$true}|ConvertTo-Json -Depth 5 -Compress'''
        result=subprocess.run([PWSH,'-NoProfile','-NonInteractive','-Command',script],input=json.dumps({'helper':str(helper),'profile':str(self.profile_path),'uninstalled':uninstalled}),capture_output=True,text=True,timeout=40)
        gate(result.returncode==0,'SCM_OR_LISTENER_OWNERSHIP_UNVERIFIED')
        return json.loads(result.stdout)
    def bind(self):
        self.stage='installed_binding'
        gate(read(self.setup.parent/'WORKSTATION-BUILD.json')['payload_manifest_sha256']==digest(self.install/'PAYLOAD-MANIFEST.json'),'INSTALLED_PAYLOAD_MANIFEST_MISMATCH')
        metadata=read(self.install/'WORKSTATION-BUILD.json');gate(metadata.get('source_sha')==SOURCE and metadata.get('version')==VERSION,'INSTALLED_SOURCE_MISMATCH')
        for item in metadata['application_components']:
            path=ordinary(self.install/item['path']);gate(path.resolve().is_relative_to(self.install.resolve()),'COMPONENT_PATH_OUTSIDE_INSTALLATION')
            gate(path.stat().st_size==item['bytes'] and digest(path)==item['sha256'] and item['source_commit']==SOURCE,'INSTALLED_COMPONENT_HASH_MISMATCH')
        owner=self.ownership();self.cfg=read(self.state/'workstation.json')
        for field in ('installation_id','product','edition','environment_id','install_root','state_root','service_name','browser_user_data','cookie_name','joomla_session_suffix'):
            gate(self.cfg.get(field)==self.profile.get(field),'CONFIG_PROFILE_BINDING_MISMATCH')
        gate(self.cfg.get('source_commit')==SOURCE and self.cfg.get('version')==VERSION,'CONFIG_SOURCE_MISMATCH')
        gate(all(self.cfg.get(k+'_port')==v for k,v in PORTS[self.id].items() if k!='web') and self.cfg.get('web_port')==PORTS[self.id]['web'],'CONFIG_PORT_MISMATCH')
        self.token=read(self.state/'client/local-session.json')['token'];gate(isinstance(self.token,str) and len(self.token)>=24,'OWN_CLIENT_PAIRING_UNAVAILABLE')
        health=self.api_get('/health/ready');identity=self.api_get('/system')['installation']
        gate(health.get('source_sha')==SOURCE and health.get('version')==VERSION and identity.get('installation_id')==self.id and identity.get('build_id')==self.profile['build_id'],'AUTHENTICATED_BACKEND_IDENTITY_MISMATCH')
        self.check('installed_source_service_listener_and_authenticated_identity',**owner)
    def api_request(self,method,path,body=None,key=None):
        gate(self.id==FRESH,'ONLY_DISPOSABLE_API_ALLOWED');authorize_api(method,path,self.phase,self.predecessor_verified)
        if method=='POST':gate(body=={} and key==(KEY if path.endswith('/forecasts') else KEY+'-evaluation'),'FIXED_EMPTY_IDEMPOTENT_JOB_REQUIRED')
        else:gate(body is None and key is None,'READ_REQUEST_MUST_NOT_CARRY_ACTION')
        headers={'Authorization':'Bearer '+self.token,'Content-Type':'application/json'}
        if key:headers['Idempotency-Key']=key
        data=canonical(body) if body is not None else None
        self.requests.append({'method':method,'path':path})
        try:
            with self.api_opener.open(Request(self.api+path,data=data,headers=headers,method=method),timeout=25) as r:
                code=r.status;raw=r.read(8*1024*1024+1)
        except HTTPError as e:code=e.code;raw=e.read(1024*1024)
        gate(code==(202 if method=='POST' else 200),'API_HTTP_STATUS_UNEXPECTED');gate(len(raw)<=8*1024*1024,'API_RESPONSE_TOO_LARGE')
        self.responses.append(raw);return json.loads(raw)
    def api_get(self,path):return self.api_request('GET',path)
    def wait_service_identity(self,inventory):
        deadline=time.monotonic()+60
        while True:
            item=next((m for m in inventory.get('items',[]) if m.get('id')=='runtime_supervisor'),{})
            try:self.service_identity=guard_service_identity(item,self.profile);return inventory
            except GateError as error:
                if str(error)!='SERVICE_IDENTITY_UNAVAILABLE':raise
                gate(time.monotonic()<deadline,'ACTUAL_SERVICE_IDENTITY_NOT_OBSERVED_WITHIN_BOUND')
            time.sleep(2);inventory=self.api_get('/modules?scope=all')
    def database(self,label):
        source=ordinary(self.state/'kernel/core.sqlite3');copy=self.private/(label+'.sqlite3');deadline=time.monotonic()+15
        with closing(sqlite3.connect(source.as_uri()+'?mode=ro',uri=True,timeout=.2)) as db,closing(sqlite3.connect(copy)) as target:
            db.backup(target,pages=128,sleep=.05,progress=lambda *_:gate(time.monotonic()<deadline,'SQLITE_BACKUP_TIMEOUT'))
        with closing(sqlite3.connect(copy.as_uri()+'?mode=ro',uri=True)) as db:
            gate(db.execute('PRAGMA integrity_check').fetchone()[0]=='ok','SQLITE_BACKUP_INTEGRITY_FAILED')
            schema=list(db.execute("SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name"));tables={}
            for (name,) in db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"):
                if name in ('product_bridge_nonces','product_sessions'):continue
                gate(bool(re.fullmatch('[A-Za-z_][A-Za-z0-9_]*',name)),'UNEXPECTED_TABLE_IDENTIFIER')
                cols=[row[1] for row in db.execute('PRAGMA table_info("'+name+'")')]
                order=','.join('"'+c.replace('"','""')+'"' for c in cols)
                h=hashlib.sha256();count=0
                for row in db.execute('SELECT * FROM "'+name+'" ORDER BY '+order):
                    count+=1;gate(count<=50000,'DOMAIN_SNAPSHOT_ROW_BOUND')
                    h.update(canonical([{'binary_sha256':sha(v),'bytes':len(v)} if isinstance(v,bytes) else v for v in row])+b'\n')
                tables[name]={'rows':count,'sha256':h.hexdigest()}
            schedules=db.execute('SELECT COUNT(*) FROM connector_settings WHERE interval_seconds>0').fetchone()[0]
            active=db.execute("SELECT COUNT(*) FROM product_jobs WHERE status IN ('queued','running')").fetchone()[0]
        gate(schedules==0,'PROVIDER_SCHEDULES_ENABLED');gate(active==0,'ACTIVE_JOB_REQUIRES_RECONCILIATION')
        files={}
        for relative in ('workstation.json','first-run.json','site/configuration.php','client/local-session.json','kernel/product.json','web-config/httpd.conf','web-config/php.ini','web-config/my.ini'):
            path=self.state/relative
            if path.exists():files[relative]=digest(ordinary(path))
        vault=self.state/'kernel/vault'
        if vault.exists():
            members=list(vault.rglob('*'));gate(len(members)<=100,'VAULT_INVENTORY_BOUND')
            for p in members:
                ordinary(p)
                if p.is_file():files[p.relative_to(self.state).as_posix()]=digest(p)
        if label in ('after-reads','after-uninstall'):self.sqlite_snapshot={'path':str(copy),'sha256':digest(copy),'integrity_check':'ok','consistent_backup':True}
        return {'domain_tables':tables,'schema_sha256':sha(canonical(schema)),
            'schema_objects':{kind+':'+name:sha(canonical([kind,name,table,sql])) for kind,name,table,sql in schema},
            'configuration_fingerprints':files,'provider_schedules':schedules}
    def matches(self):
        rows=[];total=None
        while total is None or len(rows)<total:
            p=self.api_get('/matches?limit=200&offset='+str(len(rows)))
            total=p['total'] if total is None else total;gate(p['total']==total and bool(p['items']),'MATCH_PAGE_DRIFT')
            rows+=p['items'];gate(len(rows)<=20000,'MATCH_SNAPSHOT_BOUND')
        gate(len(rows)==total==760 and len({r['id'] for r in rows})==total,'RETAINED_MATCH_IDENTITIES_MISMATCH')
        return rows
    def job(self,item):
        gate(isinstance(item,dict) and bool(re.fullmatch('[a-f0-9]{32}',str(item.get('id','')))),'INVALID_OWNED_JOB_IDENTIFIER')
        deadline=time.monotonic()+90
        while time.monotonic()<deadline:
            value=self.api_get('/jobs/'+item['id'])
            if value['status'] in ('succeeded','failed','cancelled','interrupted'):
                gate(value['status']=='succeeded','EXPLICIT_WORKFLOW_JOB_FAILED');return value
            time.sleep(.2)
        raise GateError('EXPLICIT_WORKFLOW_JOB_TIMEOUT')
    def web_request(self,url,form=None,anonymous=False):
        gate(url.startswith(self.web+'/administrator/'),'WEB_URL_OUTSIDE_PINNED_ADMIN')
        opener=build_opener(ProxyHandler({}),HTTPCookieProcessor(http.cookiejar.CookieJar()),WebRedirect(self.web)) if anonymous else self.web_opener
        data=urlencode(form).encode() if form is not None else None
        try:
            with opener.open(Request(url,data=data),timeout=25) as r:code=r.status;raw=r.read(4*1024*1024+1)
        except HTTPError as e:code=e.code;raw=e.read(1024*1024)
        gate(code==200 and len(raw)<=4*1024*1024,'JOOMLA_HTTP_RESPONSE_FAILED');self.responses.append(raw)
        return raw.decode('utf-8','replace')
    def presentation(self):
        gate(self.id==FRESH,'PRESENTATION_QUERY_REQUIRES_DISPOSABLE_PROFILE')
        php=ordinary(self.install/'web/php/php.exe');ini=ordinary(self.state/'web-config/php.ini')
        configuration=ordinary(self.state/'site/configuration.php')
        data={'configuration':str(configuration),'port':PORTS[self.id]['database'],
              'schema':self.profile['database']['admin_schema'],'user':self.profile['database']['admin_user']}
        result=subprocess.run([str(php),'-c',str(ini),'-r',PHP_PRESENTATION],input=json.dumps(data),
            capture_output=True,text=True,timeout=35)
        gate(result.returncode==0,'JOOMLA_READONLY_FINGERPRINT_FAILED')
        value=json.loads(result.stdout)
        gate(value.get('passed') is True and value.get('read_only') is True and value.get('consistent_snapshot') is True,'JOOMLA_CONSISTENT_READONLY_PROOF_MISSING')
        return value
    def joomla(self,match,module_ids):
        self.stage='genuine_disposable_joomla_authentication'
        gate(self.id==FRESH,'PRIMARY_JOOMLA_CREDENTIAL_USE_FORBIDDEN')
        admin=self.web+'/administrator/';component=admin+'index.php?option=com_dragonhydra'
        guest=self.web_request(component,anonymous=True);gate('mod-login-username' in guest and 'data-core-next-control-center' not in guest,'ANONYMOUS_ADMIN_PROTECTION_FAILED')
        login=self.web_request(admin);action,hidden,userfield,passfield=login_form(login,self.web)
        hidden[userfield]=self.cfg['admin_user'];hidden[passfield]=self.cfg['admin_password']
        self.web_request(action,form=hidden)
        html=self.web_request(component+'&section=modules');p=Forms();p.feed(html)
        gate('data-core-next-control-center' in html and self.id in html and SOURCE[:12] in html and 'mod-login-username' not in html,'GENUINE_JOOMLA_COMPONENT_AUTH_FAILED')
        gate(set(p.cards)==module_ids,'JOOMLA_REGISTRY_IDS_MISMATCH')
        gate(any('task=logout' in link for link in p.links),'AUTHENTICATED_JOOMLA_LOGOUT_ACTION_MISSING')
        infrastructure=self.web_request(component+'&section=infrastructure')
        displayed=rendered_service_identity(infrastructure,self.profile)
        gate(bool(getattr(self,'service_identity',None)) and all(displayed[key]==self.service_identity[key]
            for key in ('service_name','installation_id','source_commit','build_id','verification_scope')),'JOOMLA_ACTUAL_SERVICE_IDENTITY_NOT_DISPLAYED')
        detail=self.web_request(component+'&section=matches&match_id='+match['id']);p=Forms();p.feed(detail)
        technical=[]
        for raw in p.pre:
            try:value=json.loads(raw)
            except ValueError:continue
            if isinstance(value,dict) and value.get('id')==match['id']:technical.append(value)
        gate(len(technical)==1,'JOOMLA_RETAINED_TECHNICAL_RECORD_MISSING')
        for key in ('id','version','source_id','evidence_id','event_date','home','away','score','status','competition_id'):gate(technical[0].get(key)==match.get(key),'JOOMLA_BACKEND_RECORD_MISMATCH')
        subsequent=self.web_request(component+'&section=overview');gate(self.id in subsequent and 'data-core-next-control-center' in subsequent,'JOOMLA_SESSION_CONTINUITY_FAILED')
        parser=Forms();parser.feed(subsequent);logout=[urljoin(admin,x) for x in parser.links if 'task=logout' in x]
        gate(bool(logout),'NORMAL_LOGOUT_LINK_MISSING');self.web_request(logout[0])
        after=self.web_request(component);gate('mod-login-username' in after and 'data-core-next-control-center' not in after,'LOGOUT_PROTECTION_FAILED')
        gate('data-core-next-control-center' not in self.web_request(component,anonymous=True),'FRESH_ANONYMOUS_SESSION_EXPOSED_ADMIN')
        self.check('genuine_joomla_owner_auth_session_control_center_retained_record_and_logout',username=self.cfg['admin_user'],modules=len(module_ids),match_id=match['id'],actual_form_csrf_used=True,record_fields_compared=10)
    def run(self):
        if self.args.uninstalled:
            self.cfg=read(self.state/'workstation.json');owner=self.ownership(True)
            gate(not (self.install/'server/DRAGONHYDRA-Server.exe').exists() and not (self.install/'client/DRAGONHYDRA-Client.exe').exists(),'DISPOSABLE_BINARIES_REMAIN')
            self.snapshot=self.database('after-uninstall')
            expected={k:v for k,v in self.reference['snapshot'].items() if k!='match_id_versions'}
            gate(self.snapshot==expected,'UNINSTALL_RETAINED_STATE_CHANGED')
            self.snapshot['match_id_versions']=self.reference['snapshot']['match_id_versions']
            self.historical_joomla_presentation=self.reference.get('joomla_presentation') or self.reference.get('historical_joomla_presentation')
            gate(self.historical_joomla_presentation is not None,'PRE_UNINSTALL_JOOMLA_HISTORY_MISSING')
            self.check('disposable_uninstall_preserved_state_and_removed_only_owned_runtime',**owner);self.save(True);return
        self.bind();before=self.database('before-reads');rows=self.matches();ids=sorted([m['id'],m['version']] for m in rows)
        presentation_before=self.presentation() if self.id==FRESH else None
        if self.reference and self.id==FRESH:
            gate(presentation_before==(self.reference.get('joomla_presentation') or self.reference.get('historical_joomla_presentation')),'JOOMLA_PRESENTATION_CHANGED_ACROSS_REPAIR_OR_RESTART')
        engines=self.api_get('/modules');all_=self.api_get('/modules?scope=all')
        gate(len(engines['items'])==6 and len(all_['items'])==18 and all_['inventory']=={'engines':6,'supporting':12,'total':18},'REGISTRY_SCOPE_MISMATCH')
        all_=self.wait_service_identity(all_)
        self.check('actual_scm_supervisor_identity_and_freshness',service_identity=self.service_identity,
            verification_scope='Service/supervisor binding only; no account, administrative/control privilege or interactive-client claim')
        self.check('authenticated_actual_760_and_registry_6_18',retained=len(rows),inventory=all_['inventory'])
        if self.args.workflow:
            self.stage='explicit_disposable_workflow'
            gate(dict(before,match_id_versions=ids)==self.reference['snapshot'],'PREDECESSOR_STATE_CHANGED_RECONCILE_REQUIRED')
            target=next((r for r in rows if r['id']==TARGET),None);gate(target is not None and target['status']=='scheduled','FIXED_REAL_FUTURE_TARGET_UNAVAILABLE')
            forecast=self.job(self.api_request('POST','/matches/'+TARGET+'/forecasts',{},KEY))
            replay=self.api_request('POST','/matches/'+TARGET+'/forecasts',{},KEY)
            gate(replay['id']==forecast['id'] and replay['result']==forecast['result'],'FORECAST_DUPLICATE_IDENTITY_FAILED')
            result=forecast['result'];gate(result.get('available') is True and result.get('status')=='persisted' and len(result['predictions'])==5 and len(result['model_runs'])==5,'PERSISTED_REAL_FORECAST_UNAVAILABLE')
            gate(all(m['parameters']['workflow']['build']['source_sha']==SOURCE and m['parameters']['workflow']['match_id']==TARGET for m in result['model_runs']),'FORECAST_BUILD_PROVENANCE_MISMATCH')
            pending=self.job(self.api_request('POST','/matches/'+TARGET+'/evaluations',{},KEY+'-evaluation'))
            pending_replay=self.api_request('POST','/matches/'+TARGET+'/evaluations',{},KEY+'-evaluation')
            gate(pending_replay['id']==pending['id'] and pending_replay['result']==pending['result'],'EVALUATION_DUPLICATE_IDENTITY_FAILED')
            gate(pending['result']['status']=='pending' and pending['result'].get('available') is False and pending['result']['reason']=='LATER_RETAINED_OUTCOME_UNAVAILABLE','EVALUATION_MUST_REMAIN_HONESTLY_PENDING')
            history=self.api_get('/matches/'+TARGET+'/cognition-history')
            self.workflow={'match_id':TARGET,'forecast_job_id':forecast['id'],'evaluation_job_id':pending['id'],
                'record_ids':{k:[r['record_id'] for r in v] for k,v in history['records'].items()},'history_records_sha256':sha(canonical(history['records'])),
                'counts':history['counts'],'input_evidence_ids':result['model_runs'][0]['input_evidence_ids'],
                'model_generation_time':result['model_runs'][0]['parameters']['workflow']['generated_at'],
                'forecast_key':KEY,'pending_reason':pending['result']['reason']}
            self.check('disposable_real_forecast_persisted_duplicate_reused_and_evaluation_pending',forecast_job_id=forecast['id'],evaluation_job_id=pending['id'],counts=history['counts'])
        elif self.reference and self.reference.get('workflow'):
            self.workflow=self.reference['workflow'];history=self.api_get('/matches/'+TARGET+'/cognition-history')
            gate(sha(canonical(history['records']))==self.workflow['history_records_sha256'],'RESTART_HISTORY_RECORDS_CHANGED')
            for key in ('forecast_job_id','evaluation_job_id'):gate(self.api_get('/jobs/'+self.workflow[key])['status']=='succeeded','PERSISTED_JOB_STATUS_CHANGED')
            self.check('disposable_restart_readback_preserved_real_records_and_jobs',counts=history['counts'])
        if self.id==FRESH:self.joomla(rows[0],{m['id'] for m in all_['items']})
        if self.id==FRESH:
            self.joomla_presentation=self.presentation()
            gate(self.joomla_presentation==presentation_before,'JOOMLA_READS_CHANGED_PRESENTATION_DATA')
            self.check('joomla_presentation_idempotence_consistent_innodb_snapshot',fingerprints=self.joomla_presentation['fingerprints'],
                compared_to_prior_receipt=bool(self.reference),table_prefix=self.joomla_presentation['table_prefix'])
        self.stage='preservation_snapshot';self.snapshot=self.database('after-reads');self.snapshot['match_id_versions']=ids
        if not self.args.workflow:
            expected=dict(before,match_id_versions=ids);gate(self.snapshot==expected,'READS_CHANGED_DOMAIN_OR_PROTECTED_CONFIGURATION')
        else:
            gate(before['configuration_fingerprints']==self.snapshot['configuration_fingerprints'],'WORKFLOW_CHANGED_PRIVATE_CONFIGURATION')
            allowed={'cognitive_records','cognitive_receipts','product_jobs','product_updates'}
            for table in before['domain_tables'].keys()|self.snapshot['domain_tables'].keys():
                if table not in allowed:gate(before['domain_tables'].get(table)==self.snapshot['domain_tables'].get(table),'WORKFLOW_CHANGED_RETAINED_INPUTS_OR_PROVIDER_SETTINGS')
            for name in before['schema_objects'].keys()|self.snapshot['schema_objects'].keys():
                if not name.split(':',1)[1].startswith(('cognitive_','sqlite_autoindex_cognitive_')):
                    gate(before['schema_objects'].get(name)==self.snapshot['schema_objects'].get(name),'WORKFLOW_CHANGED_UNRELATED_SCHEMA')
        if self.reference and not self.args.workflow:gate(self.snapshot==self.reference['snapshot'],'REPAIR_OR_RESTART_PRESERVATION_MISMATCH')
        secrets=[self.token]+[self.cfg[k] for k in ('root_password','db_password','core_db_password','admin_password') if isinstance(self.cfg.get(k),str)]
        gate(not any(s and s.encode() in response for s in secrets for response in self.responses),'PRIVATE_VALUE_IN_RENDERED_RESPONSE')
        self.check('consistent_sqlite_domain_configuration_pairing_and_provider_preservation',records=len(ids),provider_schedules=0,consistent_backup_integrity=True,known_secret_values_in_responses=0)
        self.save(True)

def configure(source,setup,version,fresh):
    gate(source==SOURCE and setup==SETUP and version==VERSION and fresh==FRESH,'PINNED_DISPOSABLE_RELEASE_REQUIRED')

def arguments():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile',required=True);parser.add_argument('--setup',required=True);parser.add_argument('--setup-sha256',required=True)
    parser.add_argument('--expected-source',required=True);parser.add_argument('--expected-version',required=True);parser.add_argument('--fresh-installation-id',required=True);parser.add_argument('--output',required=True)
    mode=parser.add_mutually_exclusive_group(required=True);mode.add_argument('--fresh',action='store_true');mode.add_argument('--workflow',action='store_true');mode.add_argument('--readback');mode.add_argument('--uninstalled');parser.add_argument('--previous')
    return parser.parse_args()
def main():
    test=None
    try:
        args=arguments();configure(args.expected_source,args.setup_sha256,args.expected_version,args.fresh_installation_id)
        test=Acceptance(args);test.run();print(json.dumps({'passed':True,'checks':len(test.checks),'report':str(test.output/'verification.json')}));return 0
    except Exception as error:
        code=str(error) if isinstance(error,GateError) and re.fullmatch('[A-Z0-9_]+',str(error)) else 'SANITIZED_HELPER_OPERATION_FAILED'
        if test:
            test.checks.append({'name':test.stage,'status':'FAIL','code':code,'exception_type':type(error).__name__,'helper_line':traceback.extract_tb(error.__traceback__)[-1].lineno});test.save()
        print(json.dumps({'passed':False,'code':code}));return 1
if __name__=='__main__':raise SystemExit('SUPPORT_MODULE_ONLY_USE_DEV7_SERVICE_ACCEPTANCE')
