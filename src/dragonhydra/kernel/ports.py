"""Narrow injected storage/provider/model/peer ports. No service locator or fallback."""
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Protocol


class ProviderReadPort(Protocol):
    def rows(self, *, sport: str): ...
    def evidence(self, evidence_id): ...
    def quote_source(self, observation, quote, index): ...


class DataReadPort(Protocol):
    def rows(self): ...
    def find(self, match_id): ...
    def present(self, row): ...
    def evidence(self, evidence_id): ...


class ModelPort(Protocol):
    def forecast(self, rows, target, cutoff, raw_resolver, **options): ...


class MemoryBackend(Protocol):
    def as_of(self, db_path, cutoff): ...
    def record_model_run(self, db_path, draft): ...
    def record_prediction(self, db_path, draft): ...
    def record_outcome(self, db_path, evidence_id): ...
    def record_evaluation(self, db_path, draft): ...


@dataclass(frozen=True)
class StoragePort:
    state: Path
    db_path: Path
    source_root: Path
    exports: Path
    connect: Callable


@dataclass(frozen=True)
class ApplicationContext:
    storage: StoragePort
    providers: ProviderReadPort
    clock: Callable[[], str]


@dataclass(frozen=True)
class MemoryPort:
    view: Callable
    record_model: Callable
    record_prediction: Callable
    attach_outcome: Callable


@dataclass(frozen=True)
class AIContext:
    state: Path
    db_path: Path
    find: Callable
    present: Callable
    evidence: Callable
