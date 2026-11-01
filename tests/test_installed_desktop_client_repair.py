"""Exercise client-only repair and rollback on disposable files, without services."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
PWSH = Path(r'C:\Program Files\PowerShell\7\pwsh.exe')
HELPER = ROOT/'scripts/Repair-InstalledDesktopClient.ps1'


@unittest.skipUnless(os.name == 'nt' and PWSH.is_file(), 'Windows installed-client repair contract')
class InstalledClientRepairTests(unittest.TestCase):
    def setUp(self):
        scratch = ROOT/'runtime/scratch'
        scratch.mkdir(parents=True, exist_ok=True)
        temporary = tempfile.TemporaryDirectory(dir=scratch, prefix='installed-client-repair-')
        self.addCleanup(temporary.cleanup)
        self.folder = Path(temporary.name)
        self.install = self.folder/'application files'
        (self.install/'client').mkdir(parents=True)
        (self.install/'server').mkdir()
        self.source = self.folder/'verified client'
        self.source.mkdir()
        self.backup = self.folder/'fresh backup'
        identity = {'version':'0.4.0-alpha.1','architecture':'x86_64-pc-windows-msvc',
                    'api_namespace':'/dragon/api/v1','schema_version':1,'source_content_sha256':'a'*64}
        for name, old, new in (
            ('DRAGONHYDRA-Client.exe', b'old executable', b'new verified executable'),
            ('BUILD-INFO.json', b'{"old":true}', json.dumps(identity).encode()),
            ('THIRD-PARTY-NOTICES.txt', b'old license notices', b'new full license notices')):
            (self.install/'client'/name).write_bytes(old)
            (self.source/name).write_bytes(new)
        (self.install/'server/DRAGONHYDRA-Server.exe').write_bytes(b'preserved server')
        build = {'schema_version':1,'product':'DRAGONHYDRA Workstation','version':'0.4.1-dev.1',
                 'api_namespace':'/dragon/api/v1','kernel_schema_version':1,
                 'kernel_override':{'binary_sha256':'unchanged'},
                 'inner_components':[{'filename':'DRAGONHYDRA-0.4.0-alpha.1-Desktop-win-x64-Setup.exe'}]}
        (self.install/'WORKSTATION-BUILD.json').write_text(json.dumps(build))
        inventory = {'schema_version':1,'version':'0.4.1-dev.1',
                     'files':[self.entry(p, self.install) for p in sorted(self.install.rglob('*')) if p.is_file()]}
        (self.install/'PAYLOAD-MANIFEST.json').write_text(json.dumps(inventory))
        manifest = {'schema_version':1,'product':'DRAGONHYDRA Client','version':identity['version'],
                    'architecture':identity['architecture'],'api_namespace':identity['api_namespace'],
                    'kernel_schema_version':1,'source_content_sha256':'a'*64,
                    'status':'verified_current_host','verification':{'passed':True},
                    'files':[self.entry(p,self.source) for p in sorted(self.source.iterdir())]}
        (self.source/'CLIENT-BUILD.json').write_text(json.dumps(manifest))
        self.before = {p.relative_to(self.install).as_posix():p.read_bytes()
                       for p in self.install.rglob('*') if p.is_file()}
        self.runner = self.folder/'transaction.ps1'
        self.runner.write_text('''param($Helper,$Install,$Candidate,$Backup,$Mode)
$ErrorActionPreference='Stop'
. $Helper
$script:mode=$Mode
$script:serviceReads=0
function Get-RepairServices {
    $script:serviceReads++
    $processId=100
    if($script:mode -eq 'service-change' -and $script:serviceReads -gt 1){$processId=101}
    [pscustomobject]@{Name='FixtureService';State='Running';ProcessId=$processId;PathName='preserved'}
}
function Assert-NoInstalledDesktopProcess([string]$InstallRoot) {
    if($script:mode -eq 'busy'){throw 'CLOSE_INSTALLED_CLIENT_BEFORE_REPAIR'}
}
if($Mode -eq 'write-failure') {
    $script:realAtomic=(Get-Command Set-RepairFileAtomic).ScriptBlock
    $script:atomicCalls=0
    function Set-RepairFileAtomic([string]$Source,[string]$Destination) {
        $script:atomicCalls++
        if($script:atomicCalls -eq 3){throw 'SIMULATED_THIRD_REPLACEMENT_FAILURE'}
        & $script:realAtomic -Source $Source -Destination $Destination
    }
}
$build=[pscustomobject]@{root=$Candidate;manifest=(Get-Content -LiteralPath (Join-Path $Candidate 'CLIENT-BUILD.json') -Raw|ConvertFrom-Json);manifest_sha256=(Get-RepairFileHash (Join-Path $Candidate 'CLIENT-BUILD.json'))}
$result=Invoke-DesktopClientRepairTransaction -InstallRoot $Install -ClientBuild $build -BackupRoot $Backup -Apply:($Mode -ne 'preflight')
$result|ConvertTo-Json -Depth 30
''')

    @staticmethod
    def entry(path, boundary):
        return {'path':path.relative_to(boundary).as_posix(),'bytes':path.stat().st_size,
                'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}

    def invoke(self, mode='apply'):
        result = subprocess.run([str(PWSH), '-NoLogo', '-NoProfile', '-File', str(self.runner),
                                 '-Helper', str(HELPER), '-Install', str(self.install),
                                 '-Candidate', str(self.source), '-Backup', str(self.backup), '-Mode', mode],
                                capture_output=True, text=True, timeout=45)
        self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
        return json.loads(result.stdout)

    def assert_originals(self):
        self.assertEqual(self.before, {p.relative_to(self.install).as_posix():p.read_bytes()
                                       for p in self.install.rglob('*') if p.is_file()})

    def test_preflight_writes_nothing(self):
        result = self.invoke('preflight')
        self.assertTrue(result['passed'], result)
        self.assertFalse(result['applied'])
        self.assertFalse(self.backup.exists())
        self.assert_originals()

    def test_apply_updates_only_client_and_coherent_metadata(self):
        result = self.invoke()
        self.assertTrue(result['passed'], result)
        self.assertTrue(result['applied'])
        self.assertEqual(result['services_before'], result['services_after'])
        self.assertEqual((self.install/'server/DRAGONHYDRA-Server.exe').read_bytes(), b'preserved server')
        for name, original in self.before.items():
            if name.startswith('client/') or name in ('WORKSTATION-BUILD.json','PAYLOAD-MANIFEST.json'):
                self.assertEqual((self.backup/'original'/name).read_bytes(), original)
        manifest = json.loads((self.install/'PAYLOAD-MANIFEST.json').read_text())
        for entry in manifest['files']:
            path = self.install/entry['path']
            self.assertEqual(path.stat().st_size, entry['bytes'])
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), entry['sha256'])
        build = json.loads((self.install/'WORKSTATION-BUILD.json').read_text())
        self.assertEqual(build['kernel_override'], {'binary_sha256':'unchanged'})
        self.assertEqual(build['client_override']['source_content_sha256'], 'a'*64)
        self.assertFalse(list(self.install.rglob('.desktop-repair-*.tmp')))

    def test_mid_replacement_failure_rolls_back_all_changed_files(self):
        result = self.invoke('write-failure')
        self.assertFalse(result['passed'])
        self.assertTrue(result['rollback']['passed'], result)
        self.assert_originals()

    def test_service_change_is_detected_and_files_rolled_back(self):
        result = self.invoke('service-change')
        self.assertFalse(result['passed'])
        self.assertEqual(result['error'], 'SERVICE_STATE_CHANGED_DURING_REPAIR')
        self.assertTrue(result['rollback']['passed'], result)
        self.assert_originals()

    def test_changed_installed_file_is_rejected_before_backup(self):
        (self.install/'client/DRAGONHYDRA-Client.exe').write_bytes(b'unexpected independently modified bytes')
        result = self.invoke()
        self.assertFalse(result['passed'])
        self.assertIn('INSTALLED_MANIFEST_INTEGRITY_FAILED', result['error'])
        self.assertFalse(self.backup.exists())

    def test_running_client_is_rejected_without_process_control(self):
        result = self.invoke('busy')
        self.assertFalse(result['passed'])
        self.assertEqual(result['error'], 'CLOSE_INSTALLED_CLIENT_BEFORE_REPAIR')
        self.assertFalse(self.backup.exists())
        self.assert_originals()

    def test_existing_backup_is_preserved(self):
        self.backup.mkdir()
        marker = self.backup/'keep.txt'
        marker.write_bytes(b'earlier evidence')
        result = self.invoke()
        self.assertFalse(result['passed'])
        self.assertEqual(result['error'], 'FRESH_BACKUP_ROOT_REQUIRED')
        self.assertEqual(marker.read_bytes(), b'earlier evidence')
        self.assert_originals()


if __name__ == '__main__':
    unittest.main()
