from dataclasses import replace
from pathlib import Path
import tempfile
import unittest

from dragonhydra.config import PROJECT_ROOT, load_probe_credential, load_settings, project_path


class ConfigurationTests(unittest.TestCase):
    def test_direct_settings_cannot_bypass_invariants(self):
        settings = load_settings()
        for change in ({"host": "192.168.8.8"}, {"table_prefix": "bad`;DROP"},
                       {"database": "mysql"}, {"secret_file": PROJECT_ROOT.parent / "htdocs/secret.json"},
                       {"driver_directory": PROJECT_ROOT.parent}, {"absolute_tolerance": float("nan")}):
            with self.subTest(fields=tuple(change)), self.assertRaises(ValueError):
                replace(settings, **change)

    def test_project_escape_rejected(self):
        with self.assertRaises(ValueError):
            project_path("../htdocs/secret.json")

    def test_remote_database_rejected(self):
        original = (PROJECT_ROOT / "config/genesis.toml").read_text()
        with tempfile.TemporaryDirectory(dir=PROJECT_ROOT / "runtime/tmp") as temporary:
            path = Path(temporary) / "bad.toml"
            path.write_text(original.replace('host = "127.0.0.1"', 'host = "192.168.8.8"'))
            with self.assertRaisesRegex(ValueError, "loopback"):
                load_settings(path)

    def test_configuration_secret_storage_outside_webroot(self):
        settings = load_settings()
        self.assertTrue(settings.secret_file.is_relative_to(PROJECT_ROOT / "runtime/secrets"))
        self.assertFalse(settings.secret_file.is_relative_to(PROJECT_ROOT.parent / "htdocs"))

    def test_plaintext_probe_secret_absent_from_source_config_docs(self):
        settings = load_settings()
        secret = load_probe_credential(settings)
        examined = 0
        for folder in ["config", "src", "scripts", "docs", "tests", "research"]:
            for path in (PROJECT_ROOT / folder).rglob("*"):
                if path.is_file() and path.suffix in {".py", ".php", ".ps1", ".toml", ".md", ".json"}:
                    content = path.read_text(encoding="utf-8-sig")
                    self.assertFalse(secret.password in content, f"Secret leaked in {path.relative_to(PROJECT_ROOT)}")
                    examined += 1
        self.assertGreater(examined, 10)

    def test_credential_repr_does_not_reveal_password(self):
        secret = load_probe_credential(load_settings())
        self.assertFalse(secret.password in repr(secret), "Secret leaked in repr")

    def test_no_password_key_in_nonsecret_config(self):
        content = (PROJECT_ROOT / "config/genesis.toml").read_text()
        self.assertNotIn("password", content.casefold())


if __name__ == "__main__":
    unittest.main()
