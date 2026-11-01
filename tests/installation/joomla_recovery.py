"""Scoped existing-workstation backup and genuine Joomla HTTP acceptance.

Credentials/cookies stay in memory or the separately ACL-protected backup folder.
No password reset, provider request, data import, extension install or SQL repair.
"""
import argparse
from datetime import datetime, timezone
import hashlib
from html import unescape
from html.parser import HTMLParser
import http.cookiejar
import json
from pathlib import Path
import re
import shutil
import subprocess
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
STATE = ROOT / "build/workstation/test-install/state data"
INSTALL = ROOT / "build/workstation/test-install/application files"
WORK = ROOT / "build/joomla-recovery-20261101"
PRIVATE = WORK / "private-backup"
EVIDENCE = WORK / "evidence"


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def sha(path):
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def canonical(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def write(path, value):
    assert not path.exists(), "Preserve earlier evidence"
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


class Inputs(HTMLParser):
    def __init__(self):
        super().__init__()
        self.hidden = {}
        self.links = []
        self.login_action = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "form" and attrs.get("id") == "form-login":
            self.login_action = attrs.get("action", "")
        if tag == "input" and attrs.get("type") == "hidden" and attrs.get("name"):
            self.hidden[attrs["name"]] = attrs.get("value", "")
        if tag == "a" and attrs.get("href"):
            self.links.append(attrs["href"])


def component_renders(html, heading):
    """Joomla's global noscript alert is not a failed component request."""
    return ('dragonhydra-administration' in html and 'mod-login-username' not in html
            and heading in html and 'BRIDGE_NOT_CONFIGURED' not in html
            and 'KERNEL_UNREACHABLE' not in html
            and '<div class="alert alert-warning" role="alert">' not in html)


def login_action(admin_url, inputs):
    assert inputs.login_action is not None, "Actual login form action is required"
    target = urllib.parse.urljoin(admin_url, inputs.login_action)
    assert urllib.parse.urlsplit(target).netloc == "127.0.0.1:18740"
    assert target == admin_url + "index.php", "Credentials stay at the verified login endpoint"
    return target


class Recovery:
    def __init__(self):
        self.cfg = read(STATE / "workstation.json")
        assert Path(self.cfg["state_root"]) == STATE and Path(self.cfg["install_root"]) == INSTALL
        assert self.cfg["service_name"] == "DragonhydraWorkstationTest"
        assert self.cfg["web_port"] == 18740 and self.cfg["database_port"] == 18741
        self.origin = "http://127.0.0.1:18740"
        self.api = "http://127.0.0.1:" + str(self.cfg["api_port"]) + "/dragon/api/v1"
        self.admin = self.origin + "/administrator/"
        self.component = self.admin + "index.php?option=com_dragonhydra"
        self.jar = http.cookiejar.MozillaCookieJar(str(PRIVATE / "acceptance-cookies.txt"))
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), urllib.request.HTTPCookieProcessor(self.jar))
        self.token = read(STATE / "client/local-session.json")["token"]

    def request(self, url, *, form=None, local_auth=False, anonymous=False):
        headers = {"User-Agent": "DRAGONHYDRA-existing-workstation-recovery/1"}
        if local_auth:
            assert url.startswith(self.api + "/")
            headers["Authorization"] = "Bearer " + self.token
        data = None if form is None else urllib.parse.urlencode(form).encode()
        req = urllib.request.Request(url, data=data, headers=headers)
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({})) if anonymous else self.opener
        try:
            response = opener.open(req, timeout=20)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            body = response.read(4 * 1024 * 1024 + 1)
            assert len(body) <= 4 * 1024 * 1024
            return response.status, body.decode("utf-8", errors="replace"), response.headers

    def api_read(self, path):
        status, text, _ = self.request(self.api + path, local_auth=True)
        assert status == 200, "API read failed"
        return json.loads(text)

    def snapshot(self):
        connections = self.api_read("/connections")
        items = []
        offset = 0
        while True:
            page = self.api_read("/matches?limit=100&offset=" + str(offset))
            batch = page["items"]
            items.extend(batch)
            offset += len(batch)
            if offset >= page["total"]:
                break
            assert batch and offset < 20000
        fingerprints = {}
        for relative in ("workstation.json", "first-run.json", "site/configuration.php", "client/local-session.json", "web-config/httpd.conf", "web-config/php.ini"):
            fingerprints[relative] = sha(STATE / relative)
        return {"records": len(items), "all_matches_sha256": canonical(items),
                "match_identifiers_sha256": canonical(sorted(item["id"] for item in items)),
                "provider_connections_sha256": canonical(connections),
                "provider_record_counts": {item["id"]: item.get("record_count") for item in connections["items"]},
                "configuration_sha256": fingerprints}

    def backup(self):
        assert PRIVATE.is_dir() and not (PRIVATE / "joomla-and-core.sql").exists()
        report = {"schema_version": 1, "passed": False, "started_at": datetime.now(timezone.utc).isoformat(),
                  "private_backup_directory": str(PRIVATE), "files": [], "configuration_or_database_repairs": False}
        for relative in ("workstation.json", "first-run.json", "site/configuration.php", "web-config/httpd.conf", "web-config/php.ini", "web-config/my.ini"):
            source = STATE / relative
            target = PRIVATE / "files" / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            report["files"].append({"relative_path": relative, "sha256": sha(target), "bytes": target.stat().st_size})
        source = STATE / "site/administrator/components/com_dragonhydra"
        shutil.copytree(source, PRIVATE / "com_dragonhydra")
        report["component_files_backed_up"] = len([path for path in source.rglob("*") if path.is_file()])
        bridge = STATE / "kernel/joomla-bridge.json"
        try:
            shutil.copy2(bridge, PRIVATE / "joomla-bridge.json")
            report["bridge_backup"] = "Copied into private ACL-protected folder"
        except PermissionError:
            report["bridge_backup"] = "Current token cannot read protected bridge; no bridge modification is permitted without an elevated backup"
        defaults = PRIVATE / "dump-client.cnf"
        password = self.cfg["root_password"].replace("\\", "\\\\").replace('"', '\\"')
        defaults.write_text('[client]\nhost=127.0.0.1\nport=' + str(self.cfg["database_port"]) + '\nuser=root\npassword="' + password + '"\n', encoding="utf-8")
        try:
            dump = INSTALL / "web/mariadb/bin/mysqldump.exe"
            command = [str(dump), "--defaults-extra-file=" + str(defaults), "--single-transaction", "--skip-lock-tables", "--hex-blob", "--databases", self.cfg["db_name"], self.cfg["core_db_name"]]
            with (PRIVATE / "joomla-and-core.sql").open("xb") as output:
                result = subprocess.run(command, stdout=output, stderr=subprocess.PIPE, timeout=90)
            report["database_dump"] = {"command_credentials_exposed": False, "exit_code": result.returncode,
                                       "bytes": (PRIVATE / "joomla-and-core.sql").stat().st_size,
                                       "sha256": sha(PRIVATE / "joomla-and-core.sql"), "stderr_bytes": len(result.stderr)}
            assert result.returncode == 0 and report["database_dump"]["bytes"] > 1000
        finally:
            defaults.unlink(missing_ok=True)
        report["sports_and_configuration_baseline"] = self.snapshot()
        report["passed"] = True
        report["finished_at"] = datetime.now(timezone.utc).isoformat()
        write(EVIDENCE / "backup-r1.json", report)
        return {"passed": True, "backup": str(PRIVATE), "database_dump_bytes": report["database_dump"]["bytes"], "records": report["sports_and_configuration_baseline"]["records"]}

    def verify(self, output, resume=False):
        assert output.parent.resolve() == EVIDENCE.resolve() and not output.exists()
        baseline = read(EVIDENCE / "backup-r1.json")
        assert baseline["passed"]
        report = {"schema_version": 1, "passed": False, "started_at": datetime.now(timezone.utc).isoformat(),
                  "web_origin": self.origin, "actual_backend": self.api, "service": self.cfg["service_name"],
                  "genuine_login_post": not resume, "resumed_real_cookie_session": resume,
                  "provider_or_import_requests": False, "password_reset": False, "checks": []}
        def check(name, passed, **evidence):
            report["checks"].append({"name": name, "status": "PASS" if passed else "FAIL", **evidence})
            write_temp()
            assert passed, name
        def write_temp():
            temporary = output.with_suffix(".running.json")
            temporary.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        try:
            status, html, headers = self.request(self.admin, anonymous=True)
            check("apache_and_joomla_login", status == 200 and 'mod-login-username' in html, http_status=status)
            status, html, _ = self.request(self.component, anonymous=True)
            check("anonymous_component_requires_login", status == 200 and 'mod-login-username' in html and 'dragonhydra-administration' not in html, http_status=status)
            if resume:
                self.jar.load(ignore_discard=True, ignore_expires=False)
            else:
                status, html, _ = self.request(self.admin)
                inputs = Inputs(); inputs.feed(html)
                token_names = [key for key in inputs.hidden if re.fullmatch('[a-f0-9]{32}', key)]
                check("login_csrf_form_and_cookie_session", len(token_names) == 1 and len(list(self.jar)) > 0,
                      csrf_token_field_present=len(token_names) == 1, cookie_count=len(list(self.jar)))
                form = inputs.hidden | {"username": self.cfg["admin_user"], "passwd": self.cfg["admin_password"], "option": "com_login", "task": "login"}
                actual_action = login_action(self.admin, inputs)
                status, html, _ = self.request(actual_action, form=form)
                check("genuine_existing_admin_authentication", status == 200 and 'mod-login-username' not in html, http_status=status,
                      username=self.cfg["admin_user"], password_or_session_value_logged=False)
                self.jar.save(ignore_discard=True, ignore_expires=True)
            sources_html = ""
            for section, title in [("sources", "Data sources"), ("matches", "Matches and teams"), ("odds", "Odds administration"), ("models", "AI and models"), ("research", "Research"), ("databases", "Database connections"), ("system", "System")]:
                status, html, _ = self.request(self.component + "&section=" + section)
                check("authenticated_component_" + section, status == 200 and component_renders(html, title),
                      http_status=status, expected_heading=title)
                if section == "sources": sources_html = html
            status, html, _ = self.request(self.component + "&task=actions.sync", form={})
            check("authenticated_mutation_without_csrf_denied", status == 403, http_status=status, provider_acquisition_occurred=False)
            status, html, _ = self.request(self.component + "&task=actions.sync", form={}, anonymous=True)
            check("anonymous_mutation_denied", (status in (401, 403) or 'mod-login-username' in html) and 'Import queued' not in html, http_status=status)
            health = self.api_read("/health/ready")
            check("corresponding_backend_ready", health.get("status") == "ready", api_port=self.cfg["api_port"], health=health)
            default_state = Path("C:/ProgramData/DRAGONHYDRA/client")
            assert read(default_state / "endpoint.json")["url"] == "http://127.0.0.1:18743"
            default_token = read(default_state / "local-session.json")["token"]
            separate_request = urllib.request.Request("http://127.0.0.1:18743/dragon/api/v1/health/ready",
                                                     headers={"Authorization": "Bearer " + default_token})
            with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(separate_request, timeout=15) as response:
                status, separate = response.status, json.load(response)
            check("separate_requested_backend_18743_available", status == 200 and separate.get("status") == "ready", http_status=status,
                  integration_target=False, authenticated_with_corresponding_existing_local_metadata=True,
                  reason="This is the separate ProgramData/default workstation")
            page = self.api_read("/matches?limit=1&offset=0")
            match = page["items"][0]
            status, html, _ = self.request(self.component + "&section=matches&match_id=" + match["id"])
            check("joomla_renders_actual_backend_match", status == 200 and match["home"]["name"] in unescape(html) and match["away"]["name"] in unescape(html)
                  and match["id"] in html and '<div class="alert alert-warning" role="alert">' not in html, http_status=status,
                  match={key:match[key] for key in ("id", "event_date", "source_id", "evidence_id", "home", "away")})
            connections = self.api_read("/connections")
            check("joomla_signed_connections_route", all(item["name"] in unescape(sources_html) for item in connections["items"]), providers=len(connections["items"]))
            status, text, _ = self.request(self.api + "/matches?limit=1", anonymous=True)
            check("unsigned_backend_data_request_denied", status in (401,403), http_status=status)
            current = self.snapshot()
            check("sports_provider_and_configuration_integrity", current == baseline["sports_and_configuration_baseline"], snapshot=current)
            self.jar.save(ignore_discard=True, ignore_expires=True)
            report["passed"] = True
        except Exception as error:
            report["failure_class"] = type(error).__name__
            report["error_details_omitted"] = "No raw request, exception message, cookie, token or password serialized"
        report["finished_at"] = datetime.now(timezone.utc).isoformat()
        write(output, report)
        return {"passed": report["passed"], "groups": len(report["checks"]), "report": str(output), "last_check": report["checks"][-1] if report["checks"] else None}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("backup", "verify", "resume"))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    recovery = Recovery()
    result = recovery.backup() if args.phase == "backup" else recovery.verify(args.output.resolve(), resume=args.phase == "resume")
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result["passed"] else 1)


if __name__ == "__main__":
    main()
