"""Future mathematical engines exchange validated, immutable value snapshots.

No engines are implemented here. Adapters must supply JSON-compatible values;
arrays and database objects require explicit conversion. Fingerprints are caller
provenance references, not hashes computed or verified by these contracts.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
import math
from types import MappingProxyType
from typing import Protocol, cast

type JSONValue = None | bool | int | float | str | list[JSONValue] | tuple[JSONValue, ...] | Mapping[str, JSONValue]
type FrozenJSONValue = None | bool | int | float | str | tuple[FrozenJSONValue, ...] | Mapping[str, FrozenJSONValue]


def _text(value: str, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")


def _freeze(value: JSONValue, ancestors: set[int] | None = None) -> FrozenJSONValue:
    """Defensively copy containers; reject cycles, objects and non-finite floats."""
    if value is None or type(value) in (bool, int, str):
        return value
    if type(value) is float:
        if not math.isfinite(value):
            raise ValueError("JSON numbers must be finite")
        return value
    if not isinstance(value, (Mapping, list, tuple)):
        raise ValueError("Payload must contain only JSON-compatible values")
    ancestors = set() if ancestors is None else ancestors
    identity = id(value)
    if identity in ancestors:
        raise ValueError("Cyclic payloads are not supported")
    ancestors.add(identity)
    try:
        if isinstance(value, Mapping):
            if any(type(key) is not str for key in value):
                raise ValueError("JSON object keys must be strings")
            return MappingProxyType({key: _freeze(item, ancestors) for key, item in value.items()})
        return tuple(_freeze(item, ancestors) for item in value)
    finally:
        ancestors.remove(identity)


def _mapping(value: Mapping[str, JSONValue], name: str) -> Mapping[str, FrozenJSONValue]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be a mapping")
    return cast(Mapping[str, FrozenJSONValue], _freeze(value))


def _strings(values: tuple[str, ...], name: str) -> tuple[str, ...]:
    if not isinstance(values, (tuple, list)):
        raise ValueError(f"{name} must be a sequence of strings")
    for value in values:
        _text(value, name)
    return tuple(values)


class MathCapability(StrEnum):
    SOLVE = "solve"
    FIT = "fit"
    PREDICT = "predict"
    SIMULATE = "simulate"
    OPTIMIZE = "optimize"
    DIFFERENTIATE = "differentiate"
    INTEGRATE = "integrate"
    CALIBRATE = "calibrate"
    EXPLAIN = "explain"


@dataclass(frozen=True, slots=True)
class MathEngineRequest:
    operation: MathCapability
    inputs: Mapping[str, JSONValue]
    input_fingerprint: str
    target_as_of_at: datetime
    seed: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.operation, MathCapability):
            raise ValueError("operation must be MathCapability")
        _text(self.input_fingerprint, "input_fingerprint")
        target = self.target_as_of_at
        if not isinstance(target, datetime) or target.tzinfo is None or target.utcoffset() is None:
            raise ValueError("target_as_of_at must be a timezone-aware datetime")
        if self.seed is not None and type(self.seed) is not int:
            raise ValueError("seed must be an integer or None")
        object.__setattr__(self, "inputs", _mapping(self.inputs, "inputs"))


@dataclass(frozen=True, slots=True)
class MathEngineResult:
    engine_id: str
    engine_version: str
    inputs: Mapping[str, JSONValue]
    result: JSONValue
    distribution: Mapping[str, JSONValue] | None
    confidence: float | None
    numerical_precision: str
    warnings: tuple[str, ...]
    assumptions: tuple[str, ...]
    runtime: float
    hardware: str
    reason_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        if type(self.runtime) not in (int, float) or self.runtime < 0 or (
            type(self.runtime) is float and not math.isfinite(self.runtime)
        ):
            raise ValueError("Runtime must be finite and nonnegative")
        if self.confidence is not None and (
            type(self.confidence) not in (int, float) or not 0 <= self.confidence <= 1
        ):
            raise ValueError("Confidence must be finite in [0,1], or unknown (None)")
        for name in ("engine_id", "engine_version", "numerical_precision", "hardware"):
            _text(getattr(self, name), name)
        for name in ("warnings", "assumptions", "reason_codes"):
            object.__setattr__(self, name, _strings(getattr(self, name), name))
        object.__setattr__(self, "inputs", _mapping(self.inputs, "inputs"))
        object.__setattr__(self, "result", _freeze(self.result))
        if self.distribution is not None:
            object.__setattr__(self, "distribution", _mapping(self.distribution, "distribution"))


class MathEngine(Protocol):
    engine_id: str
    engine_version: str
    capabilities: frozenset[MathCapability]

    def solve(self, request: MathEngineRequest) -> MathEngineResult: ...
    def fit(self, request: MathEngineRequest) -> MathEngineResult: ...
    def predict(self, request: MathEngineRequest) -> MathEngineResult: ...
    def simulate(self, request: MathEngineRequest) -> MathEngineResult: ...
    def optimize(self, request: MathEngineRequest) -> MathEngineResult: ...
    def differentiate(self, request: MathEngineRequest) -> MathEngineResult: ...
    def integrate(self, request: MathEngineRequest) -> MathEngineResult: ...
    def calibrate(self, request: MathEngineRequest) -> MathEngineResult: ...
    def explain(self, request: MathEngineRequest) -> MathEngineResult: ...
