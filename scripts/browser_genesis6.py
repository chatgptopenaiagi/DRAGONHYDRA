"""Actual loopback Edge acceptance for the fictional research workspace."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import time
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright, expect

TOKEN = "virtual-session-only-not-a-real-account-1234"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--url", default="http://127.0.0.1:19380")
    parser.add_argument("--resume", type=Path)
    args = parser.parse_args(argv)
    address = urlparse(args.url)
    if address.scheme != "http" or address.hostname != "127.0.0.1" or address.path not in ("", "/"):
        raise ValueError("EXACT_LOOPBACK_URL_REQUIRED")
    output = args.output.absolute()
    if output.exists():
        raise ValueError("NEW_BROWSER_EVIDENCE_REQUIRED")
    output.mkdir(parents=True)
    report = {"schema_version": "dragonhydra.virtual-browser/1", "synthetic": True,
              "status": "RUNNING", "checks": [], "page_errors": [], "external_requests_blocked": []}
    def check(name, condition):
        report["checks"].append({"name": name, "status": "PASS" if condition else "FAIL"})
        if not condition:
            raise AssertionError(name)
    def sha(value):
        return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(executable_path=r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe", headless=True,
                args=["--disable-background-networking", "--disable-component-update", "--no-first-run"])
            report["browser"] = browser.version
            context = browser.new_context(viewport={"width": 1440, "height": 1080}, locale="en-GB")
            def route(request):
                url = urlparse(request.request.url)
                if url.hostname != "127.0.0.1" or url.port != address.port:
                    report["external_requests_blocked"].append(request.request.url)
                    request.abort()
                else:
                    request.continue_()
            context.route("**/*", route)
            page = context.new_page()
            page.on("pageerror", lambda error: report["page_errors"].append(error.stack))
            page.set_default_timeout(10000)
            page.goto(args.url+"/#research")
            expect(page.locator("#login-dialog")).to_be_visible()
            page.locator("#pairing-token").fill(TOKEN)
            page.get_by_role("button", name="Connect", exact=True).click()
            expect(page.locator("#login-dialog")).not_to_be_visible()
            page.goto(args.url+"/#research")
            expect(page.get_by_role("heading", name="Realtime research", exact=True)).to_be_visible()
            check("SIMULATION_BANNER", page.get_by_text("SIMULATION · SYNTHETIC DATA ONLY", exact=True).is_visible())
            system = context.request.get(args.url+"/dragon/api/v1/system").json()
            report["backend_build"] = system["build"]
            report["installation"] = system["installation"]
            local_source = Path(__file__).absolute().parents[1]
            seal = local_source / "GENESIS6-BUILD.json"
            if seal.exists():
                expected_source = json.loads(seal.read_text(encoding="utf-8"))["source_sha"]
                check("SEALED_BACKEND_SOURCE_IDENTITY", system["build"]["source_sha"] == expected_source
                      and system["build"].get("payload_verified") is True)
            served = {}
            for asset in ("index.html", "app.js", "style.css", "realtime.js", "realtime.css"):
                expected_bytes = (local_source / "src/dragonhydra/resources/web" / asset).read_bytes()
                actual_bytes = context.request.get(args.url+"/"+asset).body()
                if expected_bytes != actual_bytes:
                    raise AssertionError("SERVED_UI_ASSET_MISMATCH_"+asset)
                served[asset] = hashlib.sha256(actual_bytes).hexdigest()
            report["served_ui_sha256"] = served
            check("SERVED_UI_BYTES_MATCH_SOURCE", len(served) == 5)
            def api(path):
                response = context.request.get(args.url+"/dragon/api/v1/realtime"+path)
                if response.status != 200:
                    raise AssertionError(f"API_GET_{path}_{response.status}")
                return response.json()
            def ready():
                expect(page.get_by_role("button", name="Refresh research", exact=True)).to_be_enabled()
            if args.resume:
                previous = json.loads(args.resume.read_text(encoding="utf-8"))
                mid = previous["match_id"]
                page.locator("#research-match").select_option(mid)
                ready()
                expect(page.locator("[data-testid=observed-score]")).to_have_text("0 – 1")
                rows = api(f"/matches/{mid}/timeline")["items"]
                check("SERVER_PROCESS_RESTART_HISTORY", sha(rows) == previous["timeline_sha256"])
                check("RESTART_NO_DUPLICATE_EVENTS", api(f"/matches/{mid}")["metrics"]["events_accepted"] == previous["events_accepted"])
                check("RESTART_COMPLETED_CURSOR", api(f"/matches/{mid}")["replay"]["status"] == "COMPLETED")
                report.update(match_id=mid, timeline_sha256=sha(rows))
            else:
                check("PASSIVE_OPEN_CREATES_NO_SCENARIO", api("/matches")["items"] == [])
                page.get_by_role("button", name="New standard simulation", exact=True).click()
                expect(page.locator("#research-match")).to_be_visible()
                ready()
                mid = page.locator("#research-match").input_value()
                check("EXPLICIT_SCENARIO_CREATION", mid.startswith("virtual-"))
                page.get_by_role("button", name="Step", exact=True).click()
                ready()
                check("UI_STEP_ADVANCES_VIRTUAL_CLOCK", api(f"/matches/{mid}")["state"]["revision"] == 1)
                page.locator("#research-speed").select_option("100")
                page.get_by_role("button", name="Play", exact=True).click()
                ready()
                page.get_by_role("button", name="Pause", exact=True).click()
                ready()
                paused = api(f"/matches/{mid}")["replay"]["position"]
                page.wait_for_timeout(1200)
                check("PAUSE_AND_PASSIVE_POLL_DO_NOT_ADVANCE_TIME", api(f"/matches/{mid}")["replay"]["position"] == paused)
                page.get_by_role("button", name="Resume", exact=True).click()
                ready()
                page.get_by_role("button", name="Pause", exact=True).click()
                ready()
                check("PLAY_RESUME_PAUSE", api(f"/matches/{mid}")["replay"]["status"] == "PAUSED")
                page.locator("#research-steps").fill("100")
                page.get_by_role("button", name="Step", exact=True).click()
                ready()
                expect(page.locator("[data-testid=observed-score]")).to_have_text("0 – 1")
                check("UI_FINISHED_OBSERVED_SCORE", api(f"/matches/{mid}")["state"]["status"] == "FINISHED")
                rows = api(f"/matches/{mid}/timeline")["items"]
                parent_hash = sha(rows)
                red = next(row for row in rows if row["event_type"] == "RED_CARD")
                page.get_by_label("Forecast revision", exact=True).select_option(str(red["revision"]))
                expect(page.locator(".rt-selected-caption")).to_contain_text("historical selection")
                check("INTERACTIVE_PROBABILITY_TIMELINE", page.locator("svg .rt-prob-point").count() >= len(rows)*3)
                page.get_by_role("tab", name="10 min", exact=True).click()
                check("HORIZON_SELECT", page.get_by_role("tab", name="10 min", exact=True).get_attribute("aria-selected") == "true")
                page.get_by_role("button", name="Investigate this revision", exact=True).click()
                ready()
                analysis = next(a for a in api(f"/matches/{mid}")["analyses"] if a["event_revision"] == red["state_revision"])
                check("UI_WORKING_REASONING_TOOL_LOOP", analysis["status"] == "completed" and len(analysis["tool_results"]) == 4)
                page.get_by_role("tab", name="Tools", exact=True).click()
                check("EVIDENCE_INSPECTION", page.get_by_role("tab", name="Tools", exact=True).get_attribute("aria-selected") == "true")
                page.screenshot(path=str(output / "timeline.png"), full_page=False)
                page.get_by_role("button", name="Run 400-case relevance experiment", exact=True).click()
                ready()
                expect(page.locator(".rt-experiment tbody tr")).to_have_count(100)
                check("UI_RELEVANCE_TABLE", len(api("/experiments")["rows"]) == 100)
                page.locator(".rt-experiment").scroll_into_view_if_needed()
                page.screenshot(path=str(output / "relevance.png"), full_page=False)
                page.locator("#research-seed").fill("-1")
                page.get_by_role("button", name="New standard simulation", exact=True).click()
                ready()
                expect(page.locator(".rt-error")).to_contain_text("integer seed")
                check("VALIDATION_ERROR_VISIBLE", len(api("/matches")["items"]) == 1)
                page.locator("#research-seed").fill("73")
                page.locator("#research-universe").select_option("tempo_signal")
                page.locator("#research-branch-name").fill("virtual-ui-fork")
                page.get_by_role("button", name="Rewind into new branch", exact=True).click()
                ready()
                child = page.locator("#research-match").input_value()
                check("UI_REWIND_CREATES_NEW_MATCH", child != mid and api(f"/matches/{child}")["state"]["revision"] == red["state_revision"])
                check("PARENT_TIMELINE_IMMUTABLE", sha(api(f"/matches/{mid}/timeline")["items"]) == parent_hash)
                page.locator("#research-match").select_option(mid)
                ready()
                report.update(match_id=mid, timeline_sha256=parent_hash, child_match_id=child,
                              events_accepted=api(f"/matches/{mid}")["metrics"]["events_accepted"])
            page.evaluate("window.scrollTo(0,0)")
            page.screenshot(path=str(output / "workspace.png"), full_page=False)
            page.set_viewport_size({"width": 520, "height": 900})
            page.screenshot(path=str(output / "narrow.png"), full_page=False)
            check("NO_PAGE_ERRORS", report["page_errors"] == [])
            context.close()
            browser.close()
        report["status"] = "PASS"
    except Exception as error:
        report.update(status="FAILED", failure=f"{type(error).__name__}: {error}")
        raise
    finally:
        (output / "BROWSER.json").write_text(json.dumps(report, indent=2)+"\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "checks": len(report["checks"]), "report": str(output / "BROWSER.json")}))


if __name__ == "__main__":
    main()
