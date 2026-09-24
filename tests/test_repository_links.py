"""GitHub link validity is determined by staged membership, not local existence."""

import importlib.util
from pathlib import Path
import unittest
from unittest.mock import call, patch


spec = importlib.util.spec_from_file_location("repository_links", Path(__file__).resolve().parents[1] / "scripts/check_repository_links.py")
links = importlib.util.module_from_spec(spec)
spec.loader.exec_module(links)


class RepositoryLinkTests(unittest.TestCase):
    def test_reads_markdown_from_index_object_not_working_tree(self):
        oid = "a" * 40
        listing = f"100644 {oid} 0\tREADME.md\0".encode()
        staged_body = b"[index](README.md)"
        with patch.object(links.subprocess, "check_output", side_effect=[listing, staged_body]) as git:
            self.assertEqual(links.staged_blobs(), {"README.md": staged_body})
        self.assertEqual(git.call_args_list, [
            call(["git", "ls-files", "--stage", "-z"], cwd=links.ROOT),
            call(["git", "cat-file", "blob", oid], cwd=links.ROOT),
        ])

    def test_working_directory_file_does_not_satisfy_staged_membership(self):
        result = links.check_links({"README.md": b"[real local file](pyproject.toml)"})
        self.assertFalse(result["passed"])
        self.assertEqual(result["broken_links"][0]["reason"], "target_absent_from_staged_files")

    def test_staged_target_and_directory_resolve(self):
        result = links.check_links({"README.md": b"[index](docs/INDEX.md) [docs](docs/)", "docs/INDEX.md": b""})
        self.assertTrue(result["passed"])
        self.assertEqual(result["links_checked"], 2)

    def test_checkpoint_link_fails_even_if_force_staged(self):
        result = links.check_links({"README.md": b"[raw](runtime/checkpoints/proof.json)", "runtime/checkpoints/proof.json": b"{}"})
        self.assertFalse(result["passed"])
        self.assertIn("local_forensic", result["broken_links"][0]["reason"])

    def test_reference_links_and_encoded_relative_paths(self):
        result = links.check_links({"docs/INDEX.md": b"[report][ref]\n\n[ref]: ../reports/safe%20summary.md\n", "reports/safe summary.md": b""})
        self.assertTrue(result["passed"])
        self.assertGreaterEqual(result["links_checked"], 1)

    def test_code_examples_and_external_links_are_not_file_targets(self):
        text = b"```md\n[example](missing.md)\n```\n`[also](missing.md)`\n[external](https://example.org/page)"
        self.assertTrue(links.check_links({"README.md": text})["passed"])

    def test_parent_escape_and_missing_target_fail(self):
        result = links.check_links({"README.md": b"[escape](../secret.md) [missing](absent.md)"})
        self.assertEqual({issue["reason"] for issue in result["broken_links"]}, {"outside_repository", "target_absent_from_staged_files"})

    def test_local_machine_links_are_not_external_links(self):
        result = links.check_links({"README.md": b"[drive](C:/xampp/local.json) [file](file:///C:/xampp/local.json)"})
        self.assertFalse(result["passed"])
        self.assertEqual(len(result["broken_links"]), 2)


if __name__ == "__main__":
    unittest.main()
