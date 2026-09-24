"""Independent, loopback-only SQL Server lab settings and redacted credentials."""

from dataclasses import dataclass, field
import ipaddress
import json
from pathlib import Path
import re
import tomllib

from ..config import PROJECT_ROOT, project_path


@dataclass(frozen=True, slots=True)
class SQLServerSettings:
    host: str
    port: int
    database: str
    service_name: str
    instance_id: str
    odbc_driver: str
    python_driver_version: str
    driver_directory: Path
    secret_file: Path
    connect_timeout_seconds: int
    query_timeout_seconds: int
    encrypt: bool
    trust_server_certificate: bool

    def __post_init__(self) -> None:
        if not ipaddress.ip_address(self.host).is_loopback:
            raise ValueError("SQL Server lab and certificate exception are loopback-only")
        if type(self.port) is not int or not 1 <= self.port <= 65535:
            raise ValueError("Invalid SQL Server TCP port")
        if self.database != "DRAGONHYDRA_LAB":
            raise ValueError("SQL Server adapter is restricted to its dedicated laboratory")
        if self.odbc_driver != "ODBC Driver 18 for SQL Server":
            raise ValueError("This measured adapter requires modern ODBC Driver 18")
        if not self.driver_directory.resolve().is_relative_to((PROJECT_ROOT / "runtime/vendor").resolve()):
            raise ValueError("Python driver must be project-local")
        if not self.secret_file.resolve().is_relative_to((PROJECT_ROOT / "runtime/secrets").resolve()):
            raise ValueError("SQL credential file must be in private runtime/secrets")
        if self.encrypt is not True or type(self.trust_server_certificate) is not bool:
            raise ValueError("Encryption is required; certificate policy must be explicit")
        if (type(self.connect_timeout_seconds) is not int or type(self.query_timeout_seconds) is not int
                or not 1 <= self.connect_timeout_seconds <= 30 or not 1 <= self.query_timeout_seconds <= 30):
            raise ValueError("Timeouts must remain bounded")
        if not re.fullmatch(r"[A-Za-z0-9_$.-]+", self.service_name):
            raise ValueError("Invalid service identifier")


@dataclass(frozen=True, slots=True)
class SQLServerCredential:
    username: str
    password: str = field(repr=False)


def load_sqlserver_settings(path: Path | None = None) -> SQLServerSettings:
    with (path or PROJECT_ROOT / "config/databases.toml").open("rb") as stream:
        raw = tomllib.load(stream)
    config = raw["sqlserver"].copy()
    if "password" in config or "username" in config:
        raise ValueError("Credentials belong in the protected secret file")
    config["driver_directory"] = project_path(config["driver_directory"])
    config["secret_file"] = project_path(config["secret_file"])
    return SQLServerSettings(**config)


def load_sqlserver_credential(settings: SQLServerSettings) -> SQLServerCredential:
    raw = json.loads(settings.secret_file.read_text(encoding="utf-8-sig"))
    if raw.get("username") != "dragonhydra_probe_sqlserver":
        raise ValueError("Expected the dedicated bounded SQL Server identity")
    if not isinstance(raw.get("password"), str) or len(raw["password"]) < 32:
        raise ValueError("Missing or weak SQL Server probe secret")
    return SQLServerCredential(raw["username"], raw["password"])
