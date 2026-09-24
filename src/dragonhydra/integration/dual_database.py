"""Bounded two-engine diagnostics, not a generic executor or replication service."""

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
import urllib.request

from ..config import PROJECT_ROOT, load_settings
from ..storage.mariadb import MariaDBAdapter
from ..storage.sqlserver import SQLServerAdapter
from ..storage.sqlserver_config import load_sqlserver_settings


def simultaneous_windows_snapshot() -> dict:
    # Fixed read-only script: no input is interpolated into a shell command.
    script = r"""
$ErrorActionPreference='Stop'
$services=@(Get-CimInstance Win32_Service | Where-Object {$_.Name -in 'Apache2.4','mysql','MSSQLSERVER','SQLBrowser'} | Select-Object Name,State,StartMode,ProcessId)
$ports=3306,1433,1434,14330,80,443
$tcp=@(Get-NetTCPConnection -State Listen | Where-Object {$_.LocalPort -in $ports})
$udp=@(Get-NetUDPEndpoint | Where-Object {$_.LocalPort -eq 1434})
$listeners=@(foreach($item in $tcp){[ordered]@{port=$item.LocalPort;protocol='TCP';listen_address=$item.LocalAddress;pid=$item.OwningProcess;process=(Get-Process -Id $item.OwningProcess).ProcessName;service=(@($services | Where-Object {$_.ProcessId -eq $item.OwningProcess}).Name -join ',')}})
$listeners+=@(foreach($item in $udp){[ordered]@{port=$item.LocalPort;protocol='UDP';listen_address=$item.LocalAddress;pid=$item.OwningProcess;process=(Get-Process -Id $item.OwningProcess).ProcessName;service=(@($services | Where-Object {$_.ProcessId -eq $item.OwningProcess}).Name -join ',')}})
[ordered]@{checked_utc=(Get-Date).ToUniversalTime().ToString('o');services=$services;listeners=$listeners;odbc18_product_version=(Get-Item -LiteralPath 'C:\Windows\System32\msodbcsql18.dll').VersionInfo.ProductVersion} | ConvertTo-Json -Depth 5 -Compress
"""
    result = subprocess.run(["pwsh.exe", "-NoProfile", "-NonInteractive", "-Command", script],
                            capture_output=True, text=True, timeout=30, check=False)
    if result.returncode:
        raise RuntimeError("Read-only Windows listener/service snapshot failed")
    return json.loads(result.stdout)


def joomla_health() -> dict:
    url = "http://localhost/joomla-codex-lab/"
    # Ignore proxy environment variables for this strictly local health request.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(url, timeout=10) as response:
        body = response.read(2_000_000).decode("utf-8", errors="replace")
        return {"url": url, "http_status": response.status,
                "joomla_marker": "Joomla!" in body or "cassiopeia" in body,
                "site_name_present": "Codex XAMPP Laboratory" in body,
                "php_source_exposed": "<?php" in body}


def capability_payload(report) -> dict:
    return {
        **asdict(report.identity), **asdict(report.health),
        "read": report.read, "write": report.write, "transaction": report.transaction,
        "write_rejected": report.write_rejected,
        "operation": report.result.operation, "aggregates": dict(report.result.counts),
        "diagnostic": asdict(report.diagnostic),
    }


def run_dual_database() -> dict:
    if sys.version_info[:2] != (3, 14):
        raise RuntimeError("Dual database tests require canonical Python >=3.14,<3.15")
    maria_settings = load_settings()
    sql_settings = load_sqlserver_settings()
    if maria_settings.port == sql_settings.port:
        raise ValueError("Database engines require distinct TCP ports")
    maria_report = MariaDBAdapter(maria_settings).capability_report()
    sql_report, sql_details = SQLServerAdapter(sql_settings).inspect_capabilities()
    windows = simultaneous_windows_snapshot()
    joomla = joomla_health()
    services = {item["Name"]: item for item in windows["services"]}
    required = ["Apache2.4", "mysql", sql_settings.service_name]
    services_running = all(services.get(name, {}).get("State") == "Running" for name in required)
    listeners = windows["listeners"]
    databases_listening = all(any(item["protocol"] == "TCP" and item["port"] == port
                                 and item["service"] == service for item in listeners)
                             for service, port in (("mysql", maria_settings.port),
                                                   (sql_settings.service_name, sql_settings.port)))
    passed = (services_running and databases_listening and maria_report.health.status == "healthy"
              and sql_report.health.status == "healthy" and joomla["http_status"] == 200
              and joomla["joomla_marker"] and joomla["site_name_present"] and not joomla["php_source_exposed"])
    return {
        "checked_utc": datetime.now(timezone.utc).isoformat(),
        "python_version": sys.version.split()[0], "python_executable": sys.executable,
        "mariadb": capability_payload(maria_report), "sqlserver": capability_payload(sql_report),
        "sqlserver_permission_details": sql_details, "windows": windows, "joomla": joomla,
        "simultaneous_database_listeners": databases_listening,
        "required_services_running": services_running, "passed": passed,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.is_relative_to(PROJECT_ROOT / "runtime/checkpoints") or output.exists():
        parser.error("Output must be a new file under runtime/checkpoints")
    report = run_dual_database()
    payload = json.dumps(report, default=str, indent=2, allow_nan=False)
    with output.open("x", encoding="utf-8") as stream:
        stream.write(payload + "\n")
    print(payload)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
