"""Source-bound Joomla inputs are checked before any CoreNext payload copy."""
import hashlib
import io
import json
from pathlib import Path
import re
import subprocess
import tempfile
import unittest
import zipfile

ROOT=Path(__file__).resolve().parents[1]
LAB=Path(r'C:\xampp\DRAGONHYDRA-CORE-NEXT-LAB')
PWSH=Path(r'C:\Program Files\PowerShell\7\pwsh.exe')
EXPECTED='b'*40
VERSION='0.9.7-dev.12'  # The guard follows the profile, not an old release number.

@unittest.skipUnless(PWSH.is_file(),'Existing PowerShell 7 is required')
class JoomlaPayloadInputs(unittest.TestCase):
    def setUp(self):
        base=LAB/'tests';base.mkdir(exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(dir=base,prefix='joomla-payload-input-')
        self.folder=Path(self.temp.name)
        self.addCleanup(self.cleanup)

    def cleanup(self):
        assert self.folder.resolve().is_relative_to((LAB/'tests').resolve())
        self.temp.cleanup()

    def package(self,*,receipt_source=EXPECTED,embedded_source=EXPECTED,embedded_version=VERSION,duplicate=False,
                package_version=VERSION,component_version=VERSION,built=True,kernel_schema=1):
        component=io.BytesIO()
        with zipfile.ZipFile(component,'w') as archive:
            identity=json.dumps(dict(source_sha=embedded_source,version=embedded_version,
                schema_version=1,api_namespace='/dragon/api/v1',kernel_schema_version=kernel_schema))
            archive.writestr('admin/build-info.json',identity)
            archive.writestr('dragonhydra.xml','<extension><version>'+component_version+'</version></extension>')
            if duplicate:archive.writestr('ADMIN/BUILD-INFO.JSON',identity)
        path=self.folder/'extension.zip'
        with zipfile.ZipFile(path,'w') as archive:
            archive.writestr('constituents/com_dragonhydra.zip',component.getvalue())
            archive.writestr('pkg_dragonhydra.xml','<extension><version>'+package_version+'</version></extension>')
        receipt=dict(built=built,version=VERSION,source_sha=receipt_source,
            sha256=hashlib.sha256(path.read_bytes()).hexdigest(),bytes=path.stat().st_size)
        path.with_suffix('.manifest.json').write_text(json.dumps(receipt),encoding='utf-8')
        return path

    def validate(self,path,*,source=EXPECTED,version=VERSION):
        # Execute the actual pre-copy validation block, never the builder/copy,
        # compiler, service, NSIS or installer portions of Prepare-CoreNextPayload.
        text=(ROOT/'scripts/Prepare-CoreNextPayload.ps1').read_text(encoding='utf-8-sig')
        start=text.index('$extension=$null')
        stop=text.index('# Inputs are completely checked before a fresh destination is created.')
        block=text[start:stop]
        hash_function=re.search(r'^function Hash\([^\n]+$',text,re.M).group(0)
        quote=lambda p:str(p).replace("'","''")
        script=("$ErrorActionPreference='Stop';. '"+quote(ROOT/'packaging/windows/workstation/CoreNextProfile.ps1')+"';"
            "$lab='"+quote(LAB)+"';$profile=@{source_commit='"+source+"';version='"+version+"'};"
            "$JoomlaPackagePath='"+quote(path)+"';"+hash_function+"\ntry{\n"+block+
            "\n@{accepted=$true;path=$extension}|ConvertTo-Json -Compress}catch{Write-Output 'REJECTED';exit 7}")
        result=subprocess.run([str(PWSH),'-NoLogo','-NoProfile','-NonInteractive','-Command',script],
            capture_output=True,text=True,timeout=25)
        self.assertFalse((self.folder/'stage').exists(),'Validation must never create a payload destination')
        return result

    def test_matching_source_and_future_profile_version_pass_without_building(self):
        result=self.validate(self.package())
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertTrue(json.loads(result.stdout)['accepted'])

    def test_same_version_stale_source_receipt_is_rejected(self):
        result=self.validate(self.package(receipt_source='a'*40,embedded_source='a'*40))
        self.assertEqual(result.returncode,7,result.stdout+result.stderr)

    def test_relabelled_receipt_cannot_hide_stale_embedded_component_source(self):
        result=self.validate(self.package(embedded_source='a'*40))
        self.assertEqual(result.returncode,7,result.stdout+result.stderr)

    def test_wrong_embedded_version_or_ambiguous_identity_is_rejected(self):
        result=self.validate(self.package(embedded_version='0.9.7-dev.11'))
        self.assertEqual(result.returncode,7,result.stdout+result.stderr)
        with tempfile.TemporaryDirectory(dir=self.folder) as name:
            original=self.folder;self.folder=Path(name)
            try:result=self.validate(self.package(duplicate=True))
            finally:self.folder=original
        self.assertEqual(result.returncode,7,result.stdout+result.stderr)

    def test_existing_hash_and_size_contract_still_rejects_tampering(self):
        path=self.package();path.write_bytes(path.read_bytes()+b'changed')
        self.assertEqual(self.validate(path).returncode,7)

    def test_declared_package_and_component_versions_must_match_the_profile(self):
        for key in ('package_version','component_version'):
            with self.subTest(declaration=key):
                result=self.validate(self.package(**{key:'0.9.7-dev.11'}))
                self.assertEqual(result.returncode,7,result.stdout+result.stderr)

    def test_built_and_schema_types_are_not_coerced_from_strings_or_booleans(self):
        for arguments in ({'built':'true'},{'kernel_schema':True},{'kernel_schema':'1'}):
            with self.subTest(arguments=arguments):
                result=self.validate(self.package(**arguments))
                self.assertEqual(result.returncode,7,result.stdout+result.stderr)

    def test_preserved_real_same_version_candidates_keep_their_source_binding(self):
        old=LAB/'dist/joomla-dev4-r1/pkg_dragonhydra-0.5.0-dev.4.zip'
        current=LAB/'dist/joomla-dev4-r2/pkg_dragonhydra-0.5.0-dev.4.zip'
        if not old.is_file() or not current.is_file():
            self.skipTest('Optional preserved public build artifacts unavailable; synthetic contracts remain covered')
        expected='ede5bf788097abc136eee2ae726248893fb4ae7b'
        self.assertEqual(self.validate(current,source=expected,version='0.5.0-dev.4').returncode,0)
        self.assertEqual(self.validate(old,source=expected,version='0.5.0-dev.4').returncode,7)

if __name__=='__main__':unittest.main()
