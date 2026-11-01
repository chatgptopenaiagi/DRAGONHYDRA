"""Genuine browser acceptance for the existing original Joomla workstation.

Credentials are read only in memory. No trace, HAR, cookies, full HTML, password
or vendor exception strings are saved. Only normal Joomla login POSTs are allowed;
provider, import, model, settings and tour-preference mutations are blocked.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import parse_qs, urlsplit

from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[2]
STATE = ROOT / "build/workstation/test-install/state data"
INSTALL = ROOT / "build/workstation/test-install/application files"
EVIDENCE = ROOT / "build/joomla-recovery-20261101/evidence"
ORIGIN = "http://127.0.0.1:18740"
ADMIN = ORIGIN + "/administrator/"
COMPONENT = ADMIN + "index.php?option=com_dragonhydra"


def fingerprint(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def safe_location(url):
    parts = urlsplit(url)
    query = parse_qs(parts.query)
    return {
        "origin": parts.scheme + "://" + parts.netloc,
        "path": parts.path,
        "public_query": {key: values[0] for key, values in query.items()
                         if key in ("option", "section", "match_id") and values
                         and re.fullmatch(r"[A-Za-z0-9_-]{1,100}", values[0])},
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=EVIDENCE / "browser-r2")
    args = parser.parse_args()
    output = args.output.resolve()
    assert output.parent == EVIDENCE.resolve() and re.fullmatch(r"browser-[A-Za-z0-9-]+", output.name)
    assert not output.exists(), "Preserve previous browser evidence"
    output.mkdir(parents=True)
    report = {
        "schema_version": 1, "passed": False,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "scope": "Actual installed Joomla in genuine Microsoft Edge browser session",
        "web_origin": ORIGIN, "service": "DragonhydraWorkstationTest",
        "helper_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "checks": [], "page_errors": [], "blocked_requests": [],
        "password_reset": False, "provider_or_import_requests": False,
        "credential_values_logged": False, "trace_har_cookie_or_html_saved": False,
        "stage": "configuration_binding",
    }
    browser = None
    context = None

    def check(name, passed, **evidence):
        report["checks"].append({"name": name, "status": "PASS" if passed else "FAIL", **evidence})
        assert passed, name

    def login(page, cfg, check_name):
        expect(page.locator("#mod-login-username")).to_be_visible()
        page.locator("#mod-login-username").fill(cfg["admin_user"])
        page.locator("#mod-login-password").fill(cfg["admin_password"])
        page.get_by_role("button", name="Log in", exact=True).click()
        page.wait_for_load_state("domcontentloaded")
        expect(page.locator("#mod-login-username")).not_to_be_visible(timeout=20000)
        page.keyboard.press("Escape")
        check(check_name, True, username=cfg["admin_user"],
              credential_entry="Existing owned configuration read only in memory")

    def open_from_administrator_menu(page, check_name):
        navigation = page.locator(".main-nav-container")
        dragon = navigation.locator('a[aria-label="DRAGONHYDRA"]').first
        if not dragon.is_visible():
            navigation.get_by_role("link", name="Components", exact=True).click()
        expect(dragon).to_be_visible()
        dragon.click()
        sources = navigation.locator('a[href*="option=com_dragonhydra"][href*="section=sources"]').first
        expect(sources).to_be_visible()
        sources.click()
        page.wait_for_load_state("domcontentloaded")
        expect(page.locator(".dragonhydra-administration").get_by_role("heading", name="Data sources", exact=True)).to_be_visible()
        check(check_name, True, observed_menu_path=["Components", "DRAGONHYDRA", "Data sources"],
              location=safe_location(page.url))

    try:
        cfg = json.loads((STATE / "workstation.json").read_text(encoding="utf-8-sig"))
        assert Path(cfg["state_root"]).resolve() == STATE.resolve()
        assert Path(cfg["install_root"]).resolve() == INSTALL.resolve()
        assert cfg["service_name"] == "DragonhydraWorkstationTest"
        assert cfg["web_port"] == 18740 and cfg["database_port"] == 18741 and cfg["api_port"] == 18744
        check("exact_existing_profile_binding", True, backend_port=18744, database_port=18741)
        report["stage"] = "edge_startup"
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel="msedge", headless=True)
            context = browser.new_context(viewport={"width": 1440, "height": 1000}, reduced_motion="reduce")

            def scoped_route(route):
                request = route.request
                parts = urlsplit(request.url)
                same_origin = parts.scheme + "://" + parts.netloc == ORIGIN
                allowed = same_origin and request.method in ("GET", "HEAD")
                if same_origin and request.method == "POST" and parts.path == "/administrator/index.php":
                    form = parse_qs(request.post_data or "")
                    allowed = form.get("option") == ["com_login"] and form.get("task") == ["login"]
                if allowed:
                    route.continue_()
                else:
                    report["blocked_requests"].append({"method": request.method, "location": safe_location(request.url)})
                    route.abort()

            context.route("**/*", scoped_route)
            page = context.new_page()
            page.on("pageerror", lambda error: report["page_errors"].append({"class": type(error).__name__, "message_sha256": fingerprint(str(error))}))
            report["stage"] = "unauthenticated_component"
            response = page.goto(COMPONENT, wait_until="domcontentloaded", timeout=30000)
            expect(page.locator("#mod-login-username")).to_be_visible()
            expect(page.locator(".dragonhydra-administration")).to_have_count(0)
            check("unauthenticated_browser_requires_real_joomla_login", response.status == 200)
            token_fields = page.locator('input[type="hidden"][value="1"]').evaluate_all("nodes => nodes.filter(n => /^[a-f0-9]{32}$/.test(n.name)).length")
            check("real_login_form_csrf_present", token_fields == 1, token_field_count=token_fields)
            report["stage"] = "genuine_login"
            login(page, cfg, "genuine_browser_administrator_authentication")
            report["stage"] = "joomla_administrator_menu"
            open_from_administrator_menu(page, "component_opens_from_actual_joomla_administrator_menu")
            report["stage"] = "authenticated_component_sources"
            page.goto(COMPONENT + "&section=sources", wait_until="domcontentloaded")
            component = page.locator(".dragonhydra-administration")
            expect(component).to_be_visible()
            expect(component.get_by_role("heading", name="Data sources", exact=True)).to_be_visible()
            expect(component.locator("tbody tr")).to_have_count(10)
            expect(component.locator(".alert-warning")).to_have_count(0)
            check("authenticated_sources_component_and_signed_backend_table", True, providers=10,
                  location=safe_location(page.url))
            source_shot = output / "authenticated-sources.png"
            component.screenshot(path=str(source_shot), animations="disabled")
            report["screenshots"] = [{"path": str(source_shot), "sha256": hashlib.sha256(source_shot.read_bytes()).hexdigest(),
                                      "scope": "Component only; no credential inputs or options page"}]
            report["stage"] = "authenticated_matches"
            page.goto(COMPONENT + "&section=matches", wait_until="domcontentloaded")
            component = page.locator(".dragonhydra-administration")
            expect(component.get_by_role("heading", name="Matches and teams", exact=True)).to_be_visible()
            first_match = component.locator("tbody th a").first
            expect(first_match).to_be_visible()
            match_label = first_match.inner_text()
            match_parts = urlsplit(first_match.get_attribute("href"))
            match_id = parse_qs(match_parts.query)["match_id"][0]
            assert re.fullmatch("[a-f0-9]{64}", match_id)
            first_match.click()
            page.wait_for_load_state("domcontentloaded")
            expect(component.get_by_role("heading", name=match_label, exact=True)).to_be_visible()
            expect(component.locator(".alert-warning")).to_have_count(0)
            dashboard = component.locator('a[href*="/#match/"]').get_attribute("href")
            check("real_retained_match_opened_by_component_link", match_id in page.url
                  and dashboard == "http://127.0.0.1:18744/#match/" + match_id,
                  match_id=match_id, match_label=match_label, backend_port=18744,
                  location=safe_location(page.url))
            match_shot = output / "authenticated-match.png"
            component.screenshot(path=str(match_shot), animations="disabled")
            report["screenshots"].append({"path": str(match_shot), "sha256": hashlib.sha256(match_shot.read_bytes()).hexdigest(),
                                          "scope": "Component public retained match presentation only"})
            report["stage"] = "system_and_session_navigation"
            page.goto(COMPONENT + "&section=system", wait_until="domcontentloaded")
            expect(component.get_by_role("heading", name="System", exact=True)).to_be_visible()
            expect(component.locator(".alert-warning")).to_have_count(0)
            check("authenticated_system_section_signed_backend_response", "sqlite" in component.inner_text().lower())
            page.goto(COMPONENT + "&section=sources", wait_until="domcontentloaded")
            expect(page.locator("#mod-login-username")).to_have_count(0)
            expect(component.get_by_role("heading", name="Data sources", exact=True)).to_be_visible()
            expect(component.locator("tbody tr")).to_have_count(10)
            check("genuine_authenticated_browser_session_persists_across_navigation", True,
                  authenticated_navigation_count=5, cookie_count=len(context.cookies(ORIGIN)))
            report["stage"] = "actual_web_php_runtime"
            page.goto(ADMIN + "index.php?option=com_admin&view=sysinfo", wait_until="domcontentloaded")
            expect(page.locator("#mod-login-username")).to_have_count(0)
            # Read only four public runtime fields; never serialize configuration/phpinfo HTML.
            labels = {
                "PHP Version": "php_version", "WebServer to PHP Interface": "php_sapi",
                "Joomla! Version": "joomla_version", "Database Version": "database_version",
            }
            runtime = {}
            # The later PHP-information tab also has .sysinfo with unrelated tables.
            # Scope to the first, public System Information table only.
            for row in page.locator(".sysinfo").first.locator("table tbody tr").all():
                heading = row.locator("th").inner_text().strip().rstrip(":")
                if heading not in labels:
                    continue
                text = row.locator("td").inner_text().strip()
                if labels[heading] == "php_sapi":
                    assert re.fullmatch(r"[A-Za-z0-9_-]{1,40}", text)
                    runtime[labels[heading]] = text
                else:
                    version = re.search(r"\d+\.\d+\.\d+", text)
                    assert version
                    runtime[labels[heading]] = version.group()
            check("authenticated_joomla_reports_actual_web_php_and_sapi",
                  runtime.get("php_version") == "8.4.27" and runtime.get("php_sapi") == "apache2handler",
                  runtime=runtime)
            report["stage"] = "genuine_joomla_logout_open_user_menu"
            page.goto(COMPONENT + "&section=sources", wait_until="domcontentloaded")
            page.locator(".header-profile > button.dropdown-toggle:visible").first.click()
            report["stage"] = "genuine_joomla_logout_observed_link"
            logout = page.locator('.header-profile a[href*="option=com_login"][href*="task=logout"]:visible').first
            expect(logout).to_be_visible()
            logout_query = parse_qs(urlsplit(logout.get_attribute("href")).query)
            logout_csrf_present = any(re.fullmatch(r"[a-f0-9]{32}", name) and value == ["1"]
                                      for name, value in logout_query.items())
            assert logout_csrf_present
            report["stage"] = "genuine_joomla_logout_click"
            logout.click()
            page.wait_for_load_state("domcontentloaded")
            expect(page.locator("#mod-login-username")).to_be_visible()
            check("actual_joomla_user_menu_logout", True, observed_logout_control="Joomla User Menu link",
                  csrf_present=True, cookies_forcibly_cleared=False)
            page.goto(COMPONENT + "&section=sources", wait_until="domcontentloaded")
            expect(page.locator("#mod-login-username")).to_be_visible()
            expect(page.locator(".dragonhydra-administration")).to_have_count(0)
            check("protected_component_requires_authentication_after_logout", True)
            report["stage"] = "close_and_reopen_fresh_browser"
            context.close()
            context = None
            browser.close()
            browser = None
            browser = playwright.chromium.launch(channel="msedge", headless=True)
            context = browser.new_context(viewport={"width": 1440, "height": 1000}, reduced_motion="reduce")
            context.route("**/*", scoped_route)
            page = context.new_page()
            page.on("pageerror", lambda error: report["page_errors"].append({"class": type(error).__name__, "message_sha256": fingerprint(str(error))}))
            page.goto(COMPONENT, wait_until="domcontentloaded")
            expect(page.locator("#mod-login-username")).to_be_visible()
            check("fresh_reopened_edge_requires_new_administrator_session", True,
                  storage_state_imported=False, previous_browser_process_closed=True)
            login(page, cfg, "fresh_reopened_browser_genuine_administrator_login")
            open_from_administrator_menu(page, "fresh_login_component_opens_through_administrator_menu")
            expect(page.locator(".dragonhydra-administration tbody tr")).to_have_count(10)
            check("fresh_login_preserves_actual_provider_table", True, providers=10)
            check("no_fatal_browser_javascript_errors", not report["page_errors"], fatal_errors=len(report["page_errors"]))
            report["stage"] = "complete"
            report["passed"] = True
            context.close()
            context = None
            browser.close()
            browser = None
    except Exception as error:
        # Vendor exception messages can contain locators/form values; retain only class/fingerprint.
        report["failure"] = {"class": type(error).__name__, "message_sha256": fingerprint(str(error)),
                             "locator_ambiguity": "strict mode violation" in str(error).lower()}
    finally:
        if context is not None:
            try:
                context.close()
            except Exception:
                pass
        if browser is not None:
            try:
                browser.close()
            except Exception:
                pass
        report["browser_closed"] = True
        report["finished_at"] = datetime.now(timezone.utc).isoformat()
        target = output / "verification.json"
        assert not target.exists()
        target.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(json.dumps({"passed": report["passed"], "stage": report["stage"], "checks": len(report["checks"]), "report": str(target)}))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
