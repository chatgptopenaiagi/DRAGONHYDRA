"""Pinned A6 repair and retained package acceptance for the owned A2 service.

Preflight is read-only. Repair permits one installer invocation. Readchecks
permits one UI package/3 fallback job, same-key replay and browser session auth.
No provider acquisition, settings change, model runner or extra restart occurs.
Historical A5 and local-model journeys are reused without changing their bytes.
"""
from __future__ import annotations

import argparse
from contextlib import closing
import ctypes
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import sys
import time
import traceback
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlsplit
from urllib.request import Request

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'src'))
HISTORICAL = {'tests/installation/statsbomb_context_workstation.py':'d9991f2e3092b1cc96c45829f91e42942c985633f31ada2dcc0d58c02d1ab999',
    'tests/installation/local_ai_workstation.py':'44691a2ce7a46fd40839c6ab86722e715927eae56a94af927edfb37a29da2578'}
for historical_path,historical_sha in HISTORICAL.items():
    assert hashlib.sha256((ROOT/historical_path).read_bytes()).hexdigest()==historical_sha


def module(name,path):
    spec = importlib.util.spec_from_file_location(name,path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


a5 = module('_immutable_a5_workstation_patterns',ROOT/'tests/installation/statsbomb_context_workstation.py')
prior, retained = a5.prior, a5.retained
from dragonhydra import local_ai
from dragonhydra.server import protect

SERVICE = prior.SERVICE
OLD_KERNEL = a5.KERNEL_SHA
OLD_SOURCE = a5.SOURCE_SHA
OLD_UI = a5.UI_SHA
OLD_MANIFEST = 'f6ffce8218ca4fff34d5ca31acf2a3e1604f3929113a0073bc80519e3027a158'
TERMINAL = {'succeeded','failed','cancelled'}
A6 = {'installer_sha256':'2d87e2bfac18099d9921674a2975604999fc7a79cddf36f5404cd293ff20c2d1',
    'installer_bytes':64359085,'kernel_sha256':'6960835b332728672183b2953c4003119ed743a721793dd6e21a7b66181607fc',
    'source_content_sha256':'886161d0a8c4f0bf3364fd6d0a9966630398bba6bfe27b84de9c5999a307acd4',
    'source_manifest_sha256':'110699237a7135eade0906145d7a5e0110300e14165fd7f5de9c955f545df6de',
    'ui_sha256':'02f41202e40b8ea85948e3a115e360b74d76ef7abad35b0ee5e1702a90bc9053',
    'extraction_sha256':'9f4570cfeab2d46a9d7ba38b18968995016c7185c0671a0011960a08203d9df1'}
WEB = {'app.js':A6['ui_sha256'],'index.html':'5825650304f572d45d6c21f898e4239a585a57ffc631cca2644cf26b702d441c',
    'style.css':'36e1dc9128ad1c5f81efd63381cc20c3382ccdf607cb19a04cbd5ed08dfbcdba'}


def digest_arg(value):
    if not isinstance(value,str) or re.fullmatch('[a-f0-9]{64}',value) is None:
        raise argparse.ArgumentTypeError('Use an approved lowercase SHA-256.')
    return value


def arguments(argv=None):
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--phase',choices=('preflight','repair','readchecks'),default='preflight')
    cli.add_argument('--apply',action='store_true')
    cli.add_argument('--installer',type=Path,required=True)
    cli.add_argument('--installer-sha256',type=digest_arg,required=True)
    cli.add_argument('--installer-bytes',type=int,required=True)
    cli.add_argument('--extraction',type=Path,required=True)
    cli.add_argument('--extraction-sha256',type=digest_arg,required=True)
    cli.add_argument('--kernel-sha256',type=digest_arg,required=True)
    cli.add_argument('--source-content-sha256',type=digest_arg,required=True)
    cli.add_argument('--source-manifest-sha256',type=digest_arg,required=True)
    cli.add_argument('--ui-sha256',type=digest_arg,required=True)
    cli.add_argument('--preflight-receipt',type=Path)
    cli.add_argument('--preflight-receipt-sha256',type=digest_arg)
    cli.add_argument('--repair-receipt',type=Path)
    cli.add_argument('--repair-receipt-sha256',type=digest_arg)
    cli.add_argument('--output',type=Path,required=True)
    cli.add_argument('--service-name',default=SERVICE)
    cli.add_argument('--install-root',type=Path,default=ROOT/'build/workstation/test-install/provider-a2/application files')
    cli.add_argument('--state-root',type=Path,default=ROOT/'build/workstation/test-install/provider-a2/state data')
    cli.add_argument('--allow-development-receipt',type=Path,action='append',default=[])
    args = cli.parse_args(argv)
    if args.installer_bytes <= 0:
        cli.error('The approved installer length must be positive.')
    if args.phase == 'preflight' and args.apply:
        cli.error('Preflight cannot apply changes.')
    if args.phase != 'preflight' and not args.apply:
        cli.error('Repair/readchecks require explicit --apply.')
    if args.phase == 'repair' and (args.preflight_receipt is None or args.preflight_receipt_sha256 is None):
        cli.error('Repair requires the passed preflight receipt and its reviewed SHA-256.')
    if args.phase == 'readchecks' and (args.repair_receipt is None or args.repair_receipt_sha256 is None):
        cli.error('Readchecks requires the passed repair receipt and its reviewed SHA-256.')
    return args


def snapshot(kernel):
    """One read-only SQL snapshot; public metadata and hashes, never auth rows."""
    result = {'tables':{},'auth_tables':{},'row_hashes':{},'journal_jobs':{},'journal_updates':{}}
    with closing(sqlite3.connect(kernel.resolve().joinpath('core.sqlite3').as_uri()+'?mode=ro',uri=True,timeout=10)) as db:
        db.execute('PRAGMA query_only=ON'); db.execute('BEGIN')
        result['schema'] = db.execute('SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name').fetchall()
        for name, in db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"):
            assert re.fullmatch('[A-Za-z_][A-Za-z_0-9]*',name)
            fields = db.execute('PRAGMA table_info("'+name+'")').fetchall()
            positions = [field[0] for field in sorted(fields,key=lambda field:field[5]) if field[5]]
            encoded, keyed = [],{}
            for row in db.execute('SELECT rowid,* FROM "'+name+'"'):
                values = row[1:]
                body = retained.canonical([retained.typed(value) for value in values])
                encoded.append(body)
                ident = [values[index] for index in positions] if positions else [row[0]]
                keyed[retained.canonical([retained.typed(value) for value in ident]).decode()] = hashlib.sha256(body).hexdigest()
                if name == 'product_jobs':
                    columns = {field[1]:values[field[0]] for field in fields}
                    result['journal_jobs'][columns['id']] = {key:columns[key] for key in ('id','owner','kind','status','attempts','created_at','updated_at')}
                    key=columns.get('idempotency_key')
                    result['journal_jobs'][columns['id']]['idempotency_key_sha256']=hashlib.sha256(key.encode()).hexdigest() if isinstance(key,str) else None
                elif name == 'product_updates':
                    seq,topic,payload,clock = values
                    value = json.loads(payload)
                    entry = {'seq':seq,'topic':topic,'committed_at':clock,'payload_sha256':hashlib.sha256(payload.encode()).hexdigest()}
                    if isinstance(value,dict):
                        job_id = value.get('id',value.get('job_id'))
                        if isinstance(job_id,str) and re.fullmatch('[a-f0-9]{32}',job_id):
                            entry['job_id'] = job_id
                            if (topic=='job' and set(value)=={'id','status'} and value['status'] in
                                    ('queued','running','succeeded','failed','cancelled','interrupted')):
                                entry['event'] = value
                            elif (topic=='data' and set(value)=={'job_id','kind'} and value['kind'] in
                                    ('local_explanation','explanation','export','statsbomb_context','import_public')):
                                entry['event'] = value
                    result['journal_updates'][str(seq)] = entry
            summary = {'rows':len(encoded),'sha256':hashlib.sha256(b'\n'.join(sorted(encoded))).hexdigest()}
            if name in a5.AUTH_TABLES:
                result['auth_tables'][name] = summary
            else:
                result['tables'][name] = summary; result['row_hashes'][name] = keyed
        result['counts'] = {provider:db.execute('SELECT COUNT(DISTINCT source_record_id) FROM connector_observations WHERE provider=?',(provider,)).fetchone()[0]
                            for provider in a5.EXPECTED_COUNTS if provider != 'openfootball'}
        result['counts']['openfootball'] = db.execute('SELECT COUNT(*) FROM public_fixture_records').fetchone()[0]
        result['sequences'] = dict(db.execute('SELECT name,seq FROM sqlite_sequence'))
        references = db.execute('SELECT sha256,raw_reference,bytes FROM connector_acquisitions').fetchall()
    result['raw_files'] = {}
    raw = kernel/'raw/connectors'
    for path in sorted(raw.iterdir()):
        assert path.is_file() and not path.is_symlink() and path.resolve().parent == raw.resolve() and path.suffix == '.payload'
        result['raw_files'][path.name] = {'bytes':path.stat().st_size,'sha256':prior.digest(path)}
    for sha,name,length in references:
        assert name == sha+'.payload' and name in result['raw_files'] and result['raw_files'][name] == {'bytes':length,'sha256':sha}
    return result


def compare(before,after,own_job=None):
    """Keep every old non-auth row; separately report unattributed app additions."""
    assert retained.canonical(before['schema']) == retained.canonical(after['schema']), 'Schema changed.'
    assert before['raw_files'] == after['raw_files'] and before['counts'] == after['counts'], 'Retained sources changed.'
    assert set(before['row_hashes']) == set(after['row_hashes'])
    for table,rows in before['row_hashes'].items():
        if table == 'sqlite_sequence':
            continue
        current = after['row_hashes'][table]
        assert all(current.get(key)==value for key,value in rows.items()), 'An old non-auth row changed: '+table
        if table not in ('product_jobs','product_updates'):
            assert current == rows, 'Unrelated retained table changed: '+table
    old_seq,new_seq = before['sequences'],after['sequences']
    assert {key:value for key,value in old_seq.items() if key!='product_updates'} == {key:value for key,value in new_seq.items() if key!='product_updates'}
    assert new_seq.get('product_updates',0) >= old_seq.get('product_updates',0)
    added_jobs = [value for key,value in after['journal_jobs'].items() if key not in before['journal_jobs']]
    added_events = [value for key,value in after['journal_updates'].items() if key not in before['journal_updates']]
    assert new_seq.get('product_updates',0)==max([old_seq.get('product_updates',0)]+[entry['seq'] for entry in added_events])
    if own_job:
        assert own_job not in before['journal_jobs'] and own_job in after['journal_jobs']
        own = after['journal_jobs'][own_job]
        assert own['kind']=='local_explanation' and own['status']=='succeeded' and own['attempts']==1
        key_hash=own.get('idempotency_key_sha256')
        assert isinstance(key_hash,str) and re.fullmatch('[a-f0-9]{64}',key_hash)
        assert [job['id'] for job in after['journal_jobs'].values() if job['owner']==own['owner'] and job.get('idempotency_key_sha256')==key_hash]==[own_job]
        events = [entry for entry in added_events if entry.get('job_id')==own_job]
        assert [(entry['topic'],entry.get('event')) for entry in events] == [
            ('job',{'id':own_job,'status':state}) for state in ('queued','running','succeeded')
        ]+[('data',{'job_id':own_job,'kind':'local_explanation'})]
    return {'all_old_non_auth_rows_unchanged':True,'own_job_id':own_job,'own_outbox_events':4 if own_job else 0,
        'concurrent_additions_origin':'unproven','other_jobs':[entry for entry in added_jobs if entry['id']!=own_job],
        'other_outbox_events':[entry for entry in added_events if entry.get('job_id')!=own_job],
        'auth_lifecycle_before':before['auth_tables'],'auth_lifecycle_after':after['auth_tables']}


class Journey(prior.Journey):
    _collect_secrets = a5.Journey._collect_secrets
    safe = a5.Journey.safe
    save = a5.Journey.save
    config_metadata = a5.Journey.config_metadata
    pairing = a5.Journey.pairing
    kernel_identity = a5.Journey.kernel_identity
    backup = a5.Journey.backup
    wait_ready = a5.Journey.wait_ready
    secret_absence = a5.Journey.secret_absence

    def load_endpoint(self):
        prior.Journey.load_endpoint(self)
        assert urlsplit(self.url).port==18746, 'Only the fixed owned API port is accepted.'

    def __init__(self,args):
        args.expected_kernel_sha256 = args.kernel_sha256
        args.expected_source_content_sha256 = args.source_content_sha256
        super().__init__(args)
        self.redact_only=set()
        retained.protect_directory(self.output)
        self.kernel = self.state/'kernel'
        self.match_id = a5.identity('fixture',a5.binding.PROVIDER,a5.binding.MATCH_ID)
        self.workstation = prior.read(self.state/'workstation.json')
        self._collect_secrets(self.workstation)
        self.own_job = None
        self.report.update(scope='Current-host A6 repair and retained package/3 acceptance only; one unconfigured UI job, no model/provider acquisition.',
            phase=args.phase,model_inference=False,model_settings_modified=False,provider_acquisition_jobs_submitted=0,
            explicit_service_restarts=0,installer_network_instrumented=False,wire_request_count_measured=False,
            downloads=None if args.phase=='repair' else False,
            download_scope='No provider acquisition requested; installer network activity is not instrumented.',
            source_bindings={path:prior.digest(ROOT/path) for path in ('tests/installation/context_ai_workstation.py',
                'tests/installation/statsbomb_context_workstation.py','tests/installation/local_ai_workstation.py',
                'tests/ui/statsbomb_retained_journey.py','scripts/probe_local_ai.py')})

    def call(self,path,body=None,*,timeout=15,key=None,auth=True):
        headers = {'Content-Type':'application/json'}
        if auth: headers['Authorization'] = 'Bearer '+self.token
        if key is not None: headers['Idempotency-Key'] = key
        request = Request(self.url+prior.API+path,data=prior.canonical(body) if body is not None else None,
            headers=headers,method='POST' if body is not None else 'GET')
        try:
            response = self.opener.open(request,timeout=timeout)
        except HTTPError as error:
            response = error
        try:
            raw = response.read(128*1024+1)
            assert len(raw)<=128*1024 and all(secret.encode() not in raw for secret in self.private
                if len(secret)>=8 and secret not in self.redact_only)
            return response.code,json.loads(raw)
        finally:
            response.close()

    def pins(self):
        return {name:str(getattr(self.args,name).resolve()) if name in ('installer','extraction') else str(getattr(self.args,name))
            for name in ('installer','installer_sha256','installer_bytes','extraction',
                         'extraction_sha256','kernel_sha256','source_content_sha256','source_manifest_sha256','ui_sha256')}

    def artifact(self):
        args = self.args
        assert all(getattr(args,name)==value for name,value in A6.items()), 'A6 approval pins differ.'
        installer,extraction = args.installer.resolve(),args.extraction.resolve()
        assert installer == ROOT/'dist/connections/workstation-a6/DRAGONHYDRA-0.4.1-dev.1-Workstation-win-x64-Setup.exe'
        assert extraction == installer.parent/'EXTRACTION-VERIFICATION.json'
        assert installer.is_file() and installer.stat().st_size==args.installer_bytes and prior.digest(installer)==args.installer_sha256
        assert prior.digest(extraction)==args.extraction_sha256
        proof = prior.read(extraction)
        assert proof['passed'] and proof['artifact_extracted_not_executed']
        assert proof['artifact']['sha256']==args.installer_sha256 and proof['artifact']['bytes']==args.installer_bytes
        assert Path(proof['artifact']['path']).resolve()==installer
        assert proof['kernel_binary_sha256']==args.kernel_sha256 and proof['kernel_source_content_sha256']==args.source_content_sha256
        manifest_path=ROOT/'build/connections/payload-20261031-a6/SOURCE-MANIFEST.json'
        assert prior.digest(manifest_path)==args.source_manifest_sha256
        manifest=prior.read(manifest_path)
        assert manifest['content_sha256']==args.source_content_sha256
        host_sources={entry['path']:entry['sha256'] for entry in manifest['files'] if entry['path'].startswith('src/dragonhydra/')}
        assert all(prior.digest(ROOT/name)==fingerprint for name,fingerprint in host_sources.items())
        self.report['source_bindings'].update(host_sources)
        self.report['host_product_source_binding']={'manifest':str(manifest_path.relative_to(ROOT)),
            'sha256':args.source_manifest_sha256,'source_content_sha256':args.source_content_sha256,
            'files_verified':len(host_sources),'role':'Read-only independent package reconstruction; installed API is verified separately.'}
        self.report['pins'] = self.pins()

    def installed_identity(self,*,old=False):
        kernel,source,ui,manifest = ((OLD_KERNEL,OLD_SOURCE,OLD_UI,OLD_MANIFEST) if old else
            (self.args.kernel_sha256,self.args.source_content_sha256,self.args.ui_sha256,self.args.source_manifest_sha256))
        assert prior.digest(self.install/'server/DRAGONHYDRA-Server.exe')==kernel
        assert prior.digest(self.install/'server/SOURCE-MANIFEST.json')==manifest
        if not old:
            for name,fingerprint in WEB.items():
                assert prior.digest(self.install/'server/_internal/dragonhydra/resources/web'/name)==fingerprint
        process=self.kernel_identity()
        listeners=self.powershell("""
        @{listeners=@(Get-NetTCPConnection -State Listen -LocalPort 18746|ForEach-Object {
            @{address=$_.LocalAddress;port=$_.LocalPort;pid=$_.OwningProcess}
        })}|ConvertTo-Json -Depth 4
        """)['listeners']
        assert listeners==[{'address':'127.0.0.1','port':18746,'pid':process['pid']}], 'API listener is not the owned LocalService kernel.'
        code,system = self.call('/system')
        assert code==200 and system['backend']=='sqlite' and system['build']['source_content_sha256']==source
        with self.opener.open(self.url+'/app.js',timeout=15) as response: raw=response.read(2*1024*1024+1)
        assert len(raw)<=2*1024*1024 and hashlib.sha256(raw).hexdigest()==ui
        return {'kernel_sha256':kernel,'source_content_sha256':source,'ui_sha256':ui,'source_manifest_sha256':manifest,
            'process':process,'api_listener':listeners}

    def receipt(self,path,phase):
        path = path.resolve()
        assert path.is_relative_to(ROOT/'build/workstation/evidence')
        expected = self.args.preflight_receipt_sha256 if phase=='preflight' else self.args.repair_receipt_sha256
        assert prior.digest(path)==expected, 'Reviewed prior receipt changed.'
        proof = prior.read(path)
        assert proof['passed'] and proof['phase']==phase and proof['pins']==self.pins()
        assert proof['source_bindings']==self.report['source_bindings']
        assert proof['service_name']==SERVICE and Path(proof['install_root']).resolve()==self.install and Path(proof['state_root']).resolve()==self.state
        assert proof['context_before']==self.context_before
        self.report[phase+'_receipt'] = {'path':str(path.relative_to(ROOT)),'sha256':prior.digest(path)}
        return proof

    def context_reference(self):
        path='/matches/'+self.match_id
        code,context=self.call(path+'/source-context')
        assert code==200 and context['availability']=='available'
        assert context['context_parent_observation_id']==context['parent_observation_id']
        projection=context['projection']
        assert projection['event_summary']['row_count']==4407
        assert {team['team_id']:len(team['lineup']) for team in projection['squads']}=={771:24,779:26}
        view=prior.helper.readonly_product(self.kernel)
        package=local_ai.build_context_package(view,self.match_id,context['context_record_id'])
        assert package['event']['score']=={'home':3,'away':3}
        assert package['context_summary']['event_rows']==4407
        reference={'id':context['context_record_id'],'sha256':package['evidence']['C1']['record_sha256'],
            'parent_id':context['parent_observation_id'],'documents':package['evidence']['C1']['documents'],
            'context_summary':package['context_summary'],'package_sha256':package['package_sha256']}
        return reference,package

    def preflight(self):
        self.artifact(); self.owned=self.service()
        self.config_before=self.config_metadata(); self.pairing_before=self.pairing()
        self.original_config_hash=prior.digest(self.state/'workstation.json')
        self.report['installed_before']=self.installed_identity(old=self.args.phase!='readchecks')
        self.baseline=self.configuration()
        assert self.baseline=={'endpoint':'','configured':False,'endpoint_source':'none','credential_source':'none'}
        self.passive_health(False,'blank configuration baseline')
        self.before=snapshot(self.kernel)
        assert self.before['counts']==a5.EXPECTED_COUNTS and sum(self.before['counts'].values())==1221
        assert self.before['tables']['connector_observations']['rows']==461
        assert self.before['tables']['cognitive_records']['rows']==self.before['tables']['cognitive_receipts']['rows']==1
        assert not [job for job in self.before['journal_jobs'].values() if job['status'] not in TERMINAL]
        with closing(sqlite3.connect((self.kernel/'core.sqlite3').as_uri()+'?mode=ro',uri=True)) as db:
            assert not db.execute('SELECT 1 FROM connector_settings WHERE interval_seconds>0').fetchone()
        self.context_before,self.package3=self.context_reference()
        self.before_originals=self.originals()
        self.c7_hash=prior.digest(ROOT/'dist/workstation/0.4.1-dev.1/DRAGONHYDRA-0.4.1-dev.1-Workstation-win-x64-Setup.exe')
        assert self.c7_hash=='a2a1cde06f7a9fbc86e1e564dc5aabb8984368bcf2c2d919f2f492568bd67d97'
        self.report.update(before=self.before,context_before=self.context_before,pairing_before=self.pairing_before,
            ports_before=self.config_before,configuration_before=self.baseline,originals_before=self.before_originals,
            preserved_c7_installer_sha256=self.c7_hash,workstation_configuration_sha256=self.original_config_hash)
        if self.args.phase=='repair':
            earlier=self.receipt(self.args.preflight_receipt,'preflight')
            self.report['since_preflight']=compare(earlier['before'],self.before)
        elif self.args.phase=='readchecks':
            earlier=self.receipt(self.args.repair_receipt,'repair')
            assert earlier['applied']
            self.report['since_repair']=compare(earlier['after_repair'],self.before)
        self.backup(); self.save('before.json',self.report)
        self.passed('Pinned artifact/service, 1221 records/461 observations, exact retained C1, idle worker, blank model configuration, pairing and protected backup verified')

    def package_reads(self):
        before=snapshot(self.kernel); path='/matches/'+self.match_id
        code,default=self.call(path+'/analysis-package')
        assert code==200 and default['schema_version']==local_ai.SCHEMA
        route=path+'/analysis-package?'+urlencode({'context_record_id':self.context_before['id']})
        assert self.call(route)==(200,self.package3)
        assert self.call(route,auth=False)[0]==401
        assert self.call(path+'/analysis-package?context_record_id=latest')[0]==422
        assert self.call(path+'/analysis-package?context_record_id=source_context:'+'0'*64)[0]==409
        after=snapshot(self.kernel)
        self.report.setdefault('read_check_deltas',[]).append(compare(before,after))
        assert self.call(path+'/analysis-package')[1]==default
        self.package2=default
        self.passed('Installed authenticated default/2 and exact C1 /3 reads agree with retained bytes; invalid read selectors are rejected without POST')

    def repair(self):
        assert ctypes.windll.shell32.IsUserAnAdmin()
        current=self.service()
        self.report.update(installer_invocation_requested=True,software_installations=None)
        self.save('repair-command.json',{'installer':str(self.args.installer),'sha256':self.args.installer_sha256,
            'arguments':'/S /SERVICE='+SERVICE+' /STATE="'+str(self.state)+'" /D='+str(self.install),
            'scope':'One exact owned in-place repair; /D last; no repeat/uninstall/explicit restart.'})
        outcome=self.powershell("""
        $s=Get-CimInstance Win32_Service -Filter ("Name='"+$v.name+"'");
        if(-not $s -or $s.PathName -cne $v.expected -or $s.State -ne 'Running' -or $s.StartName -cne $v.account){throw 'Exact repair service ownership changed.'};
        if((Get-FileHash -LiteralPath $v.installer -Algorithm SHA256).Hash.ToLowerInvariant() -ne $v.sha){throw 'Approved installer changed.'};
        $arguments='/S /SERVICE='+$v.name+' /STATE="'+$v.state+'" /D='+$v.install;
        $p=Start-Process -FilePath $v.installer -ArgumentList $arguments -WindowStyle Hidden -PassThru;
        $done=$p.WaitForExit(420000);
        @{pid=$p.Id;completed=$done;exit_code=$(if($done){$p.ExitCode}else{$null});automatic_repeat=$false}|ConvertTo-Json
        """,{'name':SERVICE,'expected':current['path'],'account':current['account'],'installer':str(self.args.installer.resolve()),
               'sha':self.args.installer_sha256,'state':str(self.state),'install':str(self.install)},timeout=440)
        self.report['installer_invocation']=outcome; self.save('installer-outcome.json',outcome)
        assert outcome['completed'] and outcome['exit_code']==0
        self.wait_ready(); self.service()
        self.report['installed_after']=self.installed_identity()
        assert self.context_reference()[0]==self.context_before
        self.package_reads()
        after=snapshot(self.kernel)
        self.report.update(after_repair=after,repair_delta=compare(self.before,after),software_installations=True)
        self.passed('One hidden A6 repair retained exact sources/context/schema/pairing/ports and loaded the pinned new kernel/source/UI')

    def browser(self):
        from playwright.sync_api import expect,sync_playwright
        profile=self.output/'browser-profile'; profile.mkdir(); retained.protect_directory(profile)
        blocked,errors,posts=[],[],[]
        path=prior.API+'/matches/'+self.match_id+'/local-explanations'
        try:
            with sync_playwright() as playwright:
                browser=playwright.chromium.launch_persistent_context(str(profile),executable_path=str(retained.EDGE),
                    headless=True,accept_downloads=True,viewport={'width':1500,'height':1100},service_workers='block')
                try:
                    def guard(route):
                        request=route.request; parsed=urlsplit(request.url)
                        if parsed.scheme+'://'+parsed.netloc!=self.url:
                            blocked.append({'method':request.method,'path':parsed.path}); route.abort(); return
                        if request.method in ('GET','HEAD') or (request.method=='POST' and parsed.path==prior.API+'/session'):
                            route.continue_(); return
                        if request.method=='POST' and parsed.path==path and not posts:
                            body=request.post_data_json; key=request.headers.get('idempotency-key')
                            assert body=={'context_record_id':self.context_before['id']} and isinstance(key,str) and 1<=len(key)<=128
                            posts.append({'body':body,'key':key}); self.private.append(key); self.redact_only.add(key)
                            self.save('ui-submit-intent.json',{'body':body,'idempotency_key_sha256':hashlib.sha256(key.encode()).hexdigest(),
                                'authorized_ui_post_attempts':1,'automatic_retry':False})
                            route.continue_(); return
                        blocked.append({'method':request.method,'path':parsed.path}); route.abort()
                    browser.route('**/*',guard)
                    page=browser.pages[0] if browser.pages else browser.new_page()
                    page.on('pageerror',lambda error:errors.append(self.safe(error)))
                    page.goto(self.url+'/#token='+quote(self.token,safe=''),wait_until='domcontentloaded')
                    expect(page.locator('#service-state')).to_contain_text('Server ready')
                    page.goto(self.url+'/#match/'+self.match_id,wait_until='domcontentloaded')
                    page.get_by_role('tab',name='Analysis',exact=True).click()
                    panel=page.locator('[data-context-ai]')
                    expect(panel).to_contain_text('4407 retained event rows')
                    expect(panel).to_contain_text('Argentina: 26 squad entries')
                    expect(panel).to_contain_text('France: 24 squad entries')
                    for action in ('explain','local-explain','configure-local-model','export-sports-package','local-explain-context','export-context-package'):
                        expect(page.locator('[data-action="'+action+'"]')).to_be_enabled()
                    panel.screenshot(path=str(self.output/'installed-source-counts.png'))
                    for action,name,expected in (('export-sports-package','default-package.json',self.package2),
                                                 ('export-context-package','context-package.json',self.package3)):
                        with page.expect_download() as download:
                            page.locator('[data-action="'+action+'"]').click()
                        target=self.output/name; download.value.save_as(str(target)); protect(target)
                        assert prior.read(target)==expected
                    assert self.configuration()==self.baseline
                    with page.expect_response(lambda response:response.request.method=='POST' and urlsplit(response.url).path==path) as queued:
                        page.locator('[data-action="local-explain-context"]').click()
                    assert queued.value.status==202
                    job=queued.value.json(); self.own_job=job['id']; self.report['own_job_id']=self.own_job
                    assert job['idempotency_key']==posts[0]['key']
                    self.save('queued-job.json',job)
                    deadline=time.monotonic()+90
                    while time.monotonic()<deadline:
                        _,job=self.call('/jobs/'+self.own_job)
                        if job['status'] in TERMINAL|{'interrupted'}: break
                        page.wait_for_timeout(150)
                    assert job['status']=='succeeded' and job['attempts']==1
                    result=job['result']; evidence=self.package3['evidence']; context=evidence['C1']
                    assert job['payload']=={'package':self.package3}
                    assert result['kind']=='deterministic' and result['local_ai']['code']=='AI_NOT_CONFIGURED'
                    assert result['input_manifest']==[evidence['E1']['id'],context['id'],*(context['documents'][role]['id'] for role in ('events','lineups'))]
                    assert result['package_sha256']==self.package3['package_sha256']
                    assert result['observations']==[self.package3['allowed_facts'][0]['observation']]
                    assert len(result['evidence'])==1 and result['evidence'][0]['id']==evidence['E1']['id']
                    assert len(posts)==1
                    code,replay=self.call('/matches/'+self.match_id+'/local-explanations',posts[0]['body'],key=posts[0]['key'])
                    assert code==202 and replay['id']==self.own_job and replay['result']==result
                    expect(page.locator('#explanation-result')).to_contain_text('DETERMINISTIC EVIDENCE SUMMARY')
                    expect(page.locator('#explanation-result')).to_contain_text('AI_NOT_CONFIGURED')
                    expect(page.locator('#explanation-result .explanation-citation')).to_have_count(1)
                    page.locator('#explanation-result').screenshot(path=str(self.output/'installed-context-fallback.png'))
                    self.save('completed-job.json',job)
                    assert not blocked and not errors
                    self.report['browser']={'one_ui_submission':True,'same_key_replay_same_job':True,
                        'idempotency_key_sha256':hashlib.sha256(posts[0]['key'].encode()).hexdigest(),
                        'blocked_requests':blocked,'page_errors':errors,'package_downloads':['default-package.json','context-package.json'],
                        'fallback_citations':1,'input_manifest_ids':4,'real_model_inference':False}
                finally:
                    browser.close()
        finally:
            assert profile.resolve().parent==self.output and profile.resolve().is_relative_to(ROOT)
            shutil.rmtree(profile)
            self.report['temporary_browser_profile_removed']=not profile.exists()
        self.passed('Installed Edge exports default/2 and exact real C1 /3, then one unconfigured UI job and idempotent replay preserve four input IDs with one parent citation')

    def execute(self):
        try:
            self.preflight()
            if self.args.phase=='repair': self.repair()
            elif self.args.phase=='readchecks':
                self.package_reads(); self.browser()
                self.report['after_readchecks']=snapshot(self.kernel)
                self.report['readchecks_delta']=compare(self.before,self.report['after_readchecks'],self.own_job)
            assert self.config_metadata()==self.config_before and self.pairing()==self.pairing_before
            assert prior.digest(self.state/'workstation.json')==self.original_config_hash
            assert self.configuration()==self.baseline and self.context_reference()[0]==self.context_before
            self.passive_health(False,'final blank configuration')
            self.check_originals(); self.report['final_owned_service']=self.service()
            self.report['passed']=True
        except Exception:
            self.report['error']=self.safe(traceback.format_exc())
        finally:
            if hasattr(self,'before'):
                try:
                    final=snapshot(self.kernel)
                    self.report['final_retained_snapshot']=final
                    self.report['final_preservation']=compare(self.before,final,self.own_job if self.report['passed'] else None)
                    self.report['attempted_own_job_id']=self.own_job
                except Exception:
                    self.report['final_preservation_error']=self.safe(traceback.format_exc()); self.report['passed']=False
            if hasattr(self,'before_originals') and 'originals_after' not in self.report:
                try: self.check_originals()
                except Exception:
                    self.report['originals_preservation_error']=self.safe(traceback.format_exc()); self.report['passed']=False
            try: self.report['final_owned_service']=self.service()
            except Exception:
                self.report['final_owned_service_error']=self.safe(traceback.format_exc()); self.report['passed']=False
            self.report.update(finished_at=prior.stamp(),check_groups=len(self.checks),no_automatic_retry=True,
                model_inference=False,settings_edits=False,explicit_service_restarts=0)
            self.save('journey.json',self.report)
            if not self.secret_absence(): self.report['passed']=False
            self.save('journey.json',self.report)
        print(json.dumps({'passed':self.report['passed'],'phase':self.args.phase,'applied':self.args.apply,
            'groups':len(self.checks),'error':self.report.get('error'),'evidence':str(self.output/'journey.json')}),flush=True)
        return 0 if self.report['passed'] else 1


def main():
    args=arguments()
    if os.name!='nt' or sys.flags.optimize: raise SystemExit('Use the verified Windows runtime with assertions enabled.')
    try: return Journey(args).execute()
    except Exception:
        print(json.dumps({'passed':False,'phase':args.phase,'error':'GUARDED_VERIFIER_SETUP_FAILED'}),flush=True)
        return 1


if __name__=='__main__': raise SystemExit(main())
