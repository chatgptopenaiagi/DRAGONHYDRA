"""Presentation migration invariants; no live site, credentials or database writes."""
import importlib.util
import io
import json
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


if __name__ == '__main__':
    unittest.main()
