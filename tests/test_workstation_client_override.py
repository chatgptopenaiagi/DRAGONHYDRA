"""Run the replacement-client payload validator through the installed PowerShell."""
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
HELPER = ROOT/'packaging/windows/workstation/ClientBuild.ps1'


@unittest.skipUnless(os.name == 'nt' and PWSH.is_file(), 'Windows PowerShell7 payload contract')
class ClientOverrideTests(unittest.TestCase):
    def setUp(self):
        scratch = ROOT/'runtime/scratch'
        scratch.mkdir(parents=True, exist_ok=True)
        temporary = tempfile.TemporaryDirectory(dir=scratch, prefix='client-override-')
        self.addCleanup(temporary.cleanup)
        self.project = Path(temporary.name)
        self.client = self.project/'build/connections/client build'
        self.client.mkdir(parents=True)
        self.stage = self.project/'build/connections/new workstation'
        self.stage.mkdir()
        self.identity = {'version':'0.4.0-alpha.1', 'api_namespace':'/dragon/api/v1',
                         'schema_version':1, 'architecture':'x86_64-pc-windows-msvc',
                         'source_content_sha256':'a'*64}
        (self.client/'DRAGONHYDRA-Client.exe').write_bytes(b'fixture executable integrity bytes')
        (self.client/'THIRD-PARTY-NOTICES.txt').write_text('Fixture licensing notices')
        (self.client/'BUILD-INFO.json').write_text(json.dumps(self.identity))
        self.manifest = {'schema_version':1, 'product':'DRAGONHYDRA Client',
                         'version':self.identity['version'], 'api_namespace':self.identity['api_namespace'],
                         'kernel_schema_version':1, 'architecture':self.identity['architecture'],
                         'source_content_sha256':self.identity['source_content_sha256'],
                         'status':'verified_current_host', 'verification':{'passed':True}, 'files':[]}
        self.refresh_entries()
        self.runner = self.project/'validate.ps1'
        self.runner.write_text('''param($Helper,$Root,$Project,$Stage,[switch]$StagingCopy,[switch]$ApplyFresh,[switch]$ApplyRepackage,$TargetStage,[switch]$TamperReceiptAfterValidation)
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
. $Helper
try {
 if($StagingCopy){$result=Get-VerifiedClientStagingCopy -Root $Stage -ProjectRoot $Project}
 else{
  $build=Get-VerifiedClientBuild -Root $Root -ProjectRoot $Project -StagingRoot $Stage
  if($TamperReceiptAfterValidation){[IO.File]::AppendAllText((Join-Path $Root 'CLIENT-BUILD.json'),' ')}
  if($ApplyFresh -and $build.staging_was_new){
   New-Item -ItemType Directory -Path (Join-Path $Stage 'stage/client'),(Join-Path $Stage 'stage/server') -Force|Out-Null
   [IO.File]::WriteAllText((Join-Path $Stage 'stage/server/preserved.txt'),'Independent server bytes')
  }
  if($ApplyFresh -or $ApplyRepackage){
   $target=if($TargetStage){$TargetStage}else{Join-Path $Stage 'stage'}
   $result=Set-VerifiedClientPayload -ClientBuild $build -BuildRoot $Stage -Stage $target -RepackageOnly:$ApplyRepackage
  }else{$result=$build}
 }
 $result|ConvertTo-Json -Depth 8
}catch{Write-Output $_.Exception.Message;exit 7}
''')

    def refresh_entries(self):
        self.manifest['files'] = [{'path':p.name, 'bytes':p.stat().st_size,
                                   'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
                                  for p in sorted(self.client.iterdir()) if p.name != 'CLIENT-BUILD.json']
        self.save()

    def save(self):
        (self.client/'CLIENT-BUILD.json').write_text(json.dumps(self.manifest))

    def invoke(self, *, client=None, stage=None, staging_copy=False, apply_fresh=False,
               apply_repackage=False, target_stage=None, tamper_receipt=False):
        command = [str(PWSH), '-NoLogo', '-NoProfile', '-File', str(self.runner),
                   '-Helper', str(HELPER), '-Root', str(client or self.client),
                   '-Project', str(self.project), '-Stage', str(stage or self.stage)]
        if staging_copy:
            command.append('-StagingCopy')
        if apply_fresh:
            command.append('-ApplyFresh')
        if apply_repackage:
            command.append('-ApplyRepackage')
        if target_stage is not None:
            command.extend(['-TargetStage', str(target_stage)])
        if tamper_receipt:
            command.append('-TamperReceiptAfterValidation')
        return subprocess.run(command,
                              capture_output=True, text=True, timeout=30)

    def rejected(self, text):
        result = self.invoke()
        self.assertEqual(result.returncode, 7, result.stdout+result.stderr)
        self.assertIn(text, result.stdout)

    def test_exact_verified_payload_is_accepted_without_mutation(self):
        before = {p.name:p.read_bytes() for p in self.client.iterdir()}
        result = self.invoke()
        self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
        actual = json.loads(result.stdout)
        self.assertEqual(actual['manifest']['source_content_sha256'], 'a'*64)
        self.assertEqual(before, {p.name:p.read_bytes() for p in self.client.iterdir()})

    def test_changed_binary_is_rejected(self):
        (self.client/'DRAGONHYDRA-Client.exe').write_bytes(b'tampered')
        self.rejected('Client payload integrity failed')

    def test_self_consistent_but_incompatible_metadata_is_rejected(self):
        self.identity['api_namespace'] = '/different/api'
        (self.client/'BUILD-INFO.json').write_text(json.dumps(self.identity))
        self.refresh_entries()
        self.rejected('metadata sidecar differs')

    def test_manifest_cannot_escape_payload(self):
        self.manifest['files'][0]['path'] = '../outside.exe'
        self.save()
        self.rejected('unsupported path')

    def test_duplicate_manifest_paths_are_rejected(self):
        self.manifest['files'][0] = self.manifest['files'][1]
        self.save()
        self.rejected('exactly the three')

    def test_unreviewed_extra_file_is_rejected(self):
        (self.client/'extra.txt').write_text('not part of payload')
        self.rejected('Unexpected files')

    def test_unverified_build_is_rejected(self):
        self.manifest['verification']['passed'] = False
        self.save()
        self.rejected('identity or current-host verification')

    def test_candidate_and_staging_overlap_is_rejected(self):
        result = self.invoke(stage=self.client/'nested')
        self.assertEqual(result.returncode, 7)
        self.assertIn('must be separate', result.stdout)

    def test_unowned_candidate_directory_is_rejected(self):
        result = self.invoke(client=self.project/'outside')
        self.assertEqual(result.returncode, 7)
        self.assertIn('dedicated child', result.stdout)

    def staging_copy(self):
        original = self.project/'build/connections/old workstation'
        (original/'stage').mkdir(parents=True)
        (self.stage/'stage').mkdir()
        data = b'{"schema_version":1,"files":[]}'
        for folder in (original, self.stage):
            (folder/'stage/PAYLOAD-MANIFEST.json').write_bytes(data)
        proof = {'schema_version':1, 'purpose':'desktop-client-repair',
                 'source_build_root':str(original), 'payload_manifest_sha256':hashlib.sha256(data).hexdigest()}
        (self.stage/'CLIENT-REPAIR-STAGING.json').write_text(json.dumps(proof))
        return proof

    def test_new_staging_copy_provenance_is_accepted(self):
        self.staging_copy()
        result = self.invoke(staging_copy=True)
        self.assertEqual(result.returncode, 0, result.stdout+result.stderr)

    def test_changed_staging_copy_is_rejected(self):
        self.staging_copy()
        (self.stage/'stage/PAYLOAD-MANIFEST.json').write_bytes(b'changed')
        result = self.invoke(staging_copy=True)
        self.assertEqual(result.returncode, 7)
        self.assertIn('differs from its recorded original', result.stdout)

    def test_in_place_original_staging_is_rejected(self):
        proof = self.staging_copy()
        proof['source_build_root'] = str(self.stage)
        (self.stage/'CLIENT-REPAIR-STAGING.json').write_text(json.dumps(proof))
        result = self.invoke(staging_copy=True)
        self.assertEqual(result.returncode, 7)
        self.assertIn('new separate staging copy', result.stdout)

    def test_explicit_verified_client_is_staged_on_a_new_fresh_build(self):
        fresh = self.project/'build/connections/fresh workstation'
        before = {path.name: path.read_bytes() for path in self.client.iterdir()}
        result = self.invoke(stage=fresh, apply_fresh=True)
        self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
        override = json.loads(result.stdout)
        self.assertEqual(override['staging_mode'], 'fresh_owned_build')
        self.assertIsNone(override['baseline_staging'])
        self.assertEqual(override['binary_sha256'], self.manifest['files'][1]['sha256'])
        for entry in self.manifest['files']:
            self.assertEqual((fresh/'stage/client'/entry['path']).read_bytes(), (self.client/entry['path']).read_bytes())
        self.assertFalse((fresh/'stage/client/CLIENT-BUILD.json').exists())
        self.assertEqual((fresh/'stage/server/preserved.txt').read_text(), 'Independent server bytes')
        self.assertEqual(before, {path.name: path.read_bytes() for path in self.client.iterdir()})

    def test_shared_stager_keeps_repackage_provenance_requirement(self):
        self.staging_copy()
        (self.stage/'stage/client').mkdir()
        (self.stage/'stage/server').mkdir()
        (self.stage/'stage/server/preserved.txt').write_text('Independent server bytes')
        result = self.invoke(apply_repackage=True)
        self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
        override = json.loads(result.stdout)
        self.assertEqual(override['staging_mode'], 'verified_repackage_copy')
        self.assertEqual(override['baseline_staging'], str(self.project/'build/connections/old workstation'))
        self.assertEqual((self.stage/'stage/server/preserved.txt').read_text(), 'Independent server bytes')
        for entry in self.manifest['files']:
            self.assertEqual((self.stage/'stage/client'/entry['path']).read_bytes(), (self.client/entry['path']).read_bytes())
        (self.stage/'CLIENT-REPAIR-STAGING.json').unlink()
        denied = self.invoke(apply_repackage=True)
        self.assertEqual(denied.returncode, 7)

    def test_shared_stager_refuses_existing_root_as_fresh_or_wrong_target(self):
        result = self.invoke(apply_fresh=True)
        self.assertEqual(result.returncode, 7)
        self.assertIn('new build root validated before creation', result.stdout)
        fresh = self.project/'build/connections/fresh wrong target'
        result = self.invoke(stage=fresh, apply_fresh=True, target_stage=self.project/'outside')
        self.assertEqual(result.returncode, 7)
        self.assertIn('exact owned', result.stdout)
        self.assertFalse((self.project/'outside').exists())

    def test_shared_stager_rechecks_source_receipt_before_copying(self):
        fresh = self.project/'build/connections/fresh changed receipt'
        result = self.invoke(stage=fresh, apply_fresh=True, tamper_receipt=True)
        self.assertEqual(result.returncode, 7)
        self.assertIn('receipt changed after its initial validation', result.stdout)
        self.assertFalse((fresh/'stage/client/DRAGONHYDRA-Client.exe').exists())
        self.assertEqual((fresh/'stage/server/preserved.txt').read_text(), 'Independent server bytes')

    def fresh_script_fixture(self):
        scripts = self.project/'scripts'
        helpers = self.project/'packaging/windows/workstation'
        scripts.mkdir()
        helpers.mkdir(parents=True)
        shutil.copyfile(ROOT/'scripts/Build-Workstation.ps1', scripts/'Build-Workstation.ps1')
        for name in ('ClientBuild.ps1', 'KernelBuild.ps1'):
            shutil.copyfile(ROOT/'packaging/windows/workstation'/name, helpers/name)
        xml = self.project/'server/joomla/pkg_dragonhydra.xml'
        xml.parent.mkdir(parents=True)
        xml.write_text('<extension><version>0.4.1-dev.2</version></extension>')
        package = self.project/'frontend.zip'
        package.write_bytes(b'fixture archive - not extracted')
        package.with_suffix('.manifest.json').write_text(json.dumps({'built': True,
            'version': '0.4.1-dev.2', 'frontend_setup': 'fixture', 'child_template_files': 2,
            'sha256': hashlib.sha256(package.read_bytes()).hexdigest(), 'bytes': package.stat().st_size,
            'source_sha': None}))
        tool = self.project/'must-not-execute.exe'
        tool.write_bytes(b'Not an executable')
        build, output = self.project/'build/connections/fresh-script', self.project/'dist/fresh-output'
        command = [str(PWSH), '-NoLogo', '-NoProfile', '-File', str(scripts/'Build-Workstation.ps1'),
            '-BuildRoot', str(build), '-OutputRoot', str(output), '-JoomlaPackagePath', str(package),
            '-ClientBuildRoot', str(self.client), '-SevenZip', str(tool), '-MakeNsis', str(tool)]
        return command, build, output

    def test_fresh_script_accepts_client_selection_before_immutable_baseline_gate(self):
        command, build, output = self.fresh_script_fixture()
        result = subprocess.run(command, capture_output=True, text=True, timeout=30)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('ARTIFACT-MANIFEST.json', result.stdout+result.stderr)
        self.assertNotIn('requires an isolated copy', result.stdout+result.stderr)
        self.assertFalse(build.exists())
        self.assertFalse(output.exists())

    def test_fresh_script_bad_client_fails_before_any_build_or_output(self):
        command, build, output = self.fresh_script_fixture()
        (self.client/'DRAGONHYDRA-Client.exe').write_bytes(b'tampered')
        result = subprocess.run(command, capture_output=True, text=True, timeout=30)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Client payload integrity failed', result.stdout+result.stderr)
        self.assertFalse(build.exists())
        self.assertFalse(output.exists())

    def test_fresh_script_keeps_no_overwrite_and_new_build_root_guards(self):
        command, build, output = self.fresh_script_fixture()
        output.mkdir(parents=True)
        historical = output/'DRAGONHYDRA-0.4.1-dev.1-Workstation-win-x64-Setup.exe'
        historical.write_bytes(b'Previous immutable candidate')
        denied = subprocess.run(command, capture_output=True, text=True, timeout=30)
        self.assertNotEqual(denied.returncode, 0)
        self.assertIn('never overwrites a previous installer', denied.stdout+denied.stderr)
        self.assertEqual(historical.read_bytes(), b'Previous immutable candidate')
        self.assertFalse(build.exists())
        historical.unlink()
        build.mkdir(parents=True)
        marker = build/'preserved.txt'
        marker.write_text('Independent build evidence')
        denied = subprocess.run(command, capture_output=True, text=True, timeout=30)
        self.assertNotEqual(denied.returncode, 0)
        self.assertIn('Use a fresh build directory', denied.stdout+denied.stderr)
        self.assertEqual(marker.read_text(), 'Independent build evidence')

    def test_repackage_script_requires_copy_proof_before_any_payload_mutation(self):
        command, build, output = self.fresh_script_fixture()
        source_sha = 'a1380545bd3bb225f400e7e328535ff692c0123a'
        release = self.project/'dist/releases/v0.4.0-alpha.1/assets'
        release.mkdir(parents=True)
        artifacts = []
        for name in ('DRAGONHYDRA-0.4.0-alpha.1-Server-win-x64.zip',
                     'DRAGONHYDRA-0.4.0-alpha.1-Desktop-win-x64-Setup.exe',
                     'pkg_dragonhydra-0.4.0-alpha.1.zip'):
            path = release/name
            path.write_bytes(('Immutable fixture baseline '+name).encode())
            artifacts.append({'filename': name, 'bytes': path.stat().st_size,
                              'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
        (release/'ARTIFACT-MANIFEST.json').write_text(json.dumps({'source_sha': source_sha, 'artifacts': artifacts}))
        stage = build/'stage'
        (stage/'client').mkdir(parents=True)
        for entry in self.manifest['files']:
            shutil.copyfile(self.client/entry['path'], stage/'client'/entry['path'])
        (stage/'WORKSTATION-BUILD.json').write_text(json.dumps({'product': 'DRAGONHYDRA Workstation',
            'version': '0.4.1-dev.1', 'inner_components': [{'source_sha': source_sha}]}))
        inventory = {'schema_version': 1, 'files': [{'path': path.relative_to(stage).as_posix(),
            'bytes': path.stat().st_size, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
            for path in sorted(stage.rglob('*')) if path.is_file()]}
        manifest = stage/'PAYLOAD-MANIFEST.json'
        manifest.write_text(json.dumps(inventory))
        before = {path.relative_to(stage).as_posix(): path.read_bytes() for path in stage.rglob('*') if path.is_file()}
        denied = subprocess.run(command+['-RepackageOnly'], capture_output=True, text=True, timeout=30)
        self.assertNotEqual(denied.returncode, 0)
        self.assertIn('CLIENT-REPAIR-STAGING.json', denied.stdout+denied.stderr)
        self.assertFalse(output.exists())
        self.assertEqual(before, {path.relative_to(stage).as_posix(): path.read_bytes() for path in stage.rglob('*') if path.is_file()})
        original = self.project/'build/connections/retained original'
        (original/'stage').mkdir(parents=True)
        shutil.copyfile(manifest, original/'stage/PAYLOAD-MANIFEST.json')
        (build/'CLIENT-REPAIR-STAGING.json').write_text(json.dumps({'schema_version': 1,
            'purpose': 'desktop-client-repair', 'source_build_root': str(original),
            'payload_manifest_sha256': hashlib.sha256(manifest.read_bytes()).hexdigest()}))
        accepted = subprocess.run(command+['-RepackageOnly'], capture_output=True, text=True, timeout=30)
        self.assertNotEqual(accepted.returncode, 0)
        # The proof gate is passed; the next preserved web-payload gate stops
        # this deliberately incomplete fixture without executing a build tool.
        self.assertIn('payload-manifest.json', accepted.stdout+accepted.stderr)
        self.assertNotIn('CLIENT-REPAIR-STAGING.json', accepted.stdout+accepted.stderr)
        self.assertEqual(before, {path.relative_to(stage).as_posix(): path.read_bytes() for path in stage.rglob('*') if path.is_file()})


if __name__ == '__main__':
    unittest.main()
