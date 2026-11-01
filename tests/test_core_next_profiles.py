"""Deployment binding and manifest escape guards; no services or installers run."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
LAB=Path(r'C:\xampp\DRAGONHYDRA-CORE-NEXT-LAB')
PWSH=r'C:\Program Files\PowerShell\7\pwsh.exe'
spec=importlib.util.spec_from_file_location('payload_verifier',ROOT/'scripts/verify_core_next_payload.py')
payload=importlib.util.module_from_spec(spec);spec.loader.exec_module(payload)

class ProfileGuards(unittest.TestCase):
    def setUp(self):
        scratch=LAB/'tests';scratch.mkdir(exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(dir=scratch,prefix='profile-')
        self.addCleanup(self.temp.cleanup);self.lab=Path(self.temp.name)
        suffix='a'*12;id='core-next-'+'a'*32;base=self.lab/'profiles'/id
        self.profile=dict(schema_version=1,product='DRAGONHYDRA CORE NEXT',edition='CORE NEXT',installation_id=id,environment_id='candidate',lab_root=str(self.lab),
            install_root=str(base/'application'),state_root=str(base/'state'),browser_user_data=str(base/'browser'),
            service_name='DragonhydraCoreNextcandidate'+suffix,shortcut_name='DRAGONHYDRA CORE NEXT candidate '+suffix,
            uninstall_id='DRAGONHYDRA-CORE-NEXT-'+id,ports=dict(api=18810,web=18811,database=18812),
            database=dict(admin_schema='dhcn_admin_'+suffix,admin_user='dhcn_admin_'+suffix,core_schema='dhcn_core_'+suffix,core_user='dhcn_core_'+suffix),
            cookie_name='dhcn_'+suffix,joomla_session_suffix=id,provider_schedules='disabled',copy_credentials=False,
            api_namespace='/dragon/api/v1',kernel_schema_version=1,source_commit='b'*40,build_id='fixture',version='0.5.0-dev.1')
        self.runner=self.lab/'validate.ps1'
        self.runner.write_text('param($Helper,$Profile,$Lab,$Service)\n. $Helper\nif($Service){$script:fixtureService=Get-Content -LiteralPath $Service -Raw|ConvertFrom-Json;function Get-CimInstance {param($ClassName,$Filter) $script:fixtureService}}\ntry {$p=Get-Content -LiteralPath $Profile -Raw|ConvertFrom-Json;$null=Assert-CoreNextProfile $p -LabRoot $Lab -CheckService:([bool]$Service);"PASS"}catch{Write-Output $_.Exception.Message;exit 7}\n')
    def invoke(self,profile=None,service=None):
        path=self.lab/'profile.json';path.write_text(json.dumps(profile or self.profile))
        args=[PWSH,'-NoProfile','-File',str(self.runner),'-Helper',str(ROOT/'packaging/windows/workstation/CoreNextProfile.ps1'),'-Profile',str(path),'-Lab',str(self.lab)]
        if service:
            file=self.lab/'service.json';file.write_text(json.dumps(service));args+=['-Service',str(file)]
        return subprocess.run(args,capture_output=True,text=True,timeout=15)
    def test_complete_isolated_profile_accepted(self):
        r=self.invoke();self.assertEqual(r.returncode,0,r.stdout+r.stderr)
    def test_original_application_or_state_rejected(self):
        for field,value in [('install_root',r'C:\Program Files\DRAGONHYDRA'),('state_root',r'C:\ProgramData\DRAGONHYDRA')]:
            p=copy.deepcopy(self.profile);p[field]=value;r=self.invoke(p);self.assertEqual(r.returncode,7)
    def test_service_or_database_substitution_rejected(self):
        p=copy.deepcopy(self.profile);p['service_name']='DragonhydraWorkstation';self.assertEqual(self.invoke(p).returncode,7)
        p=copy.deepcopy(self.profile);p['database']['admin_schema']='dragonhydra_admin';self.assertEqual(self.invoke(p).returncode,7)
    def test_old_ports_or_copied_credentials_rejected(self):
        p=copy.deepcopy(self.profile);p['ports']['api']=18743;self.assertEqual(self.invoke(p).returncode,7)
        p=copy.deepcopy(self.profile);p['copy_credentials']=True;self.assertEqual(self.invoke(p).returncode,7)
    def test_identity_cannot_point_to_another_profile(self):
        p=copy.deepcopy(self.profile);p['installation_id']='core-next-'+'c'*32;self.assertEqual(self.invoke(p).returncode,7)
    def test_profile_junction_or_symlink_rejected_before_install(self):
        path=Path(self.profile['install_root']);path.parent.mkdir(parents=True)
        other=self.lab/'other';other.mkdir()
        try:path.symlink_to(other,target_is_directory=True)
        except OSError:self.skipTest('Symlink creation unavailable')
        self.assertEqual(self.invoke().returncode,7)
    def test_existing_service_with_other_binary_or_account_rejected(self):
        service=dict(PathName='"C:\\Program Files\\DRAGONHYDRA\\service.exe"',StartName='NT AUTHORITY\\LocalService')
        self.assertEqual(self.invoke(service=service).returncode,7)
        image='"'+self.profile['install_root']+'\\workstation\\DragonhydraService.exe" --state "'+self.profile['state_root']+'" --name '+self.profile['service_name']
        service=dict(PathName=image,StartName='LocalSystem')
        self.assertEqual(self.invoke(service=service).returncode,7)
    def factory(self,wrong=None):
        runner=self.lab/'factory.ps1'
        runner.write_text('param($Helper,$Lab,$Wrong)\n. $Helper\ntry{$a=New-CoreNextProfileObject -SourceCommit ("b"*40) -Version "0.5.0-dev.1" -LabRoot $Lab -ReservedPorts @(18800,18801,18802);$b=New-CoreNextProfileObject -SourceCommit ("b"*40) -Version "0.5.0-dev.1" -LabRoot $Lab -ReservedPorts @(18800,18801,18802,$a.ports.api,$a.ports.web,$a.ports.database);$version=if($Wrong -eq "version"){"0.6.0-dev.1"}else{"0.5.0-dev.1"};$source=if($Wrong -eq "source"){"c"*40}else{"b"*40};Assert-CoreNextReleaseBinding $a $version $source;Assert-CoreNextReleaseBinding $b $version $source;@($a,$b)|ConvertTo-Json -Depth 8}catch{Write-Output $_.Exception.Message;exit 7}')
        args=[PWSH,'-NoProfile','-File',str(runner),'-Helper',str(ROOT/'packaging/windows/workstation/CoreNextProfile.ps1'),'-Lab',str(self.lab)]
        if wrong:args+=['-Wrong',wrong]
        return subprocess.run(args,capture_output=True,text=True,timeout=15)
    def test_default_factory_generates_two_independent_instances_without_live_state(self):
        r=self.factory();self.assertEqual(r.returncode,0,r.stdout+r.stderr)
        first,second=json.loads(r.stdout)
        for key in ['installation_id','service_name','shortcut_name','uninstall_id','browser_user_data','cookie_name','state_root','install_root']:
            self.assertNotEqual(first[key],second[key],key)
        self.assertEqual(len(set(first['ports'].values())|set(second['ports'].values())),6)
        self.assertTrue(all(p>=18800 for p in first['ports'].values()))
        self.assertFalse(Path(first['state_root']).exists())
        self.assertFalse(Path(second['state_root']).exists())
    def test_release_binding_rejects_different_source(self):
        self.assertEqual(self.factory('source').returncode,7)
    def test_release_binding_rejects_different_version(self):
        self.assertEqual(self.factory('version').returncode,7)

class PayloadGuards(unittest.TestCase):
    def setUp(self):
        scratch=LAB/'tests';scratch.mkdir(exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(dir=scratch,prefix='payload-');self.addCleanup(self.temp.cleanup)
        self.lab=Path(self.temp.name);self.root=self.lab/'input';self.root.mkdir()
        self.file=self.root/'server.exe';self.file.write_bytes(b'synthetic binary fixture never executed')
        self.entry=dict(path='server.exe',bytes=self.file.stat().st_size,sha256=hashlib.sha256(self.file.read_bytes()).hexdigest())
        self.save()
    def save(self):
        (self.root/'PAYLOAD-MANIFEST.json').write_text(json.dumps(dict(files=[self.entry])))
    def test_exact_payload_can_be_copied_only_to_fresh_lab_destination(self):
        target=self.lab/'copy';self.assertTrue(payload.verify(self.root,self.lab,target)['verified'])
        self.assertEqual((target/'server.exe').read_bytes(),self.file.read_bytes())
        with self.assertRaises(ValueError):payload.verify(self.root,self.lab,target)
    def test_changed_file_rejected(self):
        self.file.write_bytes(b'changed')
        with self.assertRaises(ValueError):payload.verify(self.root,self.lab)
    def test_manifest_escape_or_alternate_stream_rejected(self):
        for name in ['../outside.exe','C:/outside.exe','server.exe:stream']:
            self.entry['path']=name;self.save()
            with self.assertRaises(ValueError):payload.verify(self.root,self.lab)
    def test_symlink_member_rejected(self):
        link=self.root/'linked.exe'
        try:link.symlink_to(self.file)
        except OSError:self.skipTest('Symlink creation unavailable')
        self.entry['path']='linked.exe';self.save()
        with self.assertRaises(ValueError):payload.verify(self.root,self.lab)

if __name__=='__main__':unittest.main()
