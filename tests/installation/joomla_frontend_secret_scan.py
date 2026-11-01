"""Compare secrets only in Python memory; never inject needles into browser JS.

An optional owner-supplied token arrives on stdin, is compared, and is never used
as an authentication credential or written to an artifact.
"""
import base64
import argparse
from datetime import datetime, timezone
import io
import json
from pathlib import Path
import sys
from urllib.parse import quote, urlencode
from zipfile import ZipFile
from playwright.sync_api import sync_playwright, expect
from joomla_frontend_credentials import load_credentials, load_recovery

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / 'build/joomla-frontend-20261101/evidence'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=EVIDENCE / 'secret-scan-final.json')
    args = parser.parse_args()
    credentials = load_credentials()
    recovery = load_recovery().Recovery()
    supplied_text = sys.stdin.read()
    # The separate in-memory role check established that the supplied value is
    # this existing generated initial-password field, not a service token.
    supplied = json.loads(supplied_text) if supplied_text else {'token': recovery.cfg['admin_password']}
    assert set(supplied) == {'token'}
    values = [credentials['password'], recovery.token, supplied['token']]
    values += [recovery.cfg[key] for key in ('root_password', 'db_password', 'core_db_password', 'admin_password')]
    values = list(set(value for value in values if value))
    patterns = set()
    for value in values:
        patterns.update([value.encode(), json.dumps(value)[1:-1].encode(), quote(value, safe='').encode(),
                         base64.b64encode(value.encode())])
    report = {'schema_version': 1, 'passed': False, 'started_at': datetime.now(timezone.utc).isoformat(),
              'known_secret_values_compared': len(values), 'values_or_fingerprints_emitted': False,
              'needles_sent_to_browser_javascript': False, 'token_used_for_authentication': False,
              'rendered_pages': 0, 'script_resources': 0, 'source_and_report_files': 0,
              'archive_members': 0, 'secret_matches': 0}

    def inspect(data):
        assert not any(pattern in data for pattern in patterns), 'A private-value leak was detected'

    def archive(data):
        with ZipFile(io.BytesIO(data)) as package:
            for member in package.infolist():
                if member.is_dir(): continue
                content = package.read(member)
                if member.filename.endswith('.zip'): archive(content)
                else: inspect(content); report['archive_members'] += 1

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel='msedge', headless=True)
            context = browser.new_context()
            page = context.new_page()
            page.goto('http://127.0.0.1:18740/')
            inspect(page.content().encode())
            page.get_by_role('link', name='Sign in to your workspace').click()
            page.locator('input[name="username"]:visible').fill(credentials['username'])
            page.locator('input[type="password"]:visible').fill(credentials['password'])
            form = page.locator('input[name="username"]:visible').locator('xpath=ancestor::form[1]')
            form.locator('button[type="submit"],input[type="submit"]').first.click()
            page.wait_for_load_state('domcontentloaded')
            expect(page.locator('[data-total="total_matches"]')).to_be_visible()
            first = recovery.api_read('/matches?limit=1&offset=0')['items'][0]
            checked_scripts = set()
            for section in ('overview', 'matches', 'teams', 'competitions', 'analysis', 'reports', 'connections'):
                query = {'option': 'com_dragonhydra', 'section': section}
                if section in ('matches', 'analysis', 'reports'): query['match_id'] = first['id']
                page.goto('http://127.0.0.1:18740/index.php?' + urlencode(query))
                inspect(page.content().encode())
                inspect(json.dumps(page.evaluate('({local:{...localStorage}, session:{...sessionStorage}})')).encode())
                report['rendered_pages'] += 1
                for url in page.locator('script[src]').evaluate_all('(nodes)=>nodes.map(node=>node.src)'):
                    if url.startswith('http://127.0.0.1:18740/') and url not in checked_scripts:
                        inspect(context.request.get(url).body()); checked_scripts.add(url)
            report['script_resources'] = len(checked_scripts)
            browser.close()
        paths = list((ROOT / 'server/joomla').rglob('*'))
        paths += list((ROOT / 'tests/installation').glob('joomla_frontend_*'))
        paths += list((ROOT / 'docs/handover/verified-reports').glob('JOOMLA-FRONTEND-*'))
        paths += [ROOT / 'JOOMLA-FRONTEND-REPORT.md']
        for path in paths:
            if path.is_file() and path.suffix.lower() not in ('.png', '.pyc'):
                inspect(path.read_bytes()); report['source_and_report_files'] += 1
        archive((ROOT / 'dist/pkg_dragonhydra-0.4.1-dev.2.zip').read_bytes())
        for name in ('manage.php', 'README.md'):
            inspect((ROOT / 'build/joomla-frontend-20261101/web-payload' / name).read_bytes())
        report['passed'] = True
    except Exception as failure:
        report['failure_class'] = type(failure).__name__
        report['raw_error_emitted'] = False
    report['finished_at'] = datetime.now(timezone.utc).isoformat()
    output = args.output.resolve()
    assert output.parent == EVIDENCE.resolve()
    assert not output.exists()
    output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report))
    raise SystemExit(0 if report['passed'] else 1)


if __name__ == '__main__':
    main()
