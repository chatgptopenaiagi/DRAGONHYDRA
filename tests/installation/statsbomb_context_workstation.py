"""Pinned two-phase A5 r2 proof for the existing isolated A2 workstation.

Default execution is read-only preflight plus private evidence. --apply repair
permits ONE hidden in-place installer invocation. --apply context permits ONE
explicit context POST, read-only browser checks, and ONE restart of the exact
owned test service. No model/configuration changes or ordinary source resync.
No automatic repeat POST, repair, provider retry, uninstall or rollback occurs.
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
import secrets
import shutil
import sqlite3
import subprocess
import sys
import time
import traceback
from types import SimpleNamespace
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import Request


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'src'))
SERVICE = 'DragonhydraProvidersA2Test'
INSTALLER = ROOT/'dist/connections/workstation-a5-r2/DRAGONHYDRA-0.4.1-dev.1-Workstation-win-x64-Setup.exe'
INSTALLER_SHA = 'b8bcc4d7ee26ea7db2f163fd20fecdbd95349ef5ac085d40375f43e5918d7544'
INSTALLER_BYTES = 64_341_255
KERNEL_SHA = 'dac72b5eb5a5d2793e884763c14c41c91830c4cc0b5dd6a23d0dc456373b38a7'
SOURCE_SHA = '7251f7fdded28f4f2af354313c0232a6d36cb8121d0eea746a9b3922b466566a'
UI_SHA = 'd6fb940c2a1f637571f6995540312cb4cf82c9abe207242d438246292b939bf2'
A4_KERNEL_SHA = '712fedbde1b992d247e5ab01511d069ba0f608df419e37dfd30d9f6701b872ed'
A4_SOURCE_SHA = '8b3e7e0e440b9f4d090517237724999bcd824d86f460663e65d940c9c1d20fd5'
EXTRACTION = ROOT/'dist/connections/workstation-a5-r2/EXTRACTION-VERIFICATION.json'
AUTH_TABLES = {'product_sessions','product_bridge_nonces'}
EXPECTED_COUNTS = {'openfootball':760,'football-data-couk':380,'statsbomb':64,'cricsheet':17,
    'nflverse':0,'moneypuck':0,'api-football':0,'the-odds-api':0,'sportmonks':0,'football-data-org':0}


def module(name,path):
    spec = importlib.util.spec_from_file_location(name,path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


# Reuse verified service ownership, API, restart and original-instance checks.
prior = module('_workstation_service_patterns',ROOT/'tests/installation/local_ai_workstation.py')
retained = module('_retained_browser_patterns',ROOT/'tests/ui/statsbomb_retained_journey.py')
from dragonhydra.connectors import statsbomb_context as binding, statsbomb_context_parser as parser
from dragonhydra.connectors import statsbomb_context_view as view
from dragonhydra.cognition import memory
from dragonhydra.product import identity
from dragonhydra.server import protect


def snapshot(kernel):
    result = retained.snapshot(kernel)
    result['row_hashes'] = {}
    with closing(sqlite3.connect((kernel/'core.sqlite3').as_uri()+'?mode=ro',uri=True)) as db:
        db.execute('PRAGMA query_only=ON'); db.execute('BEGIN')
        result['schema'] = db.execute('SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name').fetchall()
        for name in result['tables']:
            assert re.fullmatch('[A-Za-z_][A-Za-z_0-9]*',name)
            fields = db.execute('PRAGMA table_info("'+name+'")').fetchall()
            keys = [row[0] for row in sorted(enumerate(fields),key=lambda pair:pair[1][5]) if row[1][5]]
            rows = {}
            for row in db.execute('SELECT rowid,* FROM "'+name+'"'):
                values = row[1:]
                key = [values[index] for index in keys] if keys else [row[0]]
                encoded_key = retained.canonical([retained.typed(value) for value in key]).decode()
                rows[encoded_key] = hashlib.sha256(retained.canonical([retained.typed(value) for value in values])).hexdigest()
            result['row_hashes'][name] = rows
        result['counts'] = {provider:db.execute('SELECT COUNT(DISTINCT source_record_id) FROM connector_observations WHERE provider=?',(provider,)).fetchone()[0]
                            for provider in EXPECTED_COUNTS if provider != 'openfootball'}
        result['counts']['openfootball'] = db.execute('SELECT COUNT(*) FROM public_fixture_records').fetchone()[0]
        result['active_jobs'] = db.execute("SELECT id,kind,status FROM product_jobs WHERE status NOT IN ('succeeded','failed','cancelled')").fetchall()
        result['scheduled_sources'] = db.execute('SELECT provider,interval_seconds FROM connector_settings WHERE interval_seconds>0').fetchall()
        result['sequences'] = dict(db.execute('SELECT name,seq FROM sqlite_sequence'))
    return result


def same_rows(before,after,*,growth=()):
    for table,rows in before['row_hashes'].items():
        if table == 'sqlite_sequence':
            continue
        current = after['row_hashes'][table]
        assert all(current.get(key) == value for key,value in rows.items()), 'An existing retained row changed: '+table
        if table not in growth:
            assert current == rows, 'An unrelated table grew: '+table


class Journey(prior.Journey):
    def __init__(self,args):
        args.expected_kernel_sha256 = KERNEL_SHA
        args.expected_source_content_sha256 = SOURCE_SHA
        super().__init__(args)
        retained.protect_directory(self.output)
        self.kernel = self.state/'kernel'
        self.match_id = identity('fixture',binding.PROVIDER,binding.MATCH_ID)
        self.started_context_job = None
        self.workstation = prior.read(self.state/'workstation.json')
        self._collect_secrets(self.workstation)
        self.report.update(phase=args.phase,scope='Pinned installed A5 r2 repair/context proof; only the existing isolated A2 LocalService workstation.',
            downloads=False,model_inference=False,model_settings_modified=False,ordinary_provider_resync=False,
            installer={'path':str(INSTALLER.relative_to(ROOT)),'sha256':INSTALLER_SHA,'bytes':INSTALLER_BYTES},
            expected_kernel_sha256=KERNEL_SHA,expected_source_content_sha256=SOURCE_SHA,expected_ui_sha256=UI_SHA,
            wire_request_count_measured=False,wire_request_count=None,automatic_followup_job=False)
        self.report['source_bindings'] = {'harness_sha256':prior.digest(Path(__file__)),
            'service_pattern_helper_sha256':prior.digest(ROOT/'tests/installation/local_ai_workstation.py'),
            'retained_pattern_helper_sha256':prior.digest(ROOT/'tests/ui/statsbomb_retained_journey.py')}
        self.report['download_scope'] = 'Provider context payloads only; installer network activity is not instrumented.'
        self.report['provider_payload_downloads'] = False

    def _collect_secrets(self,value):
        if isinstance(value,dict):
            for key,item in value.items():
                if re.search(r'(password|secret|token|credential)$',key,re.I) and isinstance(item,str) and len(item)>=8:
                    self.private.append(item)
                else:
                    self._collect_secrets(item)
        elif isinstance(value,list):
            for item in value:
                self._collect_secrets(item)

    def safe(self,value):
        result = str(value)
        for secret in sorted(set(self.private),key=len,reverse=True):
            for representation in (secret,json.dumps(secret,ensure_ascii=False)[1:-1],quote(secret,safe='')):
                result = result.replace(representation,'[REDACTED]')
        return result

    def save(self,name,value):
        path = self.output/name
        assert path.resolve().is_relative_to(self.output)
        path.write_text(self.safe(json.dumps(value,ensure_ascii=False,allow_nan=False,indent=2))+'\n',encoding='utf-8')
        protect(path)

    def config_metadata(self):
        config = prior.read(self.state/'workstation.json')
        self._collect_secrets(config)
        metadata = {key:config[key] for key in ('service_name','install_root','state_root','api_port','web_port','database_port','kernel_backend')}
        assert metadata == {'service_name':SERVICE,'install_root':str(self.install),'state_root':str(self.state),
            'api_port':18746,'web_port':18747,'database_port':18748,'kernel_backend':'sqlite'}
        return metadata

    def pairing(self):
        result = {}
        # The kernel token is deliberately LocalService/SYSTEM-only. Never
        # read it, take ownership or change its ACL; the owner-readable client
        # token plus successful authenticated calls prove retained pairing.
        for relative in ('client/local-session.json',):
            path = self.state/relative
            if path.is_file():
                loaded = prior.read(path)
                if isinstance(loaded.get('token'),str):
                    self.private.append(loaded['token'])
                result[relative] = prior.digest(path)
        assert 'client/local-session.json' in result
        return result

    def kernel_identity(self):
        endpoint = prior.read(self.kernel/'endpoint.json')
        result = self.powershell("""
        $p=Get-CimInstance Win32_Process -Filter ('ProcessId='+$v.pid);
        if(-not $p){throw 'Exact kernel PID missing.'};
        $owner=Invoke-CimMethod -InputObject $p -MethodName GetOwnerSid;
        @{pid=$p.ProcessId;executable=$p.ExecutablePath;sid=$owner.Sid;owner_result=$owner.ReturnValue}|ConvertTo-Json
        """,{'pid':endpoint['pid']})
        assert result['owner_result'] == 0 and result['sid'] == 'S-1-5-19'
        assert Path(result['executable']).resolve() == self.install/'server/DRAGONHYDRA-Server.exe'
        return result

    def artifact(self):
        assert self.args.installer.resolve() == INSTALLER and self.args.installer_sha256 == INSTALLER_SHA
        assert INSTALLER.is_file() and INSTALLER.stat().st_size == INSTALLER_BYTES and prior.digest(INSTALLER) == INSTALLER_SHA
        assert EXTRACTION.is_file(), 'Passed archive extraction receipt is required.'
        proof = prior.read(EXTRACTION)
        assert proof['passed'] and proof['artifact_extracted_not_executed'] and not proof['installed']
        assert proof['artifact']['sha256'] == INSTALLER_SHA and proof['artifact']['bytes'] == INSTALLER_BYTES
        assert Path(proof['artifact']['path']).resolve() == INSTALLER
        assert proof['kernel_binary_sha256'] == KERNEL_SHA and proof['kernel_source_content_sha256'] == SOURCE_SHA
        self.report['extraction'] = {'path':str(EXTRACTION.relative_to(ROOT)),'sha256':prior.digest(EXTRACTION),
            'kernel_files_verified':proof['kernel_files_verified'],'source_files_verified':proof['source_files_verified']}
        return proof

    def installed_identity(self,*,a4=False):
        kernel_sha,source_sha = (A4_KERNEL_SHA,A4_SOURCE_SHA) if a4 else (KERNEL_SHA,SOURCE_SHA)
        assert prior.digest(self.install/'server/DRAGONHYDRA-Server.exe') == kernel_sha
        _,system = self.call('/system')
        assert system['backend'] == 'sqlite' and system['build']['source_content_sha256'] == source_sha
        if not a4:
            with self.opener.open(self.url+'/app.js',timeout=15) as response:
                raw = response.read(2*1024*1024+1)
            assert len(raw) <= 2*1024*1024 and hashlib.sha256(raw).hexdigest() == UI_SHA
        return {'kernel_sha256':kernel_sha,'source_content_sha256':source_sha,'ui_sha256':UI_SHA if not a4 else None,
                'process':self.kernel_identity()}

    def backup(self):
        path = self.output/'before-core.sqlite3'
        with closing(sqlite3.connect((self.kernel/'core.sqlite3').as_uri()+'?mode=ro',uri=True)) as original, \
             closing(sqlite3.connect(path)) as copy:
            original.execute('BEGIN')
            original.backup(copy)
            assert copy.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        protect(path)
        self.report['private_baseline_backup'] = {'file':path.name,'sha256':prior.digest(path)}

    def read_routes(self):
        before = snapshot(self.kernel)
        path = '/matches/'+self.match_id
        for endpoint in ('/source-context','/source-events?offset=0&limit=200'):
            _,value = self.call(path+endpoint)
            assert value['supported'] and value['availability'] == 'not_requested'
            assert not any(key in value for key in ('projection','items','total'))
            try:
                self.opener.open(self.url+prior.API+path+endpoint,timeout=10).close()
                raise AssertionError('Unauthenticated context read accepted.')
            except HTTPError as error:
                assert error.code == 401; error.close()
        for authenticated in (False,True):
            headers = {'Content-Type':'application/json'}
            if authenticated:
                headers['Authorization'] = 'Bearer '+self.token
            request = Request(self.url+prior.API+path+'/source-context',data=b'{"forbidden":true}',headers=headers,method='POST')
            try:
                self.opener.open(request,timeout=10).close()
                raise AssertionError('Invalid context write accepted.')
            except HTTPError as error:
                assert error.code == (422 if authenticated else 401); error.close()
        after = snapshot(self.kernel)
        assert after == before and not any(name.startswith('cognitive_') for name in after['tables'])
        self.passed('Three authenticated context routes reject unauthorized/invalid writes and reads create no context schema or rows')

    def preflight(self):
        self.artifact()
        self.owned = self.service()
        self.config_before = self.config_metadata()
        self.pairing_before = self.pairing()
        self.original_config_hash = prior.digest(self.state/'workstation.json')
        self.baseline = self.configuration()
        assert self.baseline == {'endpoint':'','configured':False,'endpoint_source':'none','credential_source':'none'}
        self.passive_health(False,'empty installed baseline')
        self.before = snapshot(self.kernel)
        assert self.before['counts'] == EXPECTED_COUNTS and sum(self.before['counts'].values()) == 1221
        assert self.before['tables']['connector_observations']['rows'] == 461
        assert not self.before['active_jobs'] and not self.before['scheduled_sources'], 'Active jobs or scheduled sources could acquire unrelated data.'
        assert not any(name.startswith('cognitive_') for name in self.before['tables']), 'This proof requires an initial no-context schema.'
        with closing(sqlite3.connect((self.kernel/'core.sqlite3').as_uri()+'?mode=ro',uri=True)) as db:
            assert not db.execute("SELECT 1 FROM product_jobs WHERE kind='statsbomb_context'").fetchone(), 'A previous context job requires review; this harness will not submit a follow-up.'
            assert not db.execute("SELECT 1 FROM connector_attempts WHERE operation='statsbomb_context'").fetchone()
        self.before_originals = self.originals()
        c7 = ROOT/'dist/workstation/0.4.1-dev.1/DRAGONHYDRA-0.4.1-dev.1-Workstation-win-x64-Setup.exe'
        self.c7_hash = prior.digest(c7)
        assert self.c7_hash == 'a2a1cde06f7a9fbc86e1e564dc5aabb8984368bcf2c2d919f2f492568bd67d97'
        self.report['installed_before'] = self.installed_identity(a4=self.args.phase == 'repair')
        self.report.update(before=self.before,pairing_before=self.pairing_before,ports_before=self.config_before,
            originals_before=self.before_originals,preserved_c7_installer_sha256=self.c7_hash,
            configuration_before=self.baseline,workstation_configuration_sha256=self.original_config_hash)
        if self.args.phase == 'context':
            receipt_path = self.args.repair_receipt.resolve()
            assert receipt_path.is_relative_to(ROOT/'build/workstation/evidence')
            repair = prior.read(receipt_path)
            assert repair['passed'] and repair['applied'] and repair['phase'] == 'repair'
            assert repair['installer']['sha256'] == INSTALLER_SHA and repair['expected_kernel_sha256'] == KERNEL_SHA
            assert repair['before']['tables'] == self.before['tables'] and repair['before']['raw_files'] == self.before['raw_files']
            self.report['repair_receipt'] = {'path':str(receipt_path.relative_to(ROOT)),'sha256':prior.digest(receipt_path)}
            self.read_routes()
        self.backup()
        self.save('before.json',self.report)
        self.passed('Pinned A2 LocalService, 1221 records/461 observations, idle worker, ports/pairing, empty AI configuration and private baseline verified')

    def wait_ready(self):
        deadline = time.monotonic()+150
        while time.monotonic()<deadline:
            try:
                self.load_endpoint()
                if prior.read(self.state/'status.json')['stage'] == 'ready' and self.call('/health/ready')[0] == 200:
                    return
            except (OSError,ValueError,URLError,TimeoutError):
                pass
            time.sleep(.3)
        raise TimeoutError('OWNED_WORKSTATION_NOT_READY')

    def repair(self):
        assert ctypes.windll.shell32.IsUserAnAdmin(), 'Elevated ownership verification is required before installer invocation.'
        current = self.service()
        command = {'installer':str(INSTALLER),'sha256':INSTALLER_SHA,
            'arguments':'/S /SERVICE='+SERVICE+' /STATE="'+str(self.state)+'" /D='+str(self.install),
            'scope':'Only the existing exact isolated A2 installation; /D is last; hidden process; no uninstall or automatic repeat.'}
        self.save('repair-command.json',command)
        outcome = self.powershell("""
        $s=Get-CimInstance Win32_Service -Filter ("Name='"+$v.name+"'");
        if(-not $s -or $s.PathName -cne $v.expected -or $s.State -ne 'Running' -or $s.StartName -cne $v.account){throw 'Exact repair service ownership changed.'};
        if((Get-FileHash -LiteralPath $v.installer -Algorithm SHA256).Hash.ToLowerInvariant() -ne $v.sha){throw 'Reviewed installer bytes changed.'};
        $arguments='/S /SERVICE='+$v.name+' /STATE="'+$v.state+'" /D='+$v.install;
        $p=Start-Process -FilePath $v.installer -ArgumentList $arguments -WindowStyle Hidden -PassThru;
        $done=$p.WaitForExit(420000);
        @{pid=$p.Id;completed=$done;exit_code=$(if($done){$p.ExitCode}else{$null});automatic_repeat=$false}|ConvertTo-Json
        """,{'name':SERVICE,'expected':current['path'],'account':current['account'],'installer':str(INSTALLER),'sha':INSTALLER_SHA,
               'state':str(self.state),'install':str(self.install)},timeout=440)
        self.report['installer_invocation'] = outcome
        self.save('installer-outcome.json',outcome)
        assert outcome['completed'] and outcome['exit_code'] == 0, 'Installer did not complete successfully; no automatic retry is permitted.'
        self.wait_ready()
        self.service()
        self.report['installed_after'] = self.installed_identity()
        self.read_routes()
        after = snapshot(self.kernel)
        assert after == self.before, 'Repair or initial route reads changed retained database/raw evidence.'
        self.report.update(after_repair=after,software_installations=True,downloads=False)
        self.passed('One hidden pinned A5 r2 repair completed; frozen kernel/source/UI and initial no-context route behavior verified')

    def submit_context_once(self):
        self.report['downloads'] = None
        self.report['provider_payload_downloads'] = None
        self.report['provider_payload_downloads_authorized'] = True
        key = 'a5-r2-installed-context-'+secrets.token_hex(12)
        self.save('context-submit-intent.json',{'method':'POST','path':'/matches/'+self.match_id+'/source-context',
            'idempotency_key':key,'one_invocation_only':True,'automatic_retry':False,'wire_count_measured':False})
        request = Request(self.url+prior.API+'/matches/'+self.match_id+'/source-context',data=b'{}',method='POST',
            headers={'Authorization':'Bearer '+self.token,'Content-Type':'application/json','Idempotency-Key':key})
        # Never retry a timed-out POST or submit a new job. Preserve its intent.
        with self.opener.open(request,timeout=20) as response:
            assert response.status == 202
            job = json.loads(response.read(1024*1024))
        self.started_context_job = job['id']
        self.report['context_job_id'] = job['id']
        self.save('context-submitted.json',job)
        deadline = time.monotonic()+150
        while time.monotonic()<deadline:
            _,job = self.call('/jobs/'+self.started_context_job)
            if job['status'] in ('succeeded','failed','cancelled','interrupted'):
                break
            time.sleep(.25)
        assert job['status'] == 'succeeded' and job['attempts'] == 1, 'Context job failed or exceeded attempt 1; no automatic follow-up.'
        self.save('context-job.json',job)
        return job

    def accepted_context(self,job):
        _,context = self.call('/matches/'+self.match_id+'/source-context')
        assert context['availability'] == 'available' and context['context_record_id'] == job['result']['context_record_id']
        assert context['parent_observation_id'] == context['context_parent_observation_id'] == job['payload']['parent']['observation_id']
        reference = view.context(SimpleNamespace(state=self.kernel,db_path=self.kernel/'core.sqlite3'),self.match_id)
        assert prior.canonical(reference) == prior.canonical(context), 'Installed API differs from independent retained full reconstruction.'
        with closing(sqlite3.connect((self.kernel/'core.sqlite3').as_uri()+'?mode=ro',uri=True)) as db:
            actual_parent = binding.parent_binding(db,self.kernel/'raw/connectors',context['parent_observation_id'])
            assert prior.canonical(actual_parent) == prior.canonical(job['payload']['parent'])
            attempt = db.execute('SELECT status,result FROM connector_attempts WHERE job_id=? AND provider=? AND operation=?',
                (job['id'],binding.PROVIDER,'statsbomb_context')).fetchall()
            assert len(attempt) == 1 and attempt[0][0] == 'succeeded'
            journal = json.loads(attempt[0][1])
        assert journal['version'] == 'statsbomb-context-job/1' and set(journal['roles']) == set(binding.ROLE_URLS)
        assert prior.canonical(journal['request']) == prior.canonical(job['payload'])
        acquisitions = []
        for role,entry in journal['roles'].items():
            assert entry['state'] == 'complete' and entry['url'] == binding.ROLE_URLS[role]
            item = entry['acquisition']
            _,metadata = self.call('/connections/statsbomb/acquisitions/'+item['id'])
            assert metadata == item and metadata['provider'] == binding.PROVIDER and metadata['http_status'] == 200
            assert metadata['original_url'] == metadata['resolved_url'] == binding.ROLE_URLS[role]
            assert 0 <= metadata['bytes'] <= binding.MAX_DOCUMENT_BYTES
            acquisitions.append({'role':role,**metadata})
        assert len({item['id'] for item in acquisitions}) == 2
        self.save('context.json',context); self.save('acquisitions.json',acquisitions)
        self.save('journal-summary.json',{'version':journal['version'],'parent_observation_id':context['parent_observation_id'],
            'roles':[{key:entry[key] for key in ('state','claim','url','intent_at')}|{'role':role,'acquisition':entry['acquisition']}
                     for role,entry in journal['roles'].items()],
            'outcome':journal['outcome'],'successful_200_receipts':2,'wire_request_count_measured':False})
        self.report.update(context_record_id=context['context_record_id'],successful_200_acquisitions=2,
            durable_complete_role_intents=2,event_rows=context['projection']['event_summary']['row_count'],
            downloads=True,provider_payload_downloads=True)
        self.passed('LocalService published exact frozen-parent context with two bounded 200 receipts and two complete durable role intents; wire count is not measured')
        return context

    def browser(self,context_info):
        from playwright.sync_api import expect,sync_playwright
        profile = self.output/'browser-profile'
        profile.mkdir(); retained.protect_directory(profile)
        before = snapshot(self.kernel)
        blocked,errors,mutations = [],[],[]
        origin = self.url
        def matrix(rows):
            return [row.locator('td').all_text_contents() for row in rows.all()]
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch_persistent_context(str(profile),executable_path=str(retained.EDGE),
                    headless=True,viewport={'width':1500,'height':1100},reduced_motion='reduce',service_workers='block')
                try:
                    def guard(route):
                        parsed = urlsplit(route.request.url)
                        method = route.request.method
                        if parsed.scheme+'://'+parsed.netloc != origin:
                            blocked.append(parsed.scheme+'://'+parsed.netloc+parsed.path); route.abort()
                        elif method not in ('GET','HEAD') and not (method == 'POST' and parsed.path == prior.API+'/session'):
                            mutations.append({'method':method,'path':parsed.path}); route.abort()
                        else:
                            route.continue_()
                    browser.route('**/*',guard)
                    page = browser.pages[0] if browser.pages else browser.new_page()
                    page.on('pageerror',lambda error:errors.append(self.safe(error)))
                    page.goto(origin+'/#token='+quote(self.token,safe=''),wait_until='domcontentloaded')
                    expect(page.locator('#service-state')).to_contain_text('Server ready')
                    page.goto(origin+'/#match/'+self.match_id,wait_until='domcontentloaded')
                    page.get_by_role('tab',name='Lineups',exact=True).click()
                    panel = page.locator('[data-context-state="available"]')
                    expect(panel).to_be_visible()
                    projection = context_info['projection']
                    for team in projection['squads']:
                        rows = panel.locator('[data-source-team-id="'+str(team['team_id'])+'"] tbody tr')
                        expect(rows).to_have_count(len(team['lineup']))
                        assert matrix(rows) == [[str(player['player_id']),player['player_name'],retained.display(player.get('player_nickname')),
                            retained.display(player.get('jersey_number')),retained.display(player.get('country',{}).get('name'))] for player in team['lineup']]
                    panel.screenshot(path=str(self.output/'installed-squads.png'))
                    page.get_by_role('tab',name='Statistics',exact=True).click()
                    panel = page.locator('[data-context-state="available"]')
                    summary = projection['event_summary']; teams = {team['team_id']:team['team_name'] for team in projection['squads']}
                    types = {item['id']:item['name'] for item in summary['types']}
                    expect(panel).to_contain_text(str(summary['row_count'])+' retained event records')
                    assert matrix(panel.locator(':scope > .table-wrap tbody tr')) == [[teams.get(group['team_id'],'Not supplied'),
                        retained.display(group['period']),types[group['type_id']],str(group['count'])] for group in summary['counts_by_team_period_type']]
                    page.locator('[data-action="browse-source-events"]').click()
                    for offset in (0,50,0):
                        if offset == 50:
                            page.get_by_role('button',name='Next events',exact=True).click()
                        elif offset == 0 and page.get_by_role('button',name='Previous events',exact=True).count():
                            page.get_by_role('button',name='Previous events',exact=True).click()
                        _,data = self.call('/matches/'+self.match_id+'/source-events?offset='+str(offset)+'&limit=50')
                        rows = page.locator('[data-source-events] tbody tr')
                        expect(rows).to_have_count(len(data['items']))
                        if data['items']:
                            expect(rows.first.locator('td').first).to_have_text(str(data['items'][0]['index']))
                        expect(page.locator('[data-source-events]')).to_contain_text(
                            str(offset+1)+'–'+str(offset+len(data['items']))+' of '+str(data['total'])+' source records')
                        assert matrix(rows) == [[str(event['index']),retained.display(event.get('period')),retained.display(event.get('timestamp')),
                            retained.display(event.get('minute')),retained.display(event.get('second')),retained.display(event.get('team',{}).get('name')),
                            retained.display(event.get('player',{}).get('name')),event['type']['name']] for event in data['items']]
                    page.locator('[data-source-events]').screenshot(path=str(self.output/'installed-events.png'))
                    assert not blocked and not mutations and not errors
                finally:
                    browser.close()
        finally:
            assert profile.resolve().parent == self.output and profile.resolve().is_relative_to(ROOT)
            shutil.rmtree(profile)
            self.report['temporary_browser_profile_removed'] = not profile.exists()
        after = snapshot(self.kernel)
        assert before['tables'] == after['tables'] and before['raw_files'] == after['raw_files'] and before['schema'] == after['schema']
        self.report['browser'] = {'read_only_actions':True,'provider_wire_calls_measured':False,
            'blocked_requests':blocked,'unexpected_mutations':mutations,'page_errors':errors,
            'non_auth_tables_unchanged':True,'raw_files_unchanged':True,'schema_unchanged':True,'offsets':[0,50,0]}
        for path in self.output.glob('*.png'):
            protect(path)
        self.passed('Installed Edge view matches all squads/counts and retained native pages; only authentication session writes occur')

    def context(self):
        assert ctypes.windll.shell32.IsUserAnAdmin(), 'Elevated ownership verification is required before the eventual exact-service restart.'
        self.report['localservice_kernel'] = self.kernel_identity()
        job = self.submit_context_once()
        context_info = self.accepted_context(job)
        after = snapshot(self.kernel)
        same_rows(self.before,after,growth=('connector_acquisitions','connector_attempts','product_jobs','product_updates'))
        assert after['tables']['connector_acquisitions']['rows'] == self.before['tables']['connector_acquisitions']['rows']+2
        assert after['tables']['connector_attempts']['rows'] == self.before['tables']['connector_attempts']['rows']+1
        assert after['tables']['product_jobs']['rows'] == self.before['tables']['product_jobs']['rows']+1
        assert after['tables']['product_updates']['rows'] == self.before['tables']['product_updates']['rows']+4
        with closing(sqlite3.connect((self.kernel/'core.sqlite3').as_uri()+'?mode=ro',uri=True)) as db:
            events = [(topic,json.loads(payload)) for topic,payload in db.execute(
                'SELECT topic,payload FROM product_updates WHERE seq>? ORDER BY seq',
                (self.before['sequences']['product_updates'],))]
        assert events == [('job',{'id':job['id'],'status':'queued'}),
                          ('job',{'id':job['id'],'status':'running'}),
                          ('job',{'id':job['id'],'status':'succeeded'}),
                          ('data',{'job_id':job['id'],'kind':'statsbomb_context'})]
        assert after['tables']['cognitive_records']['rows'] == after['tables']['cognitive_receipts']['rows'] == 1
        assert set(after['tables']) == set(self.before['tables']) | {'cognitive_records','cognitive_receipts'}
        for name,number in self.before['sequences'].items():
            if name == 'product_updates':
                assert after['sequences'][name] >= number
            else:
                assert after['sequences'][name] == number
        before_schema = {tuple(row) for row in self.before['schema']}
        after_schema = {tuple(row) for row in after['schema']}
        with closing(sqlite3.connect(':memory:')) as reference:
            reference.executescript(memory.SCHEMA_SQL)
            context_schema = set(reference.execute('SELECT type,name,tbl_name,sql FROM sqlite_master'))
        assert before_schema <= after_schema and after_schema-before_schema == context_schema
        assert all(after['raw_files'].get(name) == value for name,value in self.before['raw_files'].items())
        assert after['counts'] == EXPECTED_COUNTS
        self.report['after_context'] = after
        self.browser(context_info)
        before_restart = snapshot(self.kernel)
        self.restart('retained StatsBomb context persistence')
        self.installed_identity()
        self.passive_health(False,'after exact-service context restart')
        assert self.configuration() == self.baseline
        _,restarted = self.call('/matches/'+self.match_id+'/source-context')
        assert restarted == context_info
        after_restart = snapshot(self.kernel)
        assert before_restart['tables'] == after_restart['tables'] and before_restart['raw_files'] == after_restart['raw_files']
        assert before_restart['schema'] == after_restart['schema']
        self.report['after_restart'] = after_restart
        self.passed('Only the exact A2 service restarted; same parent/context/receipts survive with unchanged non-auth tables/raw evidence')

    def secret_absence(self):
        offending = []
        for path in self.output.rglob('*'):
            if path.is_file():
                raw = path.read_bytes()
                if any(secret.encode('utf-8') in raw or json.dumps(secret,ensure_ascii=False)[1:-1].encode('utf-8') in raw
                       or quote(secret,safe='').encode('utf-8') in raw for secret in set(self.private) if len(secret)>=8):
                    offending.append(str(path.relative_to(self.output)))
        self.report['loaded_secret_values_absent_from_evidence'] = not offending
        self.report['secret_absence_offending_files'] = offending
        return not offending

    def execute(self):
        try:
            self.preflight()
            if self.args.apply:
                self.repair() if self.args.phase == 'repair' else self.context()
            assert self.config_metadata() == self.config_before and self.pairing() == self.pairing_before
            assert prior.digest(self.state/'workstation.json') == self.original_config_hash
            assert self.configuration() == self.baseline
            self.passive_health(False,'final empty configuration')
            self.check_originals()
            self.service()
            self.report['passed'] = True
        except Exception:
            self.report['error'] = self.safe(traceback.format_exc())
        finally:
            try:
                self.report['final_owned_service'] = self.service()
            except Exception:
                self.report['final_owned_service_error'] = self.safe(traceback.format_exc())
                self.report['passed'] = False
            if hasattr(self,'before_originals') and 'originals_after' not in self.report:
                try:
                    self.check_originals()
                except Exception:
                    self.report['originals_preservation_error'] = self.safe(traceback.format_exc())
                    self.report['passed'] = False
            self.report.update(finished_at=prior.stamp(),check_groups=len(self.checks),
                no_automatic_retry=True,settings_edits=False,model_inference=False)
            self.save('journey.json',self.report)
            if not self.secret_absence():
                self.report['passed'] = False
            self.save('journey.json',self.report)
        print(json.dumps({'passed':self.report['passed'],'phase':self.args.phase,'applied':self.args.apply,
            'groups':len(self.checks),'error':self.report.get('error'),'evidence':str(self.output/'journey.json')}),flush=True)
        return 0 if self.report['passed'] else 1


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--phase',choices=('repair','context'),required=True)
    cli.add_argument('--installer',type=Path,default=INSTALLER)
    cli.add_argument('--installer-sha256',default=INSTALLER_SHA)
    cli.add_argument('--repair-receipt',type=Path)
    cli.add_argument('--install-root',type=Path,default=ROOT/'build/workstation/test-install/provider-a2/application files')
    cli.add_argument('--state-root',type=Path,default=ROOT/'build/workstation/test-install/provider-a2/state data')
    cli.add_argument('--service-name',default=SERVICE)
    cli.add_argument('--output',type=Path,required=True)
    cli.add_argument('--allow-development-receipt',type=Path,action='append',default=[])
    cli.add_argument('--apply',action='store_true')
    args = cli.parse_args()
    if args.phase == 'context' and args.repair_receipt is None:
        cli.error('--repair-receipt is required for the separate context phase.')
    if os.name != 'nt' or sys.flags.optimize:
        cli.error('Use the verified Windows Python with assertions enabled.')
    try:
        return Journey(args).execute()
    except Exception:
        # Constructor failures must not expose private configuration/URLs.
        print(json.dumps({'passed':False,'phase':args.phase,'error':'GUARDED_VERIFIER_SETUP_FAILED'}),flush=True)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
