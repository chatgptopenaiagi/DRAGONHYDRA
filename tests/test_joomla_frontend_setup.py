"""Presentation migration invariants; no live site, credentials or database writes."""
import importlib.util
import io
import hashlib
import json
import re
from pathlib import Path
import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'server/joomla'
PHP = ROOT / 'build/workstation/test-install/application files/web/php/php.exe'
SETUP = SOURCE / 'com_dragonhydra/admin/src/Service/FrontendSetup.php'


def visible(assignments, menu):
    """Joomla's documented positive/all-pages/negative module assignment semantics."""
    if -menu in assignments:
        return False
    return menu in assignments or any(value <= 0 for value in assignments)


class JoomlaFrontendSetupTests(unittest.TestCase):
    @unittest.skipUnless(PHP.is_file(), 'Selected installed private PHP required')
    def test_actual_assignment_loop_accepts_joomla_by_reference_insert_contract(self):
        # Execute the actual small write loop, using the installed driver's
        # by-reference contract without connecting to or writing a database.
        source = SETUP.read_text()
        loop = re.search(r'foreach \(\$after as \$menuId\) \{(.*?)\n\s*\}', source, re.S)
        self.assertIsNotNone(loop)
        code = ("$db=new class{public array $rows=[];public function insertObject($table,&$object,$key=null){"
                "$this->rows[]=['table'=>$table,'moduleid'=>$object->moduleid,'menuid'=>$object->menuid];return true;}};"
                "$originalRejected=false;try{$db->insertObject('#__modules_menu',(object)['moduleid'=>7,'menuid'=>-77]);}"
                "catch(Error $e){$originalRejected=true;}$moduleId=7;$after=[-77,0];foreach($after as $menuId){" +
                loop.group(1) + "}echo json_encode(['original_expression_rejected'=>$originalRejected,'rows'=>$db->rows]);")
        result = subprocess.run([str(PHP), '-n', '-r', code], capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), {'original_expression_rejected': True, 'rows': [
            {'table': '#__modules_menu', 'moduleid': 7, 'menuid': -77},
            {'table': '#__modules_menu', 'moduleid': 7, 'menuid': 0},
        ]})

    @unittest.skipUnless(PHP.is_file(), 'Selected installed private PHP required')
    def test_home_exclusion_retains_other_page_behavior_and_is_idempotent(self):
        cases = [[0], [-91], [77], [77, 91], [91], [], [0, 91], [-77, 0]]
        code = ("define('_JEXEC',1);require " + json.dumps(str(SETUP)) + ";$cases=json_decode(" +
                json.dumps(json.dumps(cases)) + ",true);$out=[];foreach($cases as $case){$next=" +
                "\\Dragonhydra\\Component\\Dragonhydra\\Administrator\\Service\\FrontendSetup::excludeMenu($case,77);" +
                "$out[]=[$next,\\Dragonhydra\\Component\\Dragonhydra\\Administrator\\Service\\FrontendSetup::excludeMenu($next,77)];}echo json_encode($out);")
        result = subprocess.run([str(PHP), '-n', '-r', code], capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        transformed = json.loads(result.stdout)
        for original, (after, repeated) in zip(cases, transformed):
            self.assertFalse(visible(after, 77), (original, after))
            self.assertEqual(after, repeated)
            for other in (1, 78, 91, 105):
                self.assertEqual(visible(original, other), visible(after, other), (original, after, other))

    def test_template_installs_before_component_and_has_parent(self):
        package = ET.parse(SOURCE / 'pkg_dragonhydra.xml').getroot()
        self.assertEqual([node.get('type') for node in package.findall('files/file')], ['template', 'component'])
        child = ET.parse(SOURCE / 'tpl_cassiopeia_dragonhydra/templateDetails.xml').getroot()
        self.assertEqual(child.findtext('parent'), 'cassiopeia')
        self.assertEqual(child.findtext('version'), package.findtext('version'))

    def test_component_manifest_deploys_site_and_scoped_media(self):
        manifest = ET.parse(SOURCE / 'com_dragonhydra/dragonhydra.xml').getroot()
        self.assertEqual(manifest.find('files').get('folder'), 'site')
        self.assertEqual(manifest.find('media').get('destination'), 'com_dragonhydra')
        self.assertEqual(manifest.findtext('media/filename'), 'joomla.asset.json')
        setup = SETUP.read_text()
        self.assertIn('new Menu($db)', setup)
        self.assertIn('transactionStart()', setup)
        self.assertNotIn('DELETE FROM', setup)
        self.assertNotIn('#__users', setup)
        self.assertNotIn('core.sqlite3', setup)

    def test_repair_calls_same_scoped_joomla_setup(self):
        manage = (ROOT / 'packaging/windows/workstation/web/manage.php').read_text()
        self.assertIn("runChild($cfg, [__FILE__, $configPath, '_configure-frontend']", manage)
        self.assertIn('FrontendSetup::apply()', manage)
        self.assertIn('FrontendSetup::apply()', (SOURCE / 'com_dragonhydra/script.php').read_text())

    def test_builder_reproducibly_includes_both_extensions_and_assets(self):
        spec = importlib.util.spec_from_file_location('frontend_joomla_builder', ROOT / 'scripts/build_joomla.py')
        builder = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(builder)
        scratch = ROOT / 'runtime/scratch'
        scratch.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='frontend-package-', dir=scratch) as temporary:
            target = Path(temporary) / 'package.zip'
            first = builder.build(target)
            second = builder.build(target)
            self.assertEqual(first['sha256'], second['sha256'])
            with zipfile.ZipFile(target) as package:
                self.assertIn('constituents/tpl_cassiopeia_dragonhydra.zip', package.namelist())
                with zipfile.ZipFile(io.BytesIO(package.read('constituents/com_dragonhydra.zip'))) as component:
                    self.assertIn('admin/src/Service/FrontendSetup.php', component.namelist())
                    if (SOURCE / 'com_dragonhydra/media/joomla.asset.json').exists():
                        self.assertIn('media/joomla.asset.json', component.namelist())
                    self.assertNotIn('configuration.php', component.namelist())

    def test_verified_web_refresh_reuses_other_files_and_rejects_tampering(self):
        def module(name, path):
            spec = importlib.util.spec_from_file_location(name, path)
            value = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(value)
            return value
        builder = module('refresh_extension_builder', ROOT / 'scripts/build_joomla.py')
        prep = module('refresh_web_inputs', ROOT / 'packaging/windows/workstation/web/prepare_payload.py')
        base = ROOT / 'build/frontend-setup-tests'
        base.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='reuse-', dir=base) as temporary:
            temp = Path(temporary).resolve()
            self.assertTrue(temp.is_relative_to((ROOT / 'build').resolve()))
            package = temp / 'extension.zip'
            builder.build(package)
            old = temp / 'old'; old.mkdir()
            contents = {'extension.zip': b'old extension', 'manage.php': b'old hook',
                        'README.md': b'old documentation', 'runtime.bin': b'verified unchanged runtime'}
            rows = []
            for name, data in contents.items():
                (old / name).write_bytes(data)
                rows.append({'path': name, 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()})
            (old / 'payload-manifest.json').write_text(json.dumps({'platform': 'windows', 'architecture': 'x64',
                'source_sha': 'a' * 40, 'files': rows, 'components': {}}), encoding='utf-8')
            result = prep.refresh_payload(old, temp / 'new', package)
            self.assertTrue(result['prepared'])
            self.assertEqual((temp / 'new/runtime.bin').read_bytes(), contents['runtime.bin'])
            self.assertEqual((old / 'manage.php').read_bytes(), contents['manage.php'])
            with self.assertRaises(ValueError):
                prep.refresh_payload(old, temp / 'new', package)
            (old / 'runtime.bin').write_bytes(b'tampered')
            with self.assertRaises(ValueError):
                prep.refresh_payload(old, temp / 'rejected', package)
            self.assertFalse((temp / 'rejected').exists())

    @unittest.skipUnless(Path('C:/Program Files/PowerShell/7/pwsh.exe').is_file(), 'Selected PowerShell 7 required')
    def test_workstation_package_gate_accepts_verified_input_and_rejects_changed_bytes(self):
        spec = importlib.util.spec_from_file_location('workstation_extension_builder', ROOT / 'scripts/build_joomla.py')
        builder = importlib.util.module_from_spec(spec); spec.loader.exec_module(builder)
        scratch = ROOT / 'runtime/scratch'; scratch.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='workstation-frontend-', dir=scratch) as temporary:
            temp = Path(temporary).resolve()
            self.assertTrue(temp.is_relative_to(scratch.resolve()))
            package = temp / 'extension.zip'; builder.build(package)
            quote = lambda value: "'" + str(value).replace("'", "''") + "'"
            script = ("$ErrorActionPreference='Stop';Set-StrictMode -Version Latest;"
                      "$project=" + quote(ROOT) + ";"
                      "function Hash([string]$Path){(Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()};"
                      "$tokens=$null;$errors=$null;$ast=[Management.Automation.Language.Parser]::ParseFile(" +
                      quote(ROOT / 'scripts/Build-Workstation.ps1') + ",[ref]$tokens,[ref]$errors);"
                      "if($errors.Count){throw 'parse error'};"
                      "$fn=$ast.Find({param($n)$n -is [Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -eq 'Get-VerifiedFrontendPackage'},$true);"
                      "Invoke-Expression $fn.Extent.Text;"
                      "$accepted=Get-VerifiedFrontendPackage " + quote(package) + ";"
                      "[IO.File]::AppendAllText(" + quote(package) + ",'tamper');"
                      "$rejected=$false;try{Get-VerifiedFrontendPackage " + quote(package) + "|Out-Null}catch{$rejected=$true};"
                      "@{accepted=($accepted.version -eq '0.4.1-dev.2');tampered_rejected=$rejected}|ConvertTo-Json")
            result = subprocess.run(['C:/Program Files/PowerShell/7/pwsh.exe', '-NoProfile', '-Command', script],
                                    capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout), {'accepted': True, 'tampered_rejected': True})


if __name__ == '__main__':
    unittest.main()
