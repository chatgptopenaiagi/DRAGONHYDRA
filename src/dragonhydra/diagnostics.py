"""Small real operations distinguish hardware discovery from executable compute."""

from datetime import datetime, timezone
import importlib.metadata
import os
from pathlib import Path
import sys
from time import perf_counter

from .config import Settings, load_settings


def compute_diagnostic(settings: Settings | None = None) -> dict:
    settings = settings or load_settings()
    if sys.version_info[:2] != (3, 14):
        raise RuntimeError("DRAGONHYDRA genesis requires Python >=3.14,<3.15")
    import numpy as np
    import torch

    cuda_available = torch.cuda.is_available()
    device = "cuda:0" if cuda_available else "cpu"
    generator = np.random.default_rng(settings.seed)
    left = generator.standard_normal((settings.matrix_size, settings.matrix_size)).astype(np.float32)
    right = generator.standard_normal((settings.matrix_size, settings.matrix_size)).astype(np.float32)
    reference = left.astype(np.float64) @ right.astype(np.float64)
    started = perf_counter()
    with torch.no_grad():
        output = torch.from_numpy(left).to(device) @ torch.from_numpy(right).to(device)
        if cuda_available:
            torch.cuda.synchronize()
        result = output.cpu().numpy()
    elapsed = perf_counter() - started
    error = float(np.max(np.abs(result.astype(np.float64) - reference)))
    numerical_pass = bool(np.allclose(result, reference, atol=settings.absolute_tolerance, rtol=0))
    return {
        "checked_utc": datetime.now(timezone.utc).isoformat(),
        "python_version": sys.version.split()[0], "python_executable": sys.executable,
        "canonical_interpreter": str(settings.python_executable),
        "canonical_interpreter_matches": settings.python_executable.resolve() == Path(sys.executable).resolve(),
        "conda_environment": os.environ.get("CONDA_DEFAULT_ENV"),
        "numpy_version": np.__version__, "torch_version": torch.__version__,
        "cuda_runtime": torch.version.cuda, "cudnn_version_encoded": torch.backends.cudnn.version(),
        "cudnn_available": torch.backends.cudnn.is_available(),
        "cuda_available": cuda_available,
        "device": device, "gpu": torch.cuda.get_device_name(0) if cuda_available else None,
        "gpu_memory_bytes": torch.cuda.get_device_properties(0).total_memory if cuda_available else None,
        "gpu_capability": list(torch.cuda.get_device_capability(0)) if cuda_available else None,
        "matrix_shape": [settings.matrix_size, settings.matrix_size],
        "reference": "NumPy float64; Torch output float32",
        "matrix_max_absolute_error": error, "absolute_tolerance": settings.absolute_tolerance,
        "matrix_passed": numerical_pass, "runtime_seconds": elapsed,
        "cpu_fallback_used": not cuda_available,
        "gpu_baseline_passed": cuda_available and numerical_pass,
        "timing_scope": "one smoke operation including transfers; not a performance benchmark",
    }


def technology_inventory() -> dict:
    names = ["numpy", "torch", "sympy", "scipy", "polars", "duckdb", "pyarrow",
             "statsmodels", "scikit-learn", "PyMySQL", "PySide6", "pytest"]
    packages = {}
    for name in names:
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            packages[name] = None
    settings = load_settings()
    local_packages = {
        distribution.metadata["Name"]: distribution.version
        for distribution in importlib.metadata.distributions(path=[str(settings.driver_directory)])
    }
    return {"packages_visible_to_current_process": packages,
            "project_local_packages": local_packages,
            "note": "Metadata inventory only; project-local driver is deliberately separate from Conda. Absence does not imply Python incompatibility."}
