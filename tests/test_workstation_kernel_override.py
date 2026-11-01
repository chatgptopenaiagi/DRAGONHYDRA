"""Fixture-only kernel/frontend proof gates; no installer, HTTP or services run."""
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
HELPER = ROOT/'packaging/windows/workstation/KernelBuild.ps1'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


@unittest.skipUnless(os.name == 'nt' and PWSH.is_file(), 'Existing Windows PowerShell7 required')
class KernelOverrideTests(unittest.TestCase):
    def setUp(self):
        scratch = ROOT/'runtime/scratch'
        scratch.mkdir(parents=True, exist_ok=True)
        temporary = tempfile.TemporaryDirectory(dir=scratch, prefix='kernel-override-')
        self.addCleanup(temporary.cleanup)
        self.project = Path(temporary.name)
        self.kernel = self.project/'build/connections/kernel build'
        self.payload = self.kernel/'dist/kernel'
        self.payload.mkdir(parents=True)
        self.build = self.project/'build/connections/new workstation'
        self.stage = self.build/'stage'
        (self.stage/'server').mkdir(parents=True)
        (self.stage/'server/DRAGONHYDRA-Server.exe').write_bytes(b'old fixture baseline')
        (self.stage/'server/THIRD-PARTY-NOTICES.txt').write_text('Verified baseline notices')
        (self.stage/'client').mkdir()
        (self.stage/'client/preserved.txt').write_text('Independent client bytes')
        self.identity = {'version': '0.4.0-alpha.1', 'api_namespace': '/dragon/api/v1',
                         'schema_version': 1, 'source_content_sha256': 'a'*64,
                         'source_sha': None, 'build_kind': 'connector-development-snapshot'}
        self.binary = self.payload/'DRAGONHYDRA-Server.exe'
        self.binary.write_bytes(b'new verified fixture kernel - never execute')
        (self.payload/'BUILD-INFO.json').write_text(json.dumps(self.identity))
        (self.payload/'SOURCE-MANIFEST.json').write_text(json.dumps({'schema_version': 1, 'content_sha256': 'a'*64, 'files': []}))
        self.report = {'schema_version': 1, 'status': 'verified_current_host',
                       'payload': str(self.payload), 'source_content_sha256': 'a'*64,
                       'binary_sha256': sha(self.binary)}
        self.inventory = {'schema_version': 1, 'files': []}
        self.proof = {'schema_version': 1, 'passed': True, 'binary': str(self.binary),
                      'binary_sha256': sha(self.binary), 'source_content_sha256': 'a'*64,
                      'checks': [{'id': 'authenticated-passive-registry-before-memory',
                                  'status': 'PASS', 'modules': 18}]}
        (self.kernel/'system-control-check').mkdir()
        self.refresh_inventory()
        self.save()
        self.runner = self.project/'validate.ps1'
        self.runner.write_text('''param($Helper,$Root,$Project,$Build,$Frontend='0.4.1-dev.3',[switch]$Apply,[switch]$NoKernel,$Inherited)
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
. $Helper
try {
  $kernel=if($NoKernel){$null}else{Get-VerifiedKernelBuild -Root $Root -ProjectRoot $Project -StagingRoot $Build}
  $old=if($Inherited){Get-Content -LiteralPath $Inherited -Raw|ConvertFrom-Json}else{$null}
  $proof=Assert-FrontendKernelCompatibility -FrontendVersion $Frontend -KernelBuild $kernel -InheritedOverride $old -Stage (Join-Path $Build 'stage') -ProjectRoot $Project -StagingRoot $Build
  if($Apply){$result=Set-VerifiedKernelPayload -KernelBuild $kernel -BuildRoot $Build -Stage (Join-Path $Build 'stage') -RegistryProof $proof}else{$result=@{proof=$proof;validated=$true}}
  $result|ConvertTo-Json -Depth 10
}catch{Write-Output $_.Exception.Message;exit 7}
''')

    def refresh_inventory(self):
        self.inventory['files'] = [{'path': path.relative_to(self.payload).as_posix(),
                                    'bytes': path.stat().st_size, 'sha256': sha(path)}
                                   for path in sorted(self.payload.rglob('*')) if path.is_file()]

    def save(self):
        for path, value in ((self.kernel/'BUILD-REPORT.json', self.report),
                            (self.kernel/'PAYLOAD-MANIFEST.json', self.inventory),
                            (self.kernel/'system-control-check/system-control-frozen.json', self.proof)):
            path.write_text(json.dumps(value))

    def invoke(self, *arguments, root=None, frontend='0.4.1-dev.3'):
        return subprocess.run([str(PWSH), '-NoLogo', '-NoProfile', '-File', str(self.runner),
            '-Helper', str(HELPER), '-Root', str(root or self.kernel), '-Project', str(self.project),
            '-Build', str(self.build), '-Frontend', frontend, *arguments],
            capture_output=True, text=True, timeout=30)

    def rejected(self, *arguments, text=None, **kwargs):
        before = {path.relative_to(self.stage).as_posix(): path.read_bytes()
                  for path in self.stage.rglob('*') if path.is_file()}
        result = self.invoke(*arguments, **kwargs)
        self.assertEqual(result.returncode, 7, result.stdout+result.stderr)
        if text:
            self.assertIn(text, result.stdout)
        self.assertEqual(before, {path.relative_to(self.stage).as_posix(): path.read_bytes()
                                 for path in self.stage.rglob('*') if path.is_file()})

    def test_good_proof_is_read_without_mutation(self):
        before = {path.relative_to(self.kernel).as_posix(): path.read_bytes()
                  for path in self.kernel.rglob('*') if path.is_file()}
        result = self.invoke()
        self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
        self.assertEqual(json.loads(result.stdout)['proof']['module_count'], 18)
        self.assertEqual(before, {path.relative_to(self.kernel).as_posix(): path.read_bytes()
                                 for path in self.kernel.rglob('*') if path.is_file()})

    def test_shared_stager_accepts_fresh_extracted_and_repackage_baselines(self):
        for lane in ('fresh-extraction', 'verified-repackage'):
            with self.subTest(lane=lane):
                (self.stage/'server/DRAGONHYDRA-Server.exe').write_bytes(('old '+lane).encode())
                result = self.invoke('-Apply')
                self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
                override = json.loads(result.stdout)
                self.assertEqual(override['binary_sha256'], sha(self.binary))
                self.assertEqual(override['registry_verification']['module_count'], 18)
                self.assertEqual((self.stage/'server/DRAGONHYDRA-Server.exe').read_bytes(), self.binary.read_bytes())
                self.assertEqual((self.stage/'server/THIRD-PARTY-NOTICES.txt').read_text(), 'Verified baseline notices')
                self.assertEqual((self.stage/'client/preserved.txt').read_text(), 'Independent client bytes')

    def test_missing_or_legacy_registry_proof_cannot_build_dev3(self):
        self.rejected('-NoKernel', text='requires an explicit verified registry-capable')
        (self.kernel/'system-control-check/system-control-frozen.json').unlink()
        self.rejected()

    def test_old_release_and_dev2_frontends_do_not_require_registry(self):
        (self.kernel/'system-control-check/system-control-frozen.json').unlink()
        for frontend in ('0.4.0-alpha.1', '0.4.1-dev.1', '0.4.1-dev.2'):
            with self.subTest(frontend=frontend):
                result = self.invoke('-NoKernel', frontend=frontend)
                self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
                self.assertIsNone(json.loads(result.stdout)['proof'])

    def test_unknown_or_failed_proof_schema_is_rejected(self):
        for field, value in (('schema_version', 2), ('passed', False), ('passed', 'true')):
            with self.subTest(field=field, value=value):
                original = self.proof[field]
                self.proof[field] = value
                self.save()
                self.rejected(text='incompatible verification, schema, binary or source')
                self.proof[field] = original

    def test_tampered_proof_binary_path_hash_and_source_are_rejected(self):
        for field, value in (('binary', str(self.project/'outside.exe')),
                             ('binary_sha256', 'b'*64), ('source_content_sha256', 'b'*64)):
            with self.subTest(field=field):
                original = self.proof[field]
                self.proof[field] = value
                self.save()
                self.rejected(text='incompatible verification, schema, binary or source')
                self.proof[field] = original

    def test_registry_check_must_be_unique_pass_and_eighteen(self):
        original = json.loads(json.dumps(self.proof['checks']))
        for checks in ([], [{'id': original[0]['id'], 'status': 'PASS', 'modules': 17}],
                       [{'id': original[0]['id'], 'status': 'NOT_RUN', 'modules': 18}], original*2):
            self.proof['checks'] = checks
            self.save()
            self.rejected(text='exactly 18 authenticated passive modules')

    def test_changed_payload_and_extra_files_are_rejected(self):
        self.binary.write_bytes(b'tampered')
        self.rejected(text='Kernel payload integrity failed')
        self.binary.write_bytes(b'new verified fixture kernel - never execute')
        (self.payload/'unexpected.txt').write_text('unexpected')
        self.rejected(text='unexpected files')

    def test_inventory_and_root_paths_cannot_escape_or_overlap(self):
        self.inventory['files'][0]['path'] = '../outside.exe'
        self.save()
        self.rejected(text='unsupported path')
        self.rejected(root=self.build, text='must be separate')
        self.rejected(root=self.project.parent/'outside', text='inside the project')

    def test_inherited_staging_requires_bound_matching_persisted_proof(self):
        result = self.invoke('-Apply')
        self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
        inherited = json.loads(result.stdout)
        marker = self.project/'inherited.json'
        marker.write_text(json.dumps(inherited))
        good = self.invoke('-NoKernel', '-Inherited', str(marker))
        self.assertEqual(good.returncode, 0, good.stdout+good.stderr)
        inherited['registry_verification']['proof_sha256'] = 'b'*64
        marker.write_text(json.dumps(inherited))
        self.rejected('-NoKernel', '-Inherited', str(marker), text='differs from its current bound receipt')

    def test_inherited_stage_binary_must_still_match_verified_proof(self):
        result = self.invoke('-Apply')
        self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
        marker = self.project/'inherited.json'
        marker.write_text(result.stdout)
        (self.stage/'server/DRAGONHYDRA-Server.exe').write_bytes(b'tampered staged bytes')
        self.rejected('-NoKernel', '-Inherited', str(marker), text='differs from its registry-capable verified payload')

    def test_fresh_dev3_build_fails_before_output_or_stage_without_proof(self):
        scripts = self.project/'scripts'
        helpers = self.project/'packaging/windows/workstation'
        scripts.mkdir()
        helpers.mkdir(parents=True)
        shutil.copyfile(ROOT/'scripts/Build-Workstation.ps1', scripts/'Build-Workstation.ps1')
        for name in ('ClientBuild.ps1', 'KernelBuild.ps1'):
            shutil.copyfile(ROOT/'packaging/windows/workstation'/name, helpers/name)
        xml = self.project/'server/joomla/pkg_dragonhydra.xml'
        xml.parent.mkdir(parents=True)
        xml.write_text('<extension><version>0.4.1-dev.3</version></extension>')
        package = self.project/'frontend.zip'
        package.write_bytes(b'fixture archive identity; never extracted')
        package.with_suffix('.manifest.json').write_text(json.dumps({'built': True,
            'version': '0.4.1-dev.3', 'frontend_setup': 'fixture', 'child_template_files': 2,
            'sha256': sha(package), 'bytes': package.stat().st_size, 'source_sha': None}))
        tool = self.project/'must-not-execute.exe'
        tool.write_bytes(b'Not an executable')
        build, output = self.project/'build/connections/fresh-default', self.project/'dist/fresh-output'
        command = [str(PWSH), '-NoLogo', '-NoProfile', '-File', str(scripts/'Build-Workstation.ps1'),
            '-BuildRoot', str(build), '-OutputRoot', str(output), '-JoomlaPackagePath', str(package),
            '-SevenZip', str(tool), '-MakeNsis', str(tool)]
        result = subprocess.run(command, capture_output=True, text=True, timeout=30)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('requires an explicit verified registry-capable', result.stdout+result.stderr)
        self.assertFalse(build.exists())
        self.assertFalse(output.exists())
        # A valid explicit kernel is accepted on the fresh lane, then the next
        # immutable-baseline gate still runs. No extraction/build is attempted.
        accepted = subprocess.run(command+['-KernelBuildRoot', str(self.kernel)],
                                  capture_output=True, text=True, timeout=30)
        self.assertNotEqual(accepted.returncode, 0)
        self.assertIn('ARTIFACT-MANIFEST.json', accepted.stdout+accepted.stderr)
        self.assertNotIn('requires an explicit verified registry-capable', accepted.stdout+accepted.stderr)
        self.assertFalse(build.exists())
        self.assertFalse(output.exists())


if __name__ == '__main__':
    unittest.main()
