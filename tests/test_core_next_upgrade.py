"""Pure upgrade transition and isolated atomic-file failure contracts."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
LAB = Path(r'C:\xampp\DRAGONHYDRA-CORE-NEXT-LAB')
PWSH = r'C:\Program Files\PowerShell\7\pwsh.exe'


class UpgradeTests(unittest.TestCase):
    def setUp(self):
        self.base = LAB/'tests'
        self.base.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=self.base, prefix='upgrade-')
        self.folder = Path(self.temp.name)
        self.addCleanup(self.clean)

    def clean(self):
        assert self.folder.resolve().is_relative_to(self.base.resolve())
        self.temp.cleanup()

    def run_ps(self, tail):
        profile = str(ROOT/'packaging/windows/workstation/CoreNextProfile.ps1').replace("'", "''")
        upgrade = str(ROOT/'packaging/windows/workstation/CoreNextUpgrade.ps1').replace("'", "''")
        script = "$ErrorActionPreference='Stop';. '"+profile+"';. '"+upgrade+"';" + tail
        return subprocess.run([PWSH, '-NoLogo', '-NoProfile', '-NonInteractive', '-Command', script],
                              capture_output=True, text=True, timeout=30)

    def plan(self, mutate='', to_version='0.5.0-dev.2', expected='$p.installation_id', source="('b'*40)"):
        return self.run_ps("""
        $p=New-CoreNextProfileObject -Environment candidate -SourceCommit ('a'*40) -Version '0.5.0-dev.1' -BuildId fixture
        $cfg=$p|ConvertTo-Json -Depth 20|ConvertFrom-Json
        $cfg|Add-Member product_version '0.5.0-dev.1'
        foreach($pair in @(@('api_port',$p.ports.api),@('web_port',$p.ports.web),@('database_port',$p.ports.database),@('db_name',$p.database.admin_schema),@('db_user',$p.database.admin_user),@('core_db_name',$p.database.core_schema),@('core_db_user',$p.database.core_user),@('root_password','synthetic-preserved-secret'),@('owner_sid','synthetic-owner'))){$cfg|Add-Member $pair[0] $pair[1]}
        """ + mutate + "\ntry{$n=New-CoreNextUpgradeMetadata -Profile $p -Config $cfg -ExpectedInstallationId "+expected+
        " -FromSource ('a'*40) -FromVersion '0.5.0-dev.1' -ToSource "+source+" -ToVersion '"+to_version+"' -BuildId dev2;"+
        "@{profile_version=$n.profile.version;config_version=$n.config.version;source=$n.profile.source_commit;identity_preserved=($n.profile.installation_id -ceq $p.installation_id);ports_preserved=(($n.config.ports|ConvertTo-Json -Compress) -ceq ($cfg.ports|ConvertTo-Json -Compress));secret_preserved=($n.config.root_password -ceq $cfg.root_password);owner_preserved=($n.config.owner_sid -ceq $cfg.owner_sid);old_untouched=($p.version -ceq '0.5.0-dev.1')}|ConvertTo-Json -Compress}catch{Write-Output $_.Exception.Message;exit 7}")

    def test_next_increment_preserves_identity_ports_secrets_owner_and_input_objects(self):
        result = self.plan()
        self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
        output = json.loads(result.stdout)
        self.assertEqual(output['profile_version'], '0.5.0-dev.2')
        self.assertEqual(output['config_version'], '0.5.0-dev.2')
        self.assertEqual(output['source'], 'b'*40)
        self.assertTrue(all(output[key] for key in ('identity_preserved','ports_preserved','secret_preserved','owner_preserved','old_untouched')))

    def test_wrong_identity_or_partial_old_binding_is_rejected(self):
        for args in ({'expected':"'core-next-'+('0'*32)"}, {'mutate':"$cfg.source_commit='c'*40"},
                     {'mutate':"$cfg.product_version='0.5.0-dev.2'"}, {'mutate':'$cfg.web_port=18740'}):
            with self.subTest(args=args):
                self.assertNotEqual(self.plan(**args).returncode, 0)

    def test_downgrades_same_version_skips_and_same_source_are_rejected(self):
        for version in ('0.5.0-dev.0','0.5.0-dev.1','0.5.0-dev.3','0.6.0-dev.1'):
            with self.subTest(version=version):
                self.assertNotEqual(self.plan(to_version=version).returncode, 0)
        self.assertNotEqual(self.plan(source="('a'*40)").returncode, 0)

    def test_original_project_cannot_be_an_upgrade_target(self):
        result = self.plan(mutate="$p.install_root='C:\\xampp\\DRAGONHYDRA\\build\\workstation\\test-install\\application files'")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('CORE_NEXT_PATH_OUTSIDE_LAB', result.stderr+result.stdout)

    def test_atomic_partial_failure_restores_only_our_written_profile(self):
        result = self.atomic_failure(independent=False)
        self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
        self.assertEqual(json.loads(result.stdout), {'profile_restored': True, 'config_original': True})

    def test_partial_failure_never_overwrites_an_independent_config_change(self):
        result = self.atomic_failure(independent=True)
        self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
        output = json.loads(result.stdout)
        self.assertEqual(output['code'], 'CORE_NEXT_UPGRADE_PARTIAL_METADATA_RECONCILIATION_REQUIRED')
        self.assertTrue(output['independent_config_preserved'])

    def metadata_fixture(self):
        folder = str(self.folder).replace("'", "''")
        return ("$root='"+folder+"';$live=Join-Path $root 'profile';$state=Join-Path $live 'state';$backup=Join-Path $root 'backup';"
                "New-Item -ItemType Directory -Path $live,$state,$backup|Out-Null;"
                "$profile=Join-Path $live 'installation-profile.json';$config=Join-Path $state 'workstation.json';"
                "$oldP=@{install_root=(Join-Path $live 'application');state_root=$state;version='old'};"
                "$oldC=@{version='old';root_password='synthetic-original'};"
                "$pText=$oldP|ConvertTo-Json -Compress;$cText=$oldC|ConvertTo-Json -Compress;"
                "[IO.File]::WriteAllText($profile,$pText);[IO.File]::WriteAllText($config,$cText);"
                "$t=@{profile=@{install_root=(Join-Path $live 'application');state_root=$state;version='new'};"
                "config=@{version='new';root_password='synthetic-original'};"
                "original_profile_fingerprint=(Get-CoreNextMetadataFingerprint $oldP);"
                "original_config_fingerprint=(Get-CoreNextMetadataFingerprint $oldC)};")

    def atomic_failure(self, independent):
        mutation = "[IO.File]::WriteAllText($config,'independent change');" if independent else ''
        ending = "@{code=$code;independent_config_preserved=([IO.File]::ReadAllText($config) -ceq 'independent change')}" if independent else "@{profile_restored=([IO.File]::ReadAllText($profile) -ceq $pText);config_original=([IO.File]::ReadAllText($config) -ceq $cText)}"
        return self.run_ps(self.metadata_fixture()+"$original=(Get-Command Write-CoreNextAtomicBytes).ScriptBlock;$script:calls=0;function Write-CoreNextAtomicBytes {param($Path,$Bytes,$BackupFile,$ExpectedCurrentSha256);$script:calls++;if($script:calls -eq 2){"+mutation+"throw 'injected second write failure'};& $original -Path $Path -Bytes $Bytes -BackupFile $BackupFile -ExpectedCurrentSha256 $ExpectedCurrentSha256};$code='';try{Set-CoreNextUpgradeMetadata -ProfilePath $profile -ConfigPath $config -Transition $t -BackupRoot $backup|Out-Null}catch{$code=$_.Exception.Message};"+ending+"|ConvertTo-Json -Compress")

    def test_stale_plan_refuses_owner_config_or_profile_changes_before_any_write(self):
        for target, change in (('$config',"$oldC.root_password='synthetic-rotated'"),
                               ('$profile',"$oldP.version='independently-updated'")):
            with self.subTest(target=target):
                child = tempfile.TemporaryDirectory(dir=self.base, prefix='stale-plan-')
                prior = self.folder
                self.folder = Path(child.name)
                try:
                    value = '$oldC' if target == '$config' else '$oldP'
                    result = self.run_ps(self.metadata_fixture()+change+";[IO.File]::WriteAllText("+target+",("+value+"|ConvertTo-Json -Compress));$pBefore=[IO.File]::ReadAllText($profile);$cBefore=[IO.File]::ReadAllText($config);$code='';try{Set-CoreNextUpgradeMetadata -ProfilePath $profile -ConfigPath $config -Transition $t -BackupRoot $backup|Out-Null}catch{$code=$_.Exception.Message};@{code=$code;profile_preserved=([IO.File]::ReadAllText($profile) -ceq $pBefore);config_preserved=([IO.File]::ReadAllText($config) -ceq $cBefore);no_backup_written=(@(Get-ChildItem -LiteralPath $backup -File).Count -eq 0)}|ConvertTo-Json -Compress")
                    self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
                    proof = json.loads(result.stdout)
                    self.assertEqual(proof['code'], 'CORE_NEXT_UPGRADE_METADATA_CHANGED_SINCE_PLAN')
                    self.assertTrue(all(proof[k] for k in ('profile_preserved','config_preserved','no_backup_written')))
                finally:
                    assert self.folder.resolve().is_relative_to(self.base.resolve())
                    child.cleanup()
                    self.folder = prior

    def test_atomic_target_changed_after_snapshot_is_not_overwritten(self):
        result = self.run_ps(self.metadata_fixture()+"$expected=Get-CoreNextBytesFingerprint ([IO.File]::ReadAllBytes($config));[IO.File]::WriteAllText($config,'independent update');$code='';try{Write-CoreNextAtomicBytes -Path $config -Bytes ([Text.Encoding]::UTF8.GetBytes('our update')) -BackupFile (Join-Path $backup 'before.json') -ExpectedCurrentSha256 $expected}catch{$code=$_.Exception.Message};@{code=$code;independent_preserved=([IO.File]::ReadAllText($config) -ceq 'independent update');no_backup_written=(@(Get-ChildItem -LiteralPath $backup -File).Count -eq 0)}|ConvertTo-Json -Compress")
        self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
        proof = json.loads(result.stdout)
        self.assertEqual(proof['code'], 'CORE_NEXT_UPGRADE_ATOMIC_TARGET_CHANGED')
        self.assertTrue(proof['independent_preserved'])
        self.assertTrue(proof['no_backup_written'])

    def test_utf8_bom_metadata_is_read_without_changing_snapshot_meaning(self):
        result = self.run_ps(self.metadata_fixture()+"$bom=[Text.UTF8Encoding]::new($true);[IO.File]::WriteAllText($profile,$pText,$bom);[IO.File]::WriteAllText($config,$cText,$bom);$r=Set-CoreNextUpgradeMetadata -ProfilePath $profile -ConfigPath $config -Transition $t -BackupRoot $backup;@{profile_updated=$r.profile_updated;config_updated=$r.config_updated;secret_preserved=(([IO.File]::ReadAllText($config)|ConvertFrom-Json).root_password -ceq 'synthetic-original')}|ConvertTo-Json -Compress")
        self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
        self.assertTrue(all(json.loads(result.stdout).values()))

    def test_snapshot_uses_real_registry_shape_and_process_local_script_policy(self):
        text = (ROOT/'scripts/Upgrade-CoreNextWorkstation.ps1').read_text()
        self.assertIn("$registry.schema_version -cne 'core-next.modules/1'", text)
        self.assertIn('$registry.installation.installation_id -cne $p.installation_id', text)
        self.assertNotIn('$registry.installation_id', text)
        calls = [line for line in text.splitlines() if 'powershell.exe' in line and ' -File ' in line]
        self.assertEqual(len(calls), 2)
        self.assertTrue(all('-ExecutionPolicy Bypass -File' in line for line in calls))
        self.assertNotIn('Set-ExecutionPolicy', text)
        self.assertLess(text.index('Assert-CoreNextUpgradeSnapshot -ProfilePath'), text.index('-File $oldController'))

    def test_reparse_atomic_target_is_rejected_without_touching_target(self):
        folder = str(self.folder).replace("'", "''")
        result = self.run_ps("$root='"+folder+"';$real=Join-Path $root 'real';$link=Join-Path $root 'linked';New-Item -ItemType Directory -Path $real|Out-Null;[IO.File]::WriteAllText((Join-Path $real 'profile.json'),'unchanged');New-Item -ItemType Junction -Path $link -Target $real|Out-Null;try{try{Write-CoreNextAtomicBytes -Path (Join-Path $link 'profile.json') -Bytes ([byte[]](1,2)) -BackupFile (Join-Path $root 'before.json');exit 8}catch{if($_.Exception.Message -cne 'CORE_NEXT_REPARSE_PATH_REJECTED'){throw};@{target_unchanged=([IO.File]::ReadAllText((Join-Path $real 'profile.json')) -ceq 'unchanged')}|ConvertTo-Json -Compress}}finally{Remove-Item -LiteralPath $link -Force}")
        self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
        self.assertTrue(json.loads(result.stdout)['target_unchanged'])

    def test_upgrade_scripts_parse_without_invoking_deployment(self):
        for path in (ROOT/'scripts/Upgrade-CoreNextWorkstation.ps1', ROOT/'packaging/windows/workstation/CoreNextUpgrade.ps1'):
            result = self.run_ps("$tokens=$null;$errors=$null;[Management.Automation.Language.Parser]::ParseFile('"+str(path).replace("'", "''")+"',[ref]$tokens,[ref]$errors)|Out-Null;if($errors.Count){$errors|ForEach-Object{$_.Message};exit 7}")
            self.assertEqual(result.returncode, 0, result.stdout+result.stderr)

    def backup_copy(self, mode='success', relative=r'kernel\joomla-bridge.json', outside=False):
        folder = str(self.folder).replace("'", "''")
        mock = "[IO.File]::Copy((Join-Path $SourceDirectory $FileName),(Join-Path $DestinationDirectory $FileName));return 1"
        if mode == 'badexit':
            mock = 'return 8'
        elif mode == 'empty':
            mock = "[IO.File]::WriteAllText((Join-Path $DestinationDirectory $FileName),'');return 0"
        state_arg = "'C:\\xampp\\DRAGONHYDRA\\state'" if outside else '$state'
        return self.run_ps("$root='"+folder+"';$state=Join-Path $root 'state';$private=Join-Path $root 'private';New-Item -ItemType Directory -Path (Join-Path $state 'kernel'),$private|Out-Null;[IO.File]::WriteAllText((Join-Path $state 'kernel/joomla-bridge.json'),'synthetic fixture only');$sid=[Security.Principal.WindowsIdentity]::GetCurrent().User.Value;& (Join-Path $env:WINDIR 'System32/icacls.exe') $private /inheritance:r /grant:r ('*'+$sid+':(OI)(CI)F') '*S-1-5-18:(OI)(CI)F' '*S-1-5-32-544:(OI)(CI)F' *> $null;if($LASTEXITCODE){throw 'fixture ACL failed'};function Invoke-CoreNextBackupCopy {param($SourceDirectory,$DestinationDirectory,$FileName,$LogPath);"+mock+"};try{$r=Copy-CoreNextProtectedBackup -StateRoot "+state_arg+" -BackupRoot $private -RelativePath '"+relative+"' -OwnerSid $sid;@{exit_code=$r.exit_code;source_hash_available=$r.source_hash_available;comparison=$r.source_hash_comparison;bytes=$r.bytes}|ConvertTo-Json -Compress}catch{Write-Output $_.Exception.Message;exit 7}")

    def test_backup_mode_uses_exact_private_file_and_records_actual_payload_integrity(self):
        result = self.backup_copy()
        self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
        proof = json.loads(result.stdout)
        self.assertEqual(proof['exit_code'], 1)
        self.assertTrue(proof['source_hash_available'])
        self.assertEqual(proof['comparison'], 'MATCH')
        self.assertGreater(proof['bytes'], 0)

    def test_backup_mode_failure_empty_and_escaped_sources_fail_before_live_actions(self):
        for args in ({'mode':'badexit'}, {'mode':'empty'}, {'relative':'kernel/other.json'}, {'outside':True}):
            with self.subTest(args=args):
                # Each nested case gets its own fixture directory.
                child = tempfile.TemporaryDirectory(dir=self.base, prefix='backup-negative-')
                prior = self.folder
                self.folder = Path(child.name)
                try:
                    result = self.backup_copy(**args)
                    self.assertEqual(result.returncode, 7, result.stdout+result.stderr)
                finally:
                    assert self.folder.resolve().is_relative_to(self.base.resolve())
                    child.cleanup()
                    self.folder = prior


if __name__ == '__main__':
    unittest.main()
