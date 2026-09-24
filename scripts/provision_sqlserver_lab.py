"""One-time administrative bootstrap; never resets existing databases or identities."""

from datetime import datetime, timezone
import json
from pathlib import Path
import secrets

from dragonhydra.config import PROJECT_ROOT
from dragonhydra.storage.sqlserver import load_odbc, local_connection_options
from dragonhydra.storage.sqlserver_config import load_sqlserver_settings


def literal(value: str) -> str:
    return "N'" + value.replace("'", "''") + "'"


def main() -> None:
    settings = load_sqlserver_settings()
    driver = load_odbc(settings)
    secret_path = settings.secret_file
    data_directory = PROJECT_ROOT / "runtime/sqlserver-lab"
    if secret_path.exists() or not data_directory.is_dir() or any(data_directory.iterdir()):
        raise RuntimeError("Expected absent credentials and a new, ACL-prepared empty lab data directory")
    # Admin setup uses the current authorized Windows identity, not an app password.
    admin_options = local_connection_options(settings).replace("DATABASE={DRAGONHYDRA_LAB};", "DATABASE={master};")
    connection = driver.connect(admin_options + "Trusted_Connection=yes;", timeout=5, autocommit=True)
    try:
        cursor = connection.cursor()
        cursor.execute("SELECT DB_ID(N'DRAGONHYDRA_LAB'),SUSER_ID(N'dragonhydra_probe_sqlserver'),IS_SRVROLEMEMBER('sysadmin')")
        database_id, login_id, is_admin = cursor.fetchone()
        if database_id is not None or login_id is not None or is_admin != 1:
            raise RuntimeError("Database/login collision or administrative prerequisite not satisfied")
        password = "Aa9!" + secrets.token_urlsafe(36)
        with secret_path.open("x", encoding="utf-8") as stream:
            json.dump({"notice": ["LOCAL TEST SECRET", "DO NOT COMMIT", "DO NOT COPY TO WEB ROOT"],
                       "created_utc": datetime.now(timezone.utc).isoformat(),
                       "username": "dragonhydra_probe_sqlserver", "password": password}, stream, indent=2)
            stream.write("\n")
        data_path = str(data_directory / "DRAGONHYDRA_LAB.mdf")
        log_path = str(data_directory / "DRAGONHYDRA_LAB_log.ldf")
        cursor.execute("CREATE DATABASE [DRAGONHYDRA_LAB] ON PRIMARY "
                       f"(NAME=N'DRAGONHYDRA_LAB_data',FILENAME={literal(data_path)},SIZE=16MB,MAXSIZE=128MB,FILEGROWTH=8MB) "
                       f"LOG ON (NAME=N'DRAGONHYDRA_LAB_log',FILENAME={literal(log_path)},SIZE=8MB,MAXSIZE=128MB,FILEGROWTH=8MB)")
        cursor.execute("USE [DRAGONHYDRA_LAB]")
        cursor.execute("CREATE SCHEMA probe AUTHORIZATION dbo")
        cursor.execute("CREATE TABLE probe.CapabilitySample(sample_id int NOT NULL PRIMARY KEY,label nvarchar(80) NOT NULL,quantity int NOT NULL CHECK(quantity>=0))")
        cursor.execute("INSERT INTO probe.CapabilitySample(sample_id,label,quantity) VALUES(1,N'synthetic-a',10),(2,N'synthetic-b',20)")
        # Password never reaches OS arguments or normal output; DDL stays in memory.
        cursor.execute("CREATE LOGIN [dragonhydra_probe_sqlserver] WITH PASSWORD=" + literal(password)
                       + ",CHECK_POLICY=ON,CHECK_EXPIRATION=OFF,DEFAULT_DATABASE=[DRAGONHYDRA_LAB]")
        cursor.execute("CREATE USER [dragonhydra_probe_sqlserver] FOR LOGIN [dragonhydra_probe_sqlserver] WITH DEFAULT_SCHEMA=probe")
        cursor.execute("GRANT CONNECT TO [dragonhydra_probe_sqlserver]")
        cursor.execute("GRANT SELECT ON OBJECT::probe.CapabilitySample TO [dragonhydra_probe_sqlserver]")
        print(json.dumps({"created_utc": datetime.now(timezone.utc).isoformat(),
                          "database": settings.database, "account": "dragonhydra_probe_sqlserver",
                          "explicit_grants": ["CONNECT database", "SELECT probe.CapabilitySample"],
                          "fixed_server_or_database_roles_added": [], "synthetic_rows": 2,
                          "data_directory": str(data_directory), "existing_objects_overwritten": False}, indent=2))
    finally:
        connection.close()


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        # Avoid any error context that might contain password-bearing SQL text.
        print(json.dumps({"status": "failed", "error_type": type(error).__name__,
                          "action": "Inspect partial state; do not rerun over existing objects or drop anything."}))
        raise SystemExit(1) from None
