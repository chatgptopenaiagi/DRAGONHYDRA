"""Run the replacement-client payload validator through the installed PowerShell."""
import hashlib
import json
import os
from pathlib import Path
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
        self.runner.write_text(
            "param($Helper,$Root,$Project,$Stage,[switch]$StagingCopy)\n$ErrorActionPreference='Stop'\n"
            ". $Helper\ntry {if($StagingCopy){$result=Get-VerifiedClientStagingCopy -Root $Stage -ProjectRoot $Project}"
            "else{$result=Get-VerifiedClientBuild -Root $Root -ProjectRoot $Project -StagingRoot $Stage};$result | "
            "ConvertTo-Json -Depth 8} catch {Write-Output $_.Exception.Message;exit 7}\n")

    def refresh_entries(self):
        self.manifest['files'] = [{'path':p.name, 'bytes':p.stat().st_size,
                                   'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
                                  for p in sorted(self.client.iterdir()) if p.name != 'CLIENT-BUILD.json']
        self.save()

    def save(self):
        (self.client/'CLIENT-BUILD.json').write_text(json.dumps(self.manifest))

    def invoke(self, *, client=None, stage=None, staging_copy=False):
        command = [str(PWSH), '-NoLogo', '-NoProfile', '-File', str(self.runner),
                   '-Helper', str(HELPER), '-Root', str(client or self.client),
                   '-Project', str(self.project), '-Stage', str(stage or self.stage)]
        if staging_copy:
            command.append('-StagingCopy')
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


if __name__ == '__main__':
    unittest.main()
