"""The repository scanner must fail closed without printing matched values."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location(
    "repository_audit", Path(__file__).resolve().parents[1] / "scripts/repository_audit.py"
)
scanner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scanner)


class RepositoryAuditTests(unittest.TestCase):
    def test_recognizes_token_without_returning_value(self):
        value = "gh" + "p_" + "x" * 36
        findings = scanner.scan_text("configuration = " + repr(value))
        self.assertEqual(findings, [{"rule": "github_token", "line": 1}])
        self.assertNotIn(value, json.dumps(findings))

    def test_detects_literal_but_accepts_reference_and_random_generator(self):
        value = "a-long-" + "embedded-credential"
        self.assertTrue(scanner.scan_text("password = " + repr(value)))
        self.assertFalse(scanner.scan_text('password = os.environ["DB_PASSWORD"]'))
        self.assertFalse(scanner.scan_text('password = "prefix" + secrets.token_urlsafe(36)'))
        self.assertFalse(scanner.scan_text('connect(password=secret.password)'))

    def test_streaming_known_secret_crosses_chunk_boundary(self):
        value = b"synthetic-" + b"boundary-sentinel"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "binary.bin"
            path.write_bytes(b"\0" * (1024 * 1024 - 5) + value + b"\0")
            self.assertTrue(scanner.contains_known_value(path, {value}))

    def test_local_known_secret_copy_in_authored_file_blocks(self):
        value = "sentinel-" + "uncommittable-credential"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            protected = root / "runtime/secrets/account.local.json"
            protected.parent.mkdir(parents=True)
            protected.write_text(json.dumps({"password": value}))
            (root / "innocent.txt").write_text(value)
            result = scanner.audit(root, all_local=True)
            self.assertFalse(result["passed"])
            self.assertEqual(result["known_local_secret_value_count"], 1)
            self.assertNotIn(value, json.dumps(result))
            self.assertTrue(any(f["path"] == "innocent.txt" and f["rule"] == "known_local_secret_bytes" and f["blocking"] for f in result["findings"]))

    def test_tracked_ignored_path_is_blocking(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "runtime/checkpoints/public.json"
            path.parent.mkdir(parents=True)
            path.write_text("{}")
            with patch.object(scanner, "git_paths", return_value=[path]):
                result = scanner.audit(root, tracked=True)
            self.assertFalse(result["passed"])
            self.assertEqual(result["findings"][0]["rule"], "tracked_generated_or_sensitive_path")

    def test_allowlist_is_exact_and_does_not_hide_other_tests(self):
        finding = {"rule": "credential_url", "line": 1}
        self.assertFalse(scanner.reviewed_synthetic("tests/test_handoff_bridge.py", finding, ["new unreviewed content"]))
        self.assertFalse(scanner.reviewed_synthetic("tests/new_test.py", finding, ["new unreviewed content"]))

    def test_sensitive_paths_and_authored_code_have_distinct_policy(self):
        for path in ("runtime/secrets/a.json", "runtime/handoff/accepted/a.json", ".env.local", "config/a.local.json", "experiments/lab/private-config/configuration.php", "models/a.bin"):
            self.assertTrue(scanner.excluded_by_policy(path), path)
        for path in ("config/web_sources.json", "src/dragonhydra/config.py", "tests/test_evidence.py", "docs/PROGRESS.md"):
            self.assertFalse(scanner.excluded_by_policy(path), path)

    def test_utf16_and_cookie_header_are_scanned_without_value_disclosure(self):
        value = "session-" + "synthetic-header-value"
        text = "Cookie: session=" + value
        decoded = scanner.decode_text(text.encode("utf-16"))
        findings = scanner.scan_text(decoded)
        self.assertEqual(findings, [{"rule": "cookie_header", "line": 1}])
        self.assertNotIn(value, json.dumps(findings))
