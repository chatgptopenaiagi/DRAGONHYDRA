import sys
import unittest
from unittest.mock import patch

from dragonhydra.diagnostics import compute_diagnostic


class ComputeBaselineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = compute_diagnostic()

    def test_python_is_canonical_314(self):
        self.assertGreaterEqual(sys.version_info[:2], (3, 14))
        self.assertLess(sys.version_info[:2], (3, 15))
        self.assertTrue(self.result["canonical_interpreter_matches"])

    def test_numpy_and_pytorch_import(self):
        self.assertTrue(self.result["numpy_version"])
        self.assertTrue(self.result["torch_version"])

    def test_cuda_available(self):
        self.assertTrue(self.result["cuda_available"])
        self.assertEqual(self.result["device"], "cuda:0")

    def test_cudnn_available(self):
        self.assertTrue(self.result["cudnn_available"])
        self.assertGreater(self.result["cudnn_version_encoded"], 0)

    def test_gpu_matrix_matches_independent_numpy_reference(self):
        self.assertTrue(self.result["matrix_passed"], self.result["matrix_max_absolute_error"])
        self.assertFalse(self.result["cpu_fallback_used"])

    def test_cpu_fallback_is_reported_without_claiming_gpu_success(self):
        with patch("torch.cuda.is_available", return_value=False):
            fallback = compute_diagnostic()
        self.assertEqual(fallback["device"], "cpu")
        self.assertTrue(fallback["matrix_passed"])
        self.assertTrue(fallback["cpu_fallback_used"])
        self.assertFalse(fallback["gpu_baseline_passed"])


if __name__ == "__main__":
    unittest.main()
