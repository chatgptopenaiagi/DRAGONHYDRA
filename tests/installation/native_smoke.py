"""Drive the compiled Tauri WebView2 client through the supported native driver."""
from __future__ import annotations
import argparse
import base64
import hashlib
import json
from pathlib import Path
import socket
import subprocess
import time
from urllib.request import Request, urlopen
from urllib.error import HTTPError

ROOT = Path(__file__).resolve().parents[2]
ELEMENT = "element-6066-11e4-a52e-4f735466cecf"

def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--state", type=Path, default=ROOT / "runtime/product")
    p.add_argument("--binary", type=Path, default=ROOT / "dist/DRAGONHYDRA-Client-x64.exe")
    p.add_argument("--output", type=Path, default=ROOT / "runtime/evidence/installation/native-smoke.json")
    args = p.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    port, native_port = free_port(), free_port()
    driver = ROOT / "runtime/tools/bin/tauri-driver.exe"
    edge = ROOT / "runtime/tools/edgedriver/msedgedriver.exe"
    checks = []
    evidence = {"binary": str(args.binary), "state": str(args.state), "driver": "tauri-driver 2.0.4 / EdgeDriver 156.0.4314.50", "scope": "Compiled native Windows x64 Tauri client, real server API", "checks": checks, "passed": False}
    proc = None
    session = None
    base = f"http://127.0.0.1:{port}"
    def call(method, path, value=None):
        data = None if value is None else json.dumps(value).encode()
        try:
            with urlopen(Request(base + path, data, {"Content-Type": "application/json"}, method=method), timeout=110 if path == "/session" else 35) as response:
                return json.load(response).get("value")
        except HTTPError as exc:
            detail = json.loads(exc.read()).get("value", {})
            raise RuntimeError(str(detail.get("message", detail))[:800]) from None
    def script(js):
        return call("POST", f"/session/{session}/execute/sync", {"script": js, "args": []})
    def wait(js, timeout=20):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if script(js):
                return
            time.sleep(.15)
        raise AssertionError("Native visible-state deadline expired: " + js[:120])
    def click(selector):
        element = call("POST", f"/session/{session}/element", {"using": "css selector", "value": selector})
        call("POST", f"/session/{session}/element/{element[ELEMENT]}/click", {})
    def click_text(text):
        element = call("POST", f"/session/{session}/element", {"using": "xpath", "value": f"//button[contains(normalize-space(.), '{text}')]"})
        call("POST", f"/session/{session}/element/{element[ELEMENT]}/click", {})
    try:
        evidence["sha256"] = hashlib.sha256(args.binary.read_bytes()).hexdigest()
        log = (args.output.parent / "tauri-driver.log").open("w", encoding="utf-8")
        proc = subprocess.Popen([str(driver), "--port", str(port), "--native-port", str(native_port), "--native-driver", str(edge)], stdout=log, stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW)
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            try:
                call("GET", "/status")
                break
            except Exception:
                time.sleep(.2)
        value = call("POST", "/session", {"capabilities": {"alwaysMatch": {"tauri:options": {"application": str(args.binary), "args": ["--state=" + str(args.state)]}}}})
        session = value["sessionId"]
        wait("return document.querySelector('#service-state')?.textContent.includes('ready')")
        checks.append({"name": "native-launch-and-pairing", "passed": True})
        click("a[data-route='connections']")
        wait("return document.querySelector('h1')?.textContent === 'Connections'")
        checks.append({"name": "connections-navigation", "passed": True})
        click("a[data-route='live']")
        wait("return document.querySelector('main')?.textContent.includes('No live matches available')")
        checks.append({"name": "honest-empty-live-state", "passed": True})
        click_text("Browse retained matches")
        wait("return document.querySelector('.match-card') !== null")
        click(".match-card")
        wait("return document.querySelector('.match-hero') !== null")
        match_id = script("return sessionStorage.getItem('dragonhydra.match')")
        checks.append({"name": "open-retained-real-match", "passed": True, "match_id": match_id})
        click_text("Open standings")
        wait("return document.querySelector('table') !== null")
        checks.append({"name": "standings-open", "passed": True})
        click_text("Return to selected match")
        wait("return document.querySelector('.match-hero') !== null")
        assert script("return sessionStorage.getItem('dragonhydra.match')") == match_id
        checks.append({"name": "retained-match-context", "passed": True})
        click("a[data-route='analysis']")
        wait("return document.querySelector('[data-action=explain]') !== null")
        click("[data-action='explain']")
        wait("return !!document.querySelector('#explanation-result')?.textContent.trim()", timeout=40)
        checks.append({"name": "evidence-explanation-job-visible", "passed": True})
        screenshot = call("GET", f"/session/{session}/screenshot")
        screenshot_path = args.output.with_suffix(".png")
        screenshot_path.write_bytes(base64.b64decode(screenshot))
        evidence.update(passed=True, screenshot=str(screenshot_path), title=script("return document.title"))
    except Exception as exc:
        evidence["error"] = f"{type(exc).__name__}: {str(exc)[:500]}"
        raise
    finally:
        if session:
            try:
                call("DELETE", f"/session/{session}")
            except Exception:
                pass
        if proc:
            proc.terminate()
            proc.wait(timeout=10)
        args.output.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
        print(json.dumps(evidence, indent=2))

if __name__ == "__main__":
    main()
