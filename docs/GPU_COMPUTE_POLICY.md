# GPU compute policy

Retain the existing Python 3.14.7 / PyTorch 2.14.0+cu132 / CUDA runtime 13.2 / cuDNN 9.24 / NVIDIA RTX 3050 baseline. Newer version numbers alone are not a reason to change it. Local operation evidence is authoritative for this machine; it does not establish every model/kernel or future package combination.

The relevant runtime is the one reported by `torch.version.cuda`; a separately installed CUDA toolkit and the driver capability shown by `nvidia-smi` are different facts. cuDNN's reported library version likewise does not demonstrate every convolution path. Preserve DLL search behavior and package identity unless a measured issue requires a scoped change.

## What genesis measures

[diagnostics.py](../src/dragonhydra/diagnostics.py) records interpreter/executable, NumPy/PyTorch versions, CUDA availability/runtime, cuDNN version/availability, GPU identity/memory/capability, selected device and operation result. It uses the bounded parameters in [genesis.toml](../config/genesis.toml): seeded float32 matrices, currently 96 by 96, a NumPy float64 reference and absolute tolerance 0.0001 with relative tolerance zero.

The operation synchronizes CUDA before completing timing and compares finite numerical output against the CPU reference. Report maximum absolute error and the actual device. A GPU baseline pass requires both CUDA availability and a passing numerical comparison; a successful CPU fallback must not be reported as a successful GPU baseline. The CLI also requires the canonical interpreter match for its diagnostic success exit.

The [executed genesis checkpoint — curated summary](evidence/foundation-summary.json) (LOCAL EVIDENCE PATH: `runtime/checkpoints/genesis-20260924T155516Z-ddf9f093/diagnostics.json`) passed on `cuda:0`, NVIDIA GeForce RTX 3050, compute capability 8.6. Maximum absolute matrix error was `5.763398931435404e-06`, below `0.0001`; CPU fallback was false. The runtime reported CUDA 13.2 and cuDNN integer version 92400 with cuDNN available. This records a successful bounded operation, not a package-wide compatibility claim.

The timer covers one operation including transfers and synchronization. It is a smoke test, not a speed benchmark. Matrix multiplication does not prove cuDNN convolution correctness, neural-model training stability, maximum usable VRAM or deterministic behavior across all kernels. Actual checkpoints and test outcomes are tracked in [PROGRESS.md](PROGRESS.md); this policy does not invent a result.

## Hardware-aware execution

P4/P5/P6 adapters should choose a device based on supported operations, tensor sizes, memory and measured benefit. Small operations may belong on CPU. Configure limits rather than copying old DRAGON's fixed budget assumptions; actual free memory varies with other processes. Report requested device, selected device, precision, fallback reason and runtime scope.

CPU fallback is appropriate where the algorithm permits it and latency/resource limits remain acceptable. It must retain the same evidence cutoff and result semantics, with numerical tolerances verified. Failure to allocate GPU memory is not permission to silently change the model, sample size or precision. If a fallback cannot satisfy the contract, return an explicit failed/deferred result.

The donor's diagnostic could set `cuda_available=True` based on NVIDIA device detection even when PyTorch was unavailable. DRAGONHYDRA rejects that inference: GPU present, driver reachable, framework runtime available and successful computation are separately reported facts. See [OLD_DRAGON_RECONCILIATION.md](OLD_DRAGON_RECONCILIATION.md).

## Compatibility gates for a future update

Before updating PyTorch, CUDA or cuDNN, identify a concrete correctness, functionality or measured-performance reason. Verify official compatibility, Python 3.14 Windows artifacts, RTX 3050 support and dependency constraints for the selected versions. Record the working baseline and an isolated rollback route first.

Then run imports and device discovery, CPU/GPU matrix agreement, an appropriate bounded cuDNN convolution comparison before neural work, and the intended workload's known-answer/regression checks. Benchmark only where relevant, with warm-up, repeated samples, declared precision, synchronization and separate transfer costs. Preserve successful old measurements; a failed candidate remains visible in progress/decision records. Promote only the candidate that meets correctness and resource goals.

No GPU-stack update, driver installation, toolkit replacement or neural-model installation is part of genesis. No external engine is accelerated merely because CUDA is present.

## Native Windows analytical compromise

OWNER_INTENT: GPU acceleration and useful columnar feature pipelines on the existing Windows workstation. TECHNICAL_CONSTRAINT: the [official Polars GPU backend](https://docs.pola.rs/user-guide/gpu-support/) requires Linux or WSL2; Python 3.14 CPU package compatibility does not establish that GPU path. OPTIONS: later CPU Polars on native Windows, an explicitly scoped WSL2 environment, or another measured GPU engine. CHOSEN_COMPROMISE: keep native Windows and the proven PyTorch GPU path; plan Polars CPU pipelines without installing them in this block. REASON: this preserves the working runtime and avoids an unrequested operating-system/runtime expansion.

External engines and Qwen remain future adapters with separate resource, compatibility and license reviews when required. PyTorch remains a computational engine within the Pyramid, never a substitute for evidence validation, analytical storage, classical mathematics or uncertainty reasoning.
