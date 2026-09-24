from dataclasses import replace
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from dragonhydra.config import PROJECT_ROOT, load_probe_credential, load_settings
from dragonhydra.integration.dual_database import run_dual_database
from dragonhydra.storage.sqlserver import lab_grants_are_exact, local_connection_options, odbc_value
from dragonhydra.storage.sqlserver_config import load_sqlserver_credential, load_sqlserver_settings


class DualDatabaseConfigurationTests(unittest.TestCase):
    def test_configurations_parse_and_ports_differ(self):
        self.assertNotEqual(load_settings().port, load_sqlserver_settings().port)

    def test_sql_settings_reject_remote_host_and_wrong_database(self):
        settings = load_sqlserver_settings()
        for changed in ({"host": "192.168.8.8"}, {"database": "master"}, {"encrypt": False},
                        {"secret_file": PROJECT_ROOT.parent / "htdocs/secret.json"},
                        {"driver_directory": PROJECT_ROOT.parent}):
            with self.subTest(fields=tuple(changed)), self.assertRaises(ValueError):
                replace(settings, **changed)

    def test_database_port_collision_fails_before_connections(self):
        bad = replace(load_sqlserver_settings(), port=load_settings().port)
        with patch("dragonhydra.integration.dual_database.load_sqlserver_settings", return_value=bad):
            with self.assertRaisesRegex(ValueError, "distinct"):
                run_dual_database()

    def test_sql_timeout_rejects_booleans_and_fractions(self):
        for value in (True, 1.5):
            with self.subTest(value=value), self.assertRaises(ValueError):
                replace(load_sqlserver_settings(), connect_timeout_seconds=value)

    def test_explicit_permission_policy_accepts_only_declared_scope(self):
        expected = [(0, 0, 0, "CONNECT", "GRANT"), (1, 123, 0, "SELECT", "GRANT")]
        self.assertTrue(lab_grants_are_exact(expected, 123))

    def test_extra_object_write_cannot_hide_behind_safe_sample_permissions(self):
        grants = [(0, 0, 0, "CONNECT", "GRANT"), (1, 123, 0, "SELECT", "GRANT"),
                  (1, 456, 0, "UPDATE", "GRANT")]
        self.assertFalse(lab_grants_are_exact(grants, 123))

    def test_schema_grant_or_grant_option_is_rejected(self):
        base = [(0, 0, 0, "CONNECT", "GRANT"), (1, 123, 0, "SELECT", "GRANT")]
        self.assertFalse(lab_grants_are_exact(base + [(3, 1, 0, "CONTROL", "GRANT")], 123))
        self.assertFalse(lab_grants_are_exact([base[0], (1, 123, 0, "SELECT", "GRANT_WITH_GRANT_OPTION")], 123))

    def test_encryption_and_loopback_exception_are_explicit(self):
        options = local_connection_options(load_sqlserver_settings())
        self.assertIn("Encrypt=yes;", options)
        self.assertIn("TrustServerCertificate=yes;", options)
        self.assertNotIn("PWD=", options)

    def test_odbc_secret_value_cannot_inject_connection_options(self):
        self.assertEqual(odbc_value("a};TrustServerCertificate=no;"), "{a}};TrustServerCertificate=no;}")

    def test_config_cannot_embed_password(self):
        source = (PROJECT_ROOT / "config/databases.toml").read_text()
        with tempfile.TemporaryDirectory(dir=PROJECT_ROOT / "runtime/tmp") as temporary:
            path = Path(temporary) / "bad.toml"
            path.write_text(source.replace("[sqlserver]", '[sqlserver]\npassword="invalid"'))
            with self.assertRaisesRegex(ValueError, "Credentials"):
                load_sqlserver_settings(path)

    def test_secrets_absent_from_source_config_and_checkpoints(self):
        passwords = (load_probe_credential(load_settings()).password,
                     load_sqlserver_credential(load_sqlserver_settings()).password)
        paths = []
        for folder in ("src", "config", "scripts", "docs", "research", "tests", "runtime/checkpoints"):
            paths.extend(path for path in (PROJECT_ROOT / folder).rglob("*")
                         if path.is_file() and path.suffix in {".py", ".php", ".ps1", ".toml", ".md", ".json", ".log"})
        for path in paths:
            content = path.read_text(encoding="utf-8-sig")
            for password in passwords:
                self.assertFalse(password in content, f"Credential leak in {path.relative_to(PROJECT_ROOT)}")
        self.assertFalse(passwords[1] in repr(load_sqlserver_credential(load_sqlserver_settings())))


class LiveDualDatabaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = run_dual_database()

    def test_python_314_invariant(self):
        self.assertEqual(sys.version_info[:2], (3, 14))
        self.assertEqual(Path(sys.executable).resolve(), load_settings().python_executable.resolve())

    def test_both_database_services_and_apache_running(self):
        self.assertTrue(self.result["required_services_running"])

    def test_simultaneous_distinct_port_listeners(self):
        self.assertTrue(self.result["simultaneous_database_listeners"])
        self.assertNotEqual(self.result["mariadb"]["port"], self.result["sqlserver"]["port"])

    def test_mariadb_health_and_aggregate_read(self):
        self.assertEqual(self.result["mariadb"]["status"], "healthy")
        self.assertTrue(self.result["mariadb"]["read"])
        self.assertEqual(self.result["mariadb"]["aggregates"]["table_count"], 76)

    def test_sqlserver_health_and_lab_read(self):
        self.assertEqual(self.result["sqlserver"]["status"], "healthy")
        self.assertEqual(self.result["sqlserver"]["database"], "DRAGONHYDRA_LAB")
        self.assertEqual(self.result["sqlserver"]["aggregates"], {"row_count": 2, "quantity_sum": 30})

    def test_mariadb_identity_rejects_writes(self):
        self.assertFalse(self.result["mariadb"]["write"])
        self.assertTrue(self.result["mariadb"]["write_rejected"])

    def test_sqlserver_bounded_identity_and_permissions(self):
        details = self.result["sqlserver_permission_details"]
        self.assertTrue(details["bounded_identity"])
        self.assertEqual(details["server_roles"], [])
        self.assertEqual(details["database_roles"], [])
        self.assertEqual(details["object_permissions"], ["SELECT"])
        self.assertEqual(details["write_denied_native_error"], 229)
        self.assertTrue(details["counts_unchanged"])
        self.assertEqual(details["writable_schema_count"], 0)
        self.assertEqual(details["visible_user_objects"], [("probe", "CapabilitySample")])

    def test_both_adapters_report_transaction_capability(self):
        self.assertTrue(self.result["mariadb"]["transaction"])
        self.assertTrue(self.result["sqlserver"]["transaction"])

    def test_joomla_http_and_php_regression(self):
        check = self.result["joomla"]
        self.assertEqual(check["http_status"], 200)
        self.assertTrue(check["joomla_marker"])
        self.assertTrue(check["site_name_present"])
        self.assertFalse(check["php_source_exposed"])

    def test_unified_capability_report_passes(self):
        self.assertTrue(self.result["passed"])


if __name__ == "__main__":
    unittest.main()
