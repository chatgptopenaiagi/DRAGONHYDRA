"""Promote the exact accepted A8 Setup, with evidence-bound delivery reports.

Run from the repository using its existing Python runtime. This does not build,
install, start services, read authentication state, or overwrite an old delivery.
"""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[2]
NAME = "DRAGONHYDRA-GENESIS-A8-Windows-x64-Setup.exe"
SETUP_SHA = "27b7b310fe78baeea76275cfc53ddacc254c99c60e7dcc641f813692398846fa"
CLIENT_SHA = "f4e8fbae68c4fdc3f52c7f9baaeb98f375df26e34dced3dc87c7988d9a4c0617"
CANDIDATE = "dist/connections/genesis-a8-candidate/DRAGONHYDRA-0.4.1-dev.1-Workstation-win-x64-Setup.exe"
DELIVERY = "dist/windows/GENESIS-A8"
EVIDENCE = "build/workstation/evidence/genesis-a8/"
RECEIPTS = {
    "upgrade": EVIDENCE + "final-upgrade-r1.json",
    "service_restart": EVIDENCE + "final-service-restart-r1.json",
    "native_journey": EVIDENCE + "final-native-full-r2/verification.json",
    "bare_client": EVIDENCE + "final-bare-client-r1/verification.json",
    "post_service_persistence": EVIDENCE + "final-post-service-persistence-r1/verification.json",
    "database_select": EVIDENCE + "final-database-readonly-r1.json",
    "regressions": EVIDENCE + "final-focused-regressions-r1.json",
    "independent_review": "docs/handover/verified-reports/GENESIS-A8-INDEPENDENT-PACKAGE-REVIEW.json",
    "component_reuse": "build/connections/genesis-a8-client/COMPONENT-REUSE.json",
}


def digest(path):
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def read(relative):
    return json.loads((ROOT / relative).read_text(encoding="utf-8-sig"))


def write(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main():
    final = ROOT / DELIVERY
    assert not final.exists(), "Existing A8 delivery must remain immutable"
    setup = ROOT / CANDIDATE
    assert setup.stat().st_size == 64769361 and digest(setup) == SETUP_SHA
    prior = ROOT / "dist/connections/external-links-workstation-20261101/DRAGONHYDRA-0.4.1-dev.1-Workstation-win-x64-Setup.exe"
    assert digest(prior) == "0f3a4aa6bcedfd29d37cb790f61d466e98e6a62a235af6b945055f28db83e135"
    evidence = {name: read(path) for name, path in RECEIPTS.items()}
    assert all(item["passed"] is True for item in evidence.values())
    for name, count in {"upgrade": 6, "service_restart": 6, "native_journey": 20,
                        "bare_client": 3, "post_service_persistence": 2}.items():
        checks = evidence[name]["checks"]
        assert len(checks) == count and all(check["passed"] is True for check in checks)
    assert evidence["upgrade"]["installer_exit_code"] == 0
    assert evidence["upgrade"]["installer"]["sha256"] == SETUP_SHA
    journey = evidence["native_journey"]
    assert journey["binary_sha256"] == CLIENT_SHA
    assert evidence["bare_client"]["binary_sha256"] == CLIENT_SHA
    assert evidence["post_service_persistence"]["binary_sha256"] == CLIENT_SHA
    assert journey["external_links"]["normal_native_mouse_clicks"] == 10
    assert journey["external_links"]["connection_settings_and_counts_unchanged"] is True
    assert journey["persistence_snapshot"]["records"] == 760
    assert journey["persistence_snapshot"] == evidence["post_service_persistence"]["persistence_snapshot"]
    assert evidence["database_select"]["result"]["answer"] == 42
    assert evidence["component_reuse"]["unchanged_server_files"] == 711
    assert evidence["component_reuse"]["unchanged_web_stack_files"] == 9941
    review = evidence["independent_review"]
    assert review["payload_manifests_byte_identical"] is True
    for component in review["critical_extracted_installed_components"]:
        for scope in ("extracted", "installed"):
            actual = component[scope]
            assert digest(ROOT / actual["path"]) == actual["sha256"]
    now = datetime.now(timezone.utc).isoformat()
    receipt_manifest = {name: {"path": path, "sha256": digest(ROOT / path)}
                        for name, path in RECEIPTS.items()}
    raw_build_path = "build/connections/genesis-a8-candidate-workstation/BUILD-REPORT.json"
    raw_build = read(raw_build_path)
    client = read("build/connections/genesis-a8-client/BUILD-INFO.json")
    assert raw_build["built"] is True and raw_build["artifact"]["sha256"] == SETUP_SHA
    status = {"built": True, "installed": True, "executed": True, "tested": True,
              "verified": True, "local_delivery": True, "release_uploaded": False,
              "clean_machine_tested": False, "os_reboot_tested": False,
              "production_signed": False}
    artifact = {"filename": NAME, "path": str(final / NAME), "bytes": 64769361,
                "sha256": SETUP_SHA, "signing_status": "NotSigned"}
    build = {
        "schema_version": 1, "milestone": "GENESIS A8", "recorded_at": now,
        "status": status, "artifact": artifact,
        "declared_workstation_version": "0.4.1-dev.1",
        "embedded_client_identity": client, "client_binary_sha256": CLIENT_SHA,
        "reused_server": raw_build["kernel_override"],
        "payload": {"files": raw_build["payload_files"], "bytes": raw_build["payload_bytes"],
                    "manifest_sha256": review["payload_manifests"][0]["sha256"],
                    "component_reuse": evidence["component_reuse"]},
        "components": ["Tauri 2.12.5 / official opener 2.7.2 desktop",
                       "Frozen Python API server/worker and private dependencies",
                       "SQLite football-data persistence", "Apache 2.4.65", "PHP 8.4.27",
                       "MariaDB 10.11.16 (Joomla database)", "Joomla 6.2.0 / existing DRAGONHYDRA extension",
                       "Windows LocalService wrapper", "Native workstation launcher",
                       "Configuration templates / WebView2 bootstrapper"],
        "build_pipeline": {
            "client": "Existing cached Tauri CLI build --no-bundle --target x86_64-pc-windows-msvc -- --locked --offline",
            "unified": "scripts/Build-Workstation.ps1 -RepackageOnly -BuildRoot build/connections/genesis-a8-candidate-workstation -ClientBuildRoot build/connections/genesis-a8-client/verified-payload -OutputRoot dist/connections/genesis-a8-candidate",
            "raw_builder_report": {"path": raw_build_path, "sha256": digest(ROOT / raw_build_path)},
            "build_steps": raw_build["steps"],
            "note": "Raw builder report is a build-time snapshot; this later report adds installation/runtime evidence. No server or web-stack rebuild."},
        "installation_acceptance": {
            "scope": "Isolated installation on current Windows 11 x64 host; complete Setup upgrade",
            "install_root": evidence["upgrade"]["install_root"],
            "state_root": evidence["upgrade"]["state_root"],
            "service": evidence["upgrade"]["service_name"],
            "installer_arguments_executed": evidence["upgrade"]["installer_arguments"],
            "installer_exit_code": 0, "data_retained": True,
            "independent_existing_services_unchanged": True},
        "evidence": receipt_manifest,
        "limitations": ["Unsigned development package", "No clean-machine or OS reboot acceptance",
                        "WebView2 installation requires internet if runtime is absent",
                        "SQLite remains application authority; no MariaDB application-backend cutover",
                        "No new GitHub release uploaded; historical releases untouched"],
    }
    tests = {
        "schema_version": 1, "milestone": "GENESIS A8", "passed": True,
        "recorded_at": now, "artifact": artifact, "client_binary_sha256": CLIENT_SHA,
        "embedded_source_commit": client["source_sha"],
        "acceptance_groups": {name: {"passed": True, "groups": len(evidence[name]["checks"])}
                              for name in ("upgrade", "native_journey", "bare_client", "service_restart", "post_service_persistence")},
        "regressions": evidence["regressions"],
        "native_runtime": {"automatic_shortcut_pairing": True, "bare_exe_pairing": True,
                           "dashboard_and_match_browsing": True, "team_navigation": True,
                           "calculated_standings_teams": 20, "retained_records": 760,
                           "retained_example": journey["selected_match"],
                           "structured_analysis": next(check for check in journey["checks"] if check["name"] == "sports_analysis_structured_result"),
                           "deterministic_explanation": next(check for check in journey["checks"] if check["name"] == "deterministic_analysis_native_job"),
                           "exports": next(check for check in journey["checks"] if check["name"] == "actual_json_csv_excel_export_files"),
                           "external_links": journey["external_links"],
                           "administration": next(check for check in evidence["bare_client"]["checks"] if check["name"] == "native_administration_default_browser_open"),
                           "persistence_snapshot": journey["persistence_snapshot"],
                           "post_service_snapshot_identical": True,
                           "connection_settings_pairing_and_config_preserved": True,
                           "page_errors": journey["page_errors"]},
        "database_component": evidence["database_select"],
        "service_preservation": {"before": evidence["service_restart"]["protected_services_before"],
                                 "after": evidence["service_restart"]["protected_services_after"],
                                 "same_status_pid_and_path": True},
        "evidence": receipt_manifest,
        "preserved_diagnostics": [
            "Initial Setup exited0; first verifier attempted protected kernel-token read and failed. Corrected verifier uses client metadata, no ACL change.",
            "First full journey helper could not locate a finished match in paginated future fixtures; exact team search fixed the helper. The successful r2 report supersedes it.",
            "Old desktop Administration window.open failure reproduced; rebuilt and finally installed desktop passes."],
        "limits": ["External links: exact native clicked HTTPS destinations and registered default Edge window/title receipts, no all-provider address-bar capture",
                   "No separate provider account-management links are currently exposed; nine adapter documentation metadata URLs are not independently rendered",
                   "Finished retained match correctly abstains from an unavailable prospective forecast; no new prediction claim",
                   "XLSX native UI plus authenticated native-page JSON/CSV/Excel downloads verified; native SaveAs dialogs not exercised",
                   "Existing connection settings were read and compared; no provider key, paid request, model inference or vault mutation",
                   "The earlier22-test repair suite is historical; this task executed5 Python wrappers containing7 native pairing cases,3 native popup cases and3 JS tests"],
    }
    assembling = final.with_name("GENESIS-A8.assembling-" + datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S"))
    assembling.mkdir(parents=True, exist_ok=False)
    shutil.copy2(setup, assembling / NAME)
    readme = (ROOT / "build/connections/genesis-a8-client/README-INSTALL.draft.txt").read_text(encoding="utf-8-sig")
    readme = readme.replace("Registration, documentation and account-management links open the provider's\nweb address", "All ten currently exposed provider registration and documentation links open\nthe provider's web address")
    (assembling / "README-INSTALL.txt").write_text(readme, encoding="utf-8")
    write(assembling / "BUILD-REPORT.json", build)
    write(assembling / "TEST-REPORT.json", tests)
    names = [NAME, "BUILD-REPORT.json", "TEST-REPORT.json", "README-INSTALL.txt"]
    sums = "".join(f"{digest(assembling / name)}  {name}\n" for name in names)
    (assembling / "SHA256SUMS.txt").write_text(sums, encoding="ascii")
    for line in sums.splitlines():
        expected, name = line.split("  ", 1)
        assert digest(assembling / name) == expected
    assert {path.name for path in assembling.iterdir()} == set(names + ["SHA256SUMS.txt"])
    assembling.rename(final)
    print(json.dumps({"delivered": True, "directory": str(final), "artifact": artifact}, indent=2))


if __name__ == "__main__":
    main()
