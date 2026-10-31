"""Verify the packaged server using isolated product state and OS-only PATH."""
from __future__ import annotations
import argparse
import ctypes
from ctypes import wintypes
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import uuid4
from zipfile import ZipFile
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]

def python_modules(pid):
    class Entry(ctypes.Structure):
        _fields_ = [("dwSize", wintypes.DWORD), ("th32ModuleID", wintypes.DWORD),
                    ("th32ProcessID", wintypes.DWORD), ("GlblcntUsage", wintypes.DWORD),
                    ("ProccntUsage", wintypes.DWORD), ("modBaseAddr", ctypes.POINTER(ctypes.c_byte)),
                    ("modBaseSize", wintypes.DWORD), ("hModule", wintypes.HMODULE),
                    ("szModule", wintypes.WCHAR * 256), ("szExePath", wintypes.WCHAR * 260)]
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    kernel.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel.Module32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(Entry)]
    kernel.Module32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(Entry)]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.CreateToolhelp32Snapshot(0x08 | 0x10, pid)
    entry = Entry()
    entry.dwSize = ctypes.sizeof(entry)
    modules = []
    try:
        okay = kernel.Module32FirstW(handle, ctypes.byref(entry))
        while okay:
            if entry.szModule.lower().startswith("python"):
                modules.append(entry.szExePath)
            okay = kernel.Module32NextW(handle, ctypes.byref(entry))
    finally:
        kernel.CloseHandle(handle)
    return modules

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--binary", type=Path, default=ROOT / "dist/DRAGONHYDRA-Server-x64/DRAGONHYDRA-Server.exe")
    parser.add_argument("--output", type=Path, default=ROOT / "runtime/evidence/installation/frozen-server.json")
    args = parser.parse_args()
    binary = args.binary.resolve()
    state = ROOT / ("runtime/scratch/frozen-server-test-" + uuid4().hex)
    state.mkdir(parents=True)
    output = args.output.resolve()
    checks = []
    record = {"created_at": datetime.now(timezone.utc).isoformat(), "binary": str(binary),
              "sha256": hashlib.sha256(binary.read_bytes()).hexdigest(), "state": str(state),
              "scope": "Packaged server on current Windows x64 host; clean-machine installation not tested",
              "checks": checks, "passed": False}
    env = os.environ.copy()
    for key in ("PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV", "CONDA_PREFIX"):
        env.pop(key, None)
    windows_root = os.environ.get("SystemRoot", r"C:\Windows")
    env["PATH"] = os.path.join(windows_root, "System32") + os.pathsep + windows_root
    logs = (state / "server.log").open("w", encoding="utf-8")
    proc = subprocess.Popen([str(binary), "--host", "127.0.0.1", "--port", "0", "--state", str(state)], cwd=state, env=env,
                            stdout=logs, stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW)
    base, token = None, None
    def call(method, path, body=None, *, auth=True, key=None):
        headers = {"Content-Type": "application/json"}
        if auth:
            headers["Authorization"] = "Bearer " + token
        if key:
            headers["Idempotency-Key"] = key
        data = None if body is None else json.dumps(body).encode()
        try:
            with urlopen(Request(base + path, data, headers, method=method), timeout=10) as response:
                raw = response.read()
                return response.status, json.loads(raw) if "json" in response.headers.get("Content-Type", "") else raw
        except HTTPError as exc:
            return exc.code, json.loads(exc.read())
    def job(job_id):
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            status, row = call("GET", "/dragon/api/v1/jobs/" + job_id)
            assert status == 200
            if row["status"] == "succeeded":
                return row
            if row["status"] in ("failed", "cancelled"):
                raise AssertionError(row["error"])
            time.sleep(.15)
        raise AssertionError("Frozen worker job timed out")
    try:
        deadline = time.monotonic() + 25
        while time.monotonic() < deadline:
            assert proc.poll() is None, "Frozen process exited during startup"
            endpoint = state / "endpoint.json"
            if endpoint.exists():
                try:
                    info = json.loads(endpoint.read_text())
                    base = info["url"]
                    token = json.loads((state / "local-session.json").read_text())["token"]
                    if call("GET", "/dragon/api/v1/health/ready")[0] == 200:
                        break
                except (OSError, ValueError):
                    pass
            time.sleep(.15)
        assert base and call("GET", "/dragon/api/v1/health/ready")[0] == 200
        record["endpoint"] = base
        modules = python_modules(info["pid"])
        record["loaded_python_modules"] = modules
        assert modules and all(Path(m).is_relative_to(binary.parent) for m in modules)
        checks.append({"name": "private-runtime-startup-os-only-path", "passed": True, "python_environment_unset": True})
        assert call("GET", "/dragon/api/v1/health/ready", auth=False)[0] == 401
        assert call("POST", "/dragon/api/v1/session", {"token": "\u65e5" * 25}, auth=False)[0] == 401
        checks.append({"name": "authentication-and-unicode-token-regression", "passed": True})
        assert call("GET", "/dragon/api/v1/matches?limit=1")[1]["total"] == 0
        status, first = call("POST", "/dragon/api/v1/connections/openfootball/sync", {}, key="frozen-retained-import")
        assert status == 202
        imported = job(first["id"])
        assert imported["result"]["record_count"] == 760
        _, repeated = call("POST", "/dragon/api/v1/connections/openfootball/sync", {}, key="frozen-retained-import")
        assert repeated["id"] == first["id"]
        checks.append({"name": "retained-760-record-import-and-idempotency", "passed": True, "job_id": first["id"], "record_count": 760})
        _, matches = call("GET", "/dragon/api/v1/matches?limit=1")
        selected = matches["items"][0]
        match_id = selected["id"]
        assert call("GET", "/dragon/api/v1/matches/" + match_id)[1]["id"] == match_id
        assert call("GET", "/dragon/api/v1/teams/" + selected["home"]["id"])[0] == 200
        assert call("GET", "/dragon/api/v1/competitions/" + selected["competition_id"] + "/standings")[0] == 200
        checks.append({"name": "same-canonical-match-team-standings", "passed": True, "match_id": match_id})
        status, export = call("POST", "/dragon/api/v1/exports", {"match_id": match_id, "format": "xlsx"})
        assert status == 202
        workbook_job = job(export["id"])
        status, workbook = call("GET", workbook_job["result"]["download_url"])
        assert status == 200
        with ZipFile(io.BytesIO(workbook)) as book:
            workbook_xml = ET.fromstring(book.read("xl/workbook.xml"))
            sheets = [n.attrib["name"] for n in workbook_xml.findall("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}sheets/*")]
            assert sheets == ["Match", "Metadata"]
            assert match_id.encode() in book.read("xl/worksheets/sheet1.xml")
        (state / "verified-report.xlsx").write_bytes(workbook)
        checks.append({"name": "frozen-worker-real-xlsx-export", "passed": True, "bytes": len(workbook), "sheets": sheets, "sha256": hashlib.sha256(workbook).hexdigest()})
        assert call("POST", "/dragon/api/v1/system/shutdown", {})[0] == 200
        proc.wait(timeout=15)
        assert proc.returncode == 0
        checks.append({"name": "authenticated-graceful-shutdown", "passed": True, "exit_code": proc.returncode})
        record["passed"] = True
    except Exception as exc:
        record["error"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        if proc.poll() is None:
            if base and token:
                try:
                    call("POST", "/dragon/api/v1/system/shutdown", {})
                    proc.wait(timeout=10)
                except Exception:
                    proc.terminate()
                    proc.wait(timeout=5)
            else:
                proc.terminate()
                proc.wait(timeout=5)
        logs.close()
        output.write_text(json.dumps(record, indent=2), encoding="utf-8")
        print(json.dumps(record, indent=2))

if __name__ == "__main__":
    main()
