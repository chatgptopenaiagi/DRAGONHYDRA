"""Execute primary-helper refusal paths in copied fixtures, with no host control."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
PWSH = Path(r'C:\Program Files\PowerShell\7\pwsh.exe')


@unittest.skipUnless(os.name == 'nt' and PWSH.is_file(), 'Existing Windows PowerShell7 required')
class PrimaryInstallGuardTests(unittest.TestCase):
    def setUp(self):
        scratch = ROOT/'runtime/scratch'
        scratch.mkdir(parents=True, exist_ok=True)
        temporary = tempfile.TemporaryDirectory(dir=scratch, prefix='primary-control-guard-')
        self.addCleanup(temporary.cleanup)
        self.project = Path(temporary.name)
        self.helper = self.project/'tests/installation/system_control_install.ps1'
        self.helper.parent.mkdir(parents=True)
        shutil.copyfile(ROOT/'tests/installation/system_control_install.ps1', self.helper)
        self.installer = self.project/'dist/fixture-never-executed.exe'
        self.installer.parent.mkdir()
        self.installer.write_bytes(b'NONEXECUTABLE FIXTURE')
        self.digest = hashlib.sha256(self.installer.read_bytes()).hexdigest()
        self.evidence = self.project/'build/system-control-center-20261101/evidence'
        self.evidence.mkdir(parents=True)
        self.host_read = self.project/'fixture-service-read.txt'
        self.mutation = self.project/'unexpected-mutation.txt'
        self.runner = self.project/'fixture.ps1'
        self.runner.write_text('''param($Helper,$Installer,$Digest,$Output,$Phase,$ReadMarker,$MutationMarker)
$ErrorActionPreference='Stop'
$global:ReadMarker=$ReadMarker
$global:MutationMarker=$MutationMarker
function Get-CimInstance {
    param($ClassName,$Filter)
    [IO.File]::WriteAllText($global:ReadMarker,'fixture service metadata only')
    @('DragonhydraProvidersA2Test','DragonhydraWorkstation','DragonhydraGenesisA8Test') | ForEach-Object {
        [pscustomobject]@{Name=$_;State='Running';ProcessId=1;PathName='fixture binding'}
    }
}
function Get-Service { param($Name) $null }
function Start-Process { [IO.File]::WriteAllText($global:MutationMarker,'blocked'); throw 'FIXTURE_MUTATION_FORBIDDEN' }
function Stop-Service { [IO.File]::WriteAllText($global:MutationMarker,'blocked'); throw 'FIXTURE_MUTATION_FORBIDDEN' }
function Start-Service { [IO.File]::WriteAllText($global:MutationMarker,'blocked'); throw 'FIXTURE_MUTATION_FORBIDDEN' }
& $Helper -Phase $Phase -Installer $Installer -ExpectedInstallerSha256 $Digest -Output $Output
exit $LASTEXITCODE
''', encoding='utf-8')

    def run_helper(self, phase, *, digest=None, output=None):
        output = output or self.evidence/(phase+'.json')
        result = subprocess.run([str(PWSH), '-NoProfile', '-File', str(self.runner),
            '-Helper',str(self.helper),'-Installer',str(self.installer),
            '-Digest',digest or self.digest,'-Output',str(output),'-Phase',phase,
            '-ReadMarker',str(self.host_read),'-MutationMarker',str(self.mutation)],
            capture_output=True, text=True, timeout=20)
        self.assertFalse(self.mutation.exists(), 'No process/service mutation is allowed in fixture tests')
        self.assertNotEqual(result.returncode, 0)
        return result, output

    def test_fresh_install_modes_rejected_before_any_observation_or_receipt(self):
        for phase in ('Install','Preflight'):
            with self.subTest(phase=phase):
                _, output = self.run_helper(phase)
                self.assertFalse(output.exists())
                self.assertFalse(self.host_read.exists())

    def test_upgrade_and_restart_require_explicit_apply(self):
        for phase in ('Upgrade','Restart'):
            with self.subTest(phase=phase):
                _, output = self.run_helper(phase)
                receipt = json.loads(output.read_text())
                self.assertEqual(receipt['error']['message'], 'EXPLICIT_APPLY_REQUIRED')
                self.assertFalse(receipt['passed'])
                self.assertFalse(receipt['applied'])
                self.assertNotIn('installer_process_id', receipt)

    def test_mismatched_installer_fails_before_service_observation(self):
        _, output = self.run_helper('Upgrade', digest='0'*64)
        self.assertEqual(json.loads(output.read_text())['error']['message'], 'INSTALLER_HASH_MISMATCH')
        self.assertFalse(self.host_read.exists())

    def test_existing_receipt_is_not_overwritten(self):
        output = self.evidence/'preserved.json'
        original = b'original receipt must survive'
        output.write_bytes(original)
        self.run_helper('Verify', output=output)
        self.assertEqual(output.read_bytes(), original)
        self.assertFalse(self.host_read.exists())

    def test_rejected_junction_cannot_receive_a_finally_receipt(self):
        outside = self.project/'outside-evidence'
        outside.mkdir()
        link = self.evidence/'redirect'
        junction_script = self.project/'make-fixture-junction.ps1'
        junction_script.write_text("param($Link,$Target)\n$ErrorActionPreference='Stop'\nNew-Item -ItemType Junction -Path $Link -Target $Target | Out-Null\n", encoding='utf-8')
        made = subprocess.run([str(PWSH),'-NoProfile','-File',str(junction_script),
            '-Link',str(link),'-Target',str(outside)],capture_output=True,text=True,timeout=15)
        self.assertEqual(made.returncode,0,'Fixture junction creation must succeed to exercise this guard')
        self.addCleanup(lambda: os.rmdir(link) if link.exists() else None)
        self.run_helper('Upgrade', output=link/'rejected.json')
        self.assertEqual(list(outside.iterdir()),[],'Rejected output must never receive a receipt')
        self.assertFalse(self.host_read.exists())

    def test_existing_temporary_receipt_is_preserved(self):
        output = self.evidence/'fresh-rejection.json'
        temporary = output.with_name(output.name+'.tmp')
        original = b'previous incomplete receipt must survive'
        temporary.write_bytes(original)
        self.run_helper('Upgrade',digest='0'*64,output=output)
        self.assertTrue(temporary.exists(),'Existing temporary evidence must not be consumed')
        self.assertEqual(temporary.read_bytes(),original)
        self.assertEqual(json.loads(output.read_text())['error']['message'],'INSTALLER_HASH_MISMATCH')
