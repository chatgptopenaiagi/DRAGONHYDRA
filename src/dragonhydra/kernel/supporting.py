"""Real supporting responsibilities, observed within the existing kernel lifecycle.

These are not new engines/processes. Registry reads use cached observations;
only the local observer calls these bounded filesystem/SQLite observations.
"""
from contextlib import closing
from dataclasses import replace
from datetime import datetime,timedelta,timezone
import json,os,re,sqlite3,time
from pathlib import Path

from .contracts import ModuleDefinition,ServiceIdentity


_SPECS=(
 ('web_server','Apache / PHP web serving','Serve this installation\'s loopback Joomla HTTP routes.','Infrastructure',(),('workstation_profile','apache_configuration','php_runtime'),'packaging/windows/workstation/Workstation.ps1','Owned Apache/PHP child processes',('joomla_http',)),
 ('joomla_administration','Joomla administration','Own user identity, ACL and component administration; bootstrap is not authenticated acceptance.','Infrastructure',('web_server','mariadb_storage','api_server'),('joomla_component',),'server/joomla/com_dragonhydra/admin','Joomla/PHP and its MariaDB account domain',('joomla_users','permissions','component_settings')),
 ('joomla_website','Joomla sports website','Render retained sports views through the existing signed server bridge.','Interfaces',('web_server','api_server'),('web_document_root','joomla_component'),'server/joomla/com_dragonhydra/site','Joomla/PHP frontend',('site_sessions','presentation')),
 ('api_server','Authenticated Python API','Own typed requests, pairing, HMAC permissions and shared client contracts.','Infrastructure',(),('worker',),'src/dragonhydra/api.py','This ASGI application process',('api_sessions','bridge_nonces')),
 ('sqlite_storage','Sports SQLite storage','Authoritative retained sports evidence, jobs and immutable research domains.','Storage',(),('core_sqlite',),'src/dragonhydra/product.py','Configured CORE NEXT SQLite file',('sports_evidence','jobs','cognition')),
 ('mariadb_storage','Joomla MariaDB storage','Own Joomla accounts/content/configuration; not the sports authority.','Storage',(),('mariadb_endpoint',),'packaging/windows/workstation/web/manage.php','Owned MariaDB child process',('joomla_accounts','joomla_content')),
 ('durable_jobs','Durable job worker','Execute fixed authorized work with owner, lease, idempotency and result history.','Infrastructure',('sqlite_storage',),('worker',),'src/dragonhydra/jobs.py','Existing Python job-worker thread',('product_jobs','product_updates')),
 ('provider_scheduler','Configured provider scheduling','Dispatch only enabled due provider schedules through the existing worker.','Data sources',('durable_jobs',),('provider_settings',),'src/dragonhydra/connectors/service.py','Existing worker scheduler',('provider_settings','scheduled_jobs')),
 ('runtime_supervisor','Runtime observation and supervision','Observe this profile and own its configured children; reads never restart them.','Infrastructure',(),('workstation_profile',),'packaging/windows/workstation/Workstation.ps1','Owning Windows service plus existing kernel worker observer',('bounded_observations','owned_child_status')),
 ('windows_desktop','Windows launcher and desktop','Native paired access and safe external-browser handoff; file presence is not interactive proof.','Interfaces',('api_server',),('endpoint_pairing',),'client/desktop','Owner interactive launcher/Tauri process',('client_pairing','webview_state')),
 ('android_client','Android client contract','Mobile access through the same explicit endpoint/pairing API; device proof is separate.','Interfaces',('api_server',),('external_android_pairing',),'android/dragonhydra_mobile','External Flutter application/device',('mobile_pairing',)),
 ('packaging_recovery','Packaging, configuration and recovery','Reproduce, install, repair and uninstall only the matching edition/profile.','Infrastructure',(),('package_manifest','workstation_profile'),'scripts/Build-CoreNextWorkstation.ps1','Scoped CORE NEXT management tooling',('distribution_manifests','installation_profile')),
)


def definitions(version):
    return tuple(ModuleDefinition(identifier,name,description,category,dependencies,
        capabilities=('inspect_status',),origin='supporting',version=version,
        configuration_requirements=config,supported_operations=('status',),data_domains=domains,
        implementation_reference=source,verification_references=('tests/core_next/test_supporting_registry.py',),
        capability_operations=(('inspect_status',('status',)),),layer='supporting',runtime_owner=owner)
        for identifier,name,description,category,dependencies,config,source,owner,domains in _SPECS)


class SupportBinding:
    contract_version='core-next.support/1'
    def __init__(self,identifier,source):self.identifier,self.source=identifier,source
    def observe(self):return self.source.observe(self.identifier)
    def status(self):return {'operation':'GET /modules/'+self.identifier,'read_only':True}


class SupportingObservations:
    def __init__(self,context,config,clock):
        self.context,self.config,self.clock=context,config,clock
        self.worker=None;self.api_active=False;self.observer=None;self._store_cache=None
    def begin_cycle(self):self._store_cache=None
    def bindings(self):return {item[0]:SupportBinding(item[0],self) for item in _SPECS}
    @staticmethod
    def _json(path,limit=65536):
        if (not path.is_file() or any(p.is_symlink() or (hasattr(p,'is_junction') and p.is_junction())
                for p in (path,*path.parents)) or path.stat().st_size>limit):return None
        try:
            with path.open('rb') as stream:raw=stream.read(limit+1)
            if len(raw)>limit:return None
            data=json.loads(raw.decode('utf-8-sig'));return data if isinstance(data,dict) else None
        except (OSError,ValueError,UnicodeError):return None
    def _profile(self):
        state=self.context.storage.state
        path=state.parent/'workstation.json'
        data=self._json(path) if state.name=='kernel' else None
        if state.name=='kernel' and path.exists() and not data:raise ValueError('WORKSTATION_PROFILE_UNREADABLE')
        if not data:return None
        if (data.get('product')!='DRAGONHYDRA CORE NEXT' or data.get('installation_id')!=self.config.installation_id
                or data.get('source_commit')!=self.config.source_commit or data.get('build_id')!=self.config.build_id
                or Path(str(data.get('state_root',''))).resolve()!=state.parent.resolve()):raise ValueError('WORKSTATION_PROFILE_IDENTITY_MISMATCH')
        return {k:data.get(k) for k in ('installation_id','source_commit','build_id','service_name','install_root','state_root','api_port','web_port','database_port')}
    def _receipt(self,cfg):
        value=self._json(self.context.storage.state.parent/'runtime-observations.json')
        if not value or value.get('schema_version')!=2 or value.get('observer')!='core-next.supervisor':return None
        if (any(value.get(k)!=cfg.get(k) for k in ('installation_id','source_commit','build_id','service_name'))
                or value.get('api_pid')!=os.getpid() or type(value.get('supervisor_pid')) is not int
                or value['supervisor_pid']<=0):return None
        try:
            at=datetime.fromisoformat(value['observed_at'].replace('Z','+00:00'));expiry=datetime.fromisoformat(value['expires_at'].replace('Z','+00:00'));now=self.clock()
            success=datetime.fromisoformat(value['last_success_at'].replace('Z','+00:00'))
            if at.utcoffset() is None or expiry.utcoffset() is None or not at<=now<expiry or not 0<(expiry-at).total_seconds()<=90:return None
            if value.get('api_verified') is not True or success.utcoffset() is None or not 0<=(at-success).total_seconds()<=90:return None
        except (TypeError,ValueError,KeyError,AttributeError):return None
        value['_at'],value['_expiry'],value['_success']=at,expiry,success
        return value
    def _store(self):
        if self._store_cache is not None:return self._store_cache
        deadline=time.monotonic()+0.25
        try:
            with closing(sqlite3.connect(self.context.storage.db_path.as_uri()+'?mode=ro',uri=True,timeout=0.1)) as db:
                db.execute('PRAGMA query_only=ON');db.set_progress_handler(lambda:int(time.monotonic()>deadline),1000)
                tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                metrics={'table_count':len(tables),'schema_complete':{'product_schema','product_jobs'}<=tables}
                if 'product_jobs' in tables:
                    metrics.update(queued_jobs=db.execute("SELECT COUNT(*) FROM product_jobs WHERE status='queued'").fetchone()[0],running_jobs=db.execute("SELECT COUNT(*) FROM product_jobs WHERE status='running'").fetchone()[0])
                schedules=None
                if 'connector_settings' in tables:
                    columns={r[1] for r in db.execute('PRAGMA table_info(connector_settings)')}
                    if 'interval_seconds' not in columns:raise ValueError('INVALID_SCHEDULE_SCHEMA')
                    schedules=db.execute('SELECT COUNT(*) FROM connector_settings WHERE interval_seconds>0').fetchone()[0]
                if schedules is not None:metrics['enabled_schedules']=schedules
                self._store_cache=metrics
        except (OSError,sqlite3.Error,ValueError):self._store_cache={}
        return self._store_cache
    def _service_identity(self,cfg,receipt):
        # A configured service name is not SCM evidence. Only the existing
        # supervisor's exact running-service/parent-PID check may supply it.
        value=receipt.get('service_identity')
        expected={'schema_version','service_name','service_process_id','supervisor_process_id','observed_at','verification_scope'}
        if not isinstance(value,dict) or set(value)!=expected:return None
        if (type(receipt.get('schema_version')) is not int or receipt['schema_version']!=2
                or type(value.get('schema_version')) is not int or value['schema_version']!=1 or value.get('service_name')!=cfg.get('service_name')
                or value.get('verification_scope')!='SCM_RUNNING_SERVICE_AND_SUPERVISOR_PARENT_ONLY'
                or type(value.get('service_process_id')) is not int or not 0<value['service_process_id']<=2**32-1
                or type(value.get('supervisor_process_id')) is not int
                or value['supervisor_process_id']!=receipt.get('supervisor_pid')
                or value['service_process_id']==value['supervisor_process_id']):return None
        try:
            at=datetime.fromisoformat(value['observed_at'].replace('Z','+00:00'))
            if at.utcoffset() is None or not 0<=(receipt['_at']-at).total_seconds()<=90:return None
            expiry=min(receipt['_expiry'],at+timedelta(seconds=90))
            if not at<=self.clock()<expiry:return None
            return ServiceIdentity(value['service_name'],cfg['installation_id'],cfg['source_commit'],cfg['build_id'],at,expiry)
        except (KeyError,TypeError,ValueError,AttributeError):return None
    def observe(self,identifier):
        def value(state,reason,metrics=None,scope='BOUNDED_LOCAL_METADATA'):
            return {'state':state,'reason':reason,'metrics':metrics or {},'evidence':[scope]}
        if identifier=='api_server':
            return value('READY' if self.api_active else 'UNVERIFIED','ASGI_LIFESPAN_ACTIVE' if self.api_active else 'HTTP_APPLICATION_NOT_OBSERVED',{'process_id':os.getpid()},'ASGI_APPLICATION_LIFESPAN; not every endpoint acceptance')
        if identifier=='sqlite_storage':
            metrics=self._store();return value('READY' if metrics.get('schema_complete') else 'UNAVAILABLE','PRODUCT_SCHEMA_READABLE' if metrics.get('schema_complete') else 'STORE_SCHEMA_UNREADABLE',metrics,'READ_ONLY_SQLITE_SCHEMA; not full integrity certification')
        if identifier in ('durable_jobs','provider_scheduler'):
            metrics=self._store();alive=bool(self.worker and self.worker.thread and self.worker.thread.is_alive() and not self.worker.stop.is_set())
            if not metrics:return value('UNAVAILABLE','JOB_STORE_UNREADABLE')
            if identifier=='provider_scheduler' and 'enabled_schedules' not in metrics:return value('NOT_CONFIGURED','SCHEDULER_SCHEMA_NOT_OBSERVED')
            if identifier=='provider_scheduler' and not metrics['enabled_schedules']:return value('NOT_APPLICABLE','NO_ENABLED_PROVIDER_SCHEDULES',{'enabled_schedules':0})
            return value('READY' if alive else 'UNAVAILABLE','EXISTING_WORKER_ALIVE' if alive else 'EXISTING_WORKER_NOT_OBSERVED',{**metrics,'worker_alive':alive},'WORKER_AND_QUEUE_METADATA_ONLY; no job dispatch')
        try:cfg=self._profile()
        except ValueError:return value('UNAVAILABLE','WORKSTATION_PROFILE_BINDING_UNVERIFIED')
        if identifier=='android_client':return value('UNVERIFIED','EXTERNAL_ANDROID_SESSION_NOT_OBSERVED',scope='SOURCE_CONTRACT_ONLY; no device/pairing claim')
        if not cfg:return value('NOT_APPLICABLE','NO_BOUND_WORKSTATION_PROFILE',scope='Standalone/source kernel; external workstation responsibility not deployed here')
        if identifier=='windows_desktop':
            present=(Path(cfg['install_root'])/'client/DRAGONHYDRA-Client.exe').is_file()
            return value('UNVERIFIED','INTERACTIVE_CLIENT_NOT_OBSERVED',{'artifact_present':present},'INSTALLED_FILE_ONLY; no native pairing/browser claim')
        if identifier=='packaging_recovery':
            present=(Path(cfg['install_root'])/'WORKSTATION-BUILD.json').is_file()
            return value('UNVERIFIED','MANAGEMENT_EXECUTION_NOT_REQUESTED',{'artifact_present':present},'MANIFEST_PRESENCE_ONLY; no install/repair/uninstall claim')
        receipt=self._receipt(cfg)
        if not receipt:return value('UNVERIFIED','SUPERVISOR_EVIDENCE_MISSING_STALE_OR_WRONG_IDENTITY')
        checks=receipt.get('checks',{})
        if identifier=='runtime_supervisor':
            result={**value('READY','BOUND_SUPERVISOR_HEARTBEAT',{'process_id':receipt.get('supervisor_pid')},'LIVE_OWNED_CHILD_PROCESSES; no service-control permission claim'),
                'observed_at':receipt['_at'],'expires_at':receipt['_expiry'],'last_success_at':receipt['_success']}
            identity=self._service_identity(cfg,receipt)
            if identity is not None:result['service_identity']=identity
            return result
        check=checks.get(identifier)
        if not isinstance(check,dict) or check.get('state') not in ('READY','DEGRADED','UNAVAILABLE','UNVERIFIED'):return value('UNVERIFIED','LOCAL_CHECK_NOT_REPORTED')
        try:
            at=datetime.fromisoformat(check['observed_at'].replace('Z','+00:00'))
            success=datetime.fromisoformat(check['last_success_at'].replace('Z','+00:00')) if check.get('last_success_at') else None
            if at.utcoffset() is None or not at<=receipt['_at'] or (receipt['_at']-at).total_seconds()>90:raise ValueError('INVALID_CHECK_CLOCK')
            if check['state']=='READY' and (success is None or success.utcoffset() is None or not 0<=(at-success).total_seconds()<=90):raise ValueError('INVALID_SUCCESS_CLOCK')
        except (KeyError,ValueError,TypeError,AttributeError):return value('UNVERIFIED','LOCAL_CHECK_CLOCK_UNVERIFIED')
        return {**value(check['state'],check.get('reason','LOCAL_CHECK_UNVERIFIED'),{k:v for k,v in check.get('metrics',{}).items() if k in ('http_status','process_id','listener_present')},check.get('scope','OWNED_LOCAL_REACHABILITY_ONLY')),
            'observed_at':at,'expires_at':receipt['_expiry'],'last_success_at':success}
