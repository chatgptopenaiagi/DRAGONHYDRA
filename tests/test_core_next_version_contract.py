"""Cross-package identity must agree before any expensive native build."""
import json
import importlib.util
from pathlib import Path
import re
import tomllib
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]


class VersionContractTests(unittest.TestCase):
    def test_affected_product_versions_and_private_runtime_identity_agree(self):
        matrix = json.loads((ROOT/'packaging/release/version.json').read_text())
        project = tomllib.loads((ROOT/'pyproject.toml').read_text())
        cargo = tomllib.loads((ROOT/'client/desktop/src-tauri/Cargo.toml').read_text())
        locked = tomllib.loads((ROOT/'client/desktop/src-tauri/Cargo.lock').read_text())
        desktop = next(package for package in locked['package'] if package['name'] == 'dragonhydra-desktop')
        package = json.loads((ROOT/'client/desktop/package.json').read_text())
        npm = json.loads((ROOT/'client/desktop/package-lock.json').read_text())
        tauri = json.loads((ROOT/'client/desktop/src-tauri/tauri.conf.json').read_text())
        self.assertEqual(project['project']['version'], matrix['python_version'])
        for value in (cargo['package']['version'], desktop['version'], package['version'],
                      npm['version'], npm['packages']['']['version'], tauri['version']):
            self.assertEqual(value, matrix['desktop_version'])
        metadata = (ROOT/'src/dragonhydra/build_meta.py').read_text()
        self.assertIn("VERSION = '"+matrix['product_version']+"'", metadata)
        self.assertIn("PYTHON_VERSION = '"+matrix['python_version']+"'", metadata)
        pe = (ROOT/'packaging/windows/version_info.txt').read_text()
        self.assertIn("StringStruct('FileVersion', '"+matrix['windows_file_version']+"')", pe)
        self.assertIn("StringStruct('ProductVersion', '"+matrix['product_version']+"')", pe)
        self.assertEqual(tauri['identifier'], 'ai.dragonhydra.corenext.desktop')
        for name in ('pkg_dragonhydra.xml', 'com_dragonhydra/dragonhydra.xml',
                     'tpl_cassiopeia_dragonhydra/templateDetails.xml'):
            self.assertEqual(ET.parse(ROOT/'server/joomla'/name).getroot().findtext('version'), matrix['joomla_version'])
        self.assertEqual(json.loads((ROOT/'server/joomla/com_dragonhydra/media/joomla.asset.json').read_text())['version'], matrix['joomla_version'])

    def test_android_release_identity_matches_actual_pubspec_and_dependency_pins_stay_fixed(self):
        matrix = json.loads((ROOT/'packaging/release/version.json').read_text())
        declared = re.findall(r'^version:\s*([^+\s]+)\+(\d+)\s*$', (ROOT/'android/dragonhydra_mobile/pubspec.yaml').read_text(), re.M)
        self.assertEqual(len(declared), 1)
        self.assertEqual(declared[0], (matrix['android_version_name'], str(matrix['android_version_code'])))
        self.assertEqual(matrix['android_version_name'], matrix['product_version'])
        self.assertEqual(matrix['android_version_code'], 10)
        self.assertIn('[int]$VersionCode='+str(matrix['android_version_code']),
                      (ROOT/'scripts/release_android.ps1').read_text())
        cargo = tomllib.loads((ROOT/'client/desktop/src-tauri/Cargo.toml').read_text())
        self.assertEqual(cargo['dependencies']['tauri']['version'], '=2.12.5')
        self.assertEqual(cargo['dependencies']['tauri-plugin-opener'], '=2.7.2')
        self.assertEqual(cargo['build-dependencies']['tauri-build']['version'], '=2.7.4')
        self.assertEqual(json.loads((ROOT/'client/desktop/package.json').read_text())['devDependencies']['@tauri-apps/cli'], '2.12.4')
        matrix_version = matrix['windows_file_version'].split('.')
        self.assertEqual(len(matrix_version), 4)
        self.assertTrue(all(re.fullmatch(r'\d+', item) for item in matrix_version))

    def test_dependency_cache_accepts_only_our_excluded_package_version_change(self):
        spec = importlib.util.spec_from_file_location('version_contract_cache', ROOT/'scripts/core_next_cargo_cache.py')
        cache = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cache)
        original = b'version = 4\n[[package]]\nname = "dragonhydra-desktop"\nversion = "0.5.0-dev.1"\ndependencies = ["dependency"]\n[[package]]\nname = "dependency"\nversion = "1.2.3"\nchecksum = "fixed"\n'
        own_version = original.replace(b'0.5.0-dev.1', b'0.5.0-dev.2')
        self.assertTrue(cache.same_locked_dependencies(original, own_version))
        for changed in (own_version.replace(b'1.2.3', b'1.2.4'), own_version.replace(b'"fixed"', b'"changed"'),
                        own_version.replace(b'["dependency"]', b'[]'), own_version.replace(b'checksum = "fixed"', b'checksum = "fixed"\nsource = "different"')):
            self.assertFalse(cache.same_locked_dependencies(original, changed))
        for invalid in (own_version.replace(b'dragonhydra-desktop', b'different-app'),
                        own_version+b'[[package]]\nname = "dragonhydra-desktop"\nversion = "0.5.0-dev.2"\n'):
            with self.assertRaises(ValueError):
                cache.same_locked_dependencies(original, invalid)


if __name__ == '__main__':
    unittest.main()
