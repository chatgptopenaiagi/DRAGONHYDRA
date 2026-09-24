"""Validated non-secret configuration; secrets live outside web roots and logs."""

from dataclasses import dataclass, field
import ipaddress
import json
import math
from pathlib import Path
import re
import tomllib

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def project_path(relative: str, root: Path = PROJECT_ROOT) -> Path:
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError("Configured path escapes the project")
    return path


@dataclass(frozen=True, slots=True)
class Settings:
    python_executable: Path
    conda_environment: str
    host: str
    port: int
    database: str
    table_prefix: str
    secret_file: Path
    driver_directory: Path
    driver_version: str
    connect_timeout_seconds: int
    matrix_size: int
    absolute_tolerance: float
    seed: int

    def __post_init__(self) -> None:
        # Validate here as well as parsing: callers can construct/replace this type.
        if not ipaddress.ip_address(self.host).is_loopback:
            raise ValueError("Genesis probe must use an explicit loopback address")
        if not isinstance(self.port, int) or not 1 <= self.port <= 65535:
            raise ValueError("Invalid database port")
        if self.database != "joomla_codex_lab":
            raise ValueError("Genesis probe is limited to its controlled Joomla source")
        if not re.fullmatch(r"[a-z][a-z0-9]*_", self.table_prefix):
            raise ValueError("Unsafe table prefix")
        if not self.secret_file.resolve().is_relative_to((PROJECT_ROOT / "runtime/secrets").resolve()):
            raise ValueError("Credential file must be in private runtime/secrets")
        if not self.driver_directory.resolve().is_relative_to((PROJECT_ROOT / "runtime/vendor").resolve()):
            raise ValueError("Driver must remain in project-local runtime/vendor")
        if not 1 <= self.connect_timeout_seconds <= 30:
            raise ValueError("Connection timeout must remain bounded")
        if not isinstance(self.matrix_size, int) or not 1 <= self.matrix_size <= 512:
            raise ValueError("Diagnostic matrix size must remain bounded")
        if not math.isfinite(self.absolute_tolerance) or not 0 < self.absolute_tolerance < 0.01:
            raise ValueError("Invalid numerical tolerance")


@dataclass(frozen=True, slots=True)
class ProbeCredential:
    username: str
    password: str = field(repr=False)


def load_settings(path: Path | None = None) -> Settings:
    with (path or PROJECT_ROOT / "config/genesis.toml").open("rb") as stream:
        raw = tomllib.load(stream)
    project, probe, diagnostic = raw["project"], raw["probe"], raw["diagnostics"]
    if not ipaddress.ip_address(probe["host"]).is_loopback:
        raise ValueError("Genesis probe must use an explicit loopback address")
    if not 1 <= probe["port"] <= 65535:
        raise ValueError("Invalid database port")
    if probe["database"] != "joomla_codex_lab":
        raise ValueError("Genesis probe is limited to its controlled Joomla source")
    if not re.fullmatch(r"[a-z][a-z0-9]*_", probe["table_prefix"]):
        raise ValueError("Unsafe table prefix")
    if "password" in probe or "password" in project:
        raise ValueError("Do not store credentials in configuration")
    secret = project_path(probe["secret_file"])
    if not secret.is_relative_to(PROJECT_ROOT / "runtime/secrets"):
        raise ValueError("Credential file must be in private runtime/secrets")
    if not 1 <= diagnostic["matrix_size"] <= 512:
        raise ValueError("Diagnostic matrix size must remain bounded")
    if not 0 < diagnostic["absolute_tolerance"] < 0.01:
        raise ValueError("Invalid numerical tolerance")
    if not 1 <= probe["connect_timeout_seconds"] <= 30:
        raise ValueError("Connection timeout must remain bounded")
    return Settings(
        python_executable=Path(project["python_executable"]),
        conda_environment=project["conda_environment"],
        host=probe["host"], port=probe["port"], database=probe["database"],
        table_prefix=probe["table_prefix"], secret_file=secret,
        driver_directory=project_path(probe["driver_directory"]),
        driver_version=probe["driver_version"],
        connect_timeout_seconds=probe["connect_timeout_seconds"],
        matrix_size=diagnostic["matrix_size"],
        absolute_tolerance=diagnostic["absolute_tolerance"], seed=diagnostic["seed"],
    )


def load_probe_credential(settings: Settings) -> ProbeCredential:
    raw = json.loads(settings.secret_file.read_text(encoding="utf-8-sig"))
    if raw.get("username") != "dragonhydra_probe":
        raise ValueError("Expected the dedicated read-only probe identity")
    password = raw.get("password")
    if not isinstance(password, str) or len(password) < 32:
        raise ValueError("Missing or weak probe secret")
    return ProbeCredential(raw["username"], password)
