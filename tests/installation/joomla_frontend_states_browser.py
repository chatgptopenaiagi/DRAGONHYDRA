"""Real-template failure/empty browser checks on an isolated fixture HTTP process."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import socket
import subprocess
import time
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / 'build/joomla-frontend-20261101/evidence/isolated-states-r1'


def main():
    OUTPUT.mkdir(exist_ok=False)
    reserve = socket.socket(); reserve.bind(('127.0.0.1', 0)); port = reserve.getsockname()[1]; reserve.close()
    command = [str(ROOT / 'build/workstation/test-install/application files/web/php/php.exe'),
               '-c', str(ROOT / 'build/workstation/test-install/state data/web-config/php.ini'),
               '-S', '127.0.0.1:' + str(port), str(ROOT / 'tests/installation/joomla_frontend_render_fixture.php')]
    report = {'schema_version': 1, 'passed': False, 'started_at': datetime.now(timezone.utc).isoformat(),
              'scope': 'Isolated actual-template fixture only; not a stopped or modified production backend',
              'production_services_modified': False, 'credentials_loaded': False, 'command': command, 'checks': [], 'page_errors': []}
    server = subprocess.Popen(command, cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                              creationflags=subprocess.CREATE_NO_WINDOW)
    try:
        deadline = time.monotonic() + 10
        while True:
            try:
                with socket.create_connection(('127.0.0.1', port), timeout=0.3): break
            except OSError:
                assert time.monotonic() < deadline and server.poll() is None
                time.sleep(0.1)
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel='msedge', headless=True)
            page = browser.new_page(viewport={'width': 1440, 'height': 1000})
            page.on('pageerror', lambda error: report['page_errors'].append(type(error).__name__))
            cases = [('empty', 'Sports intelligence,', '0'),
                     ('backend_unavailable', 'The workspace is temporarily unavailable', 'Try again'),
                     ('unavailable_record', 'The requested information is unavailable', 'Backend available'),
                     ('noanalysis', 'Analysis & predictions', 'No supported forecast is available'),
                     ('anonymous', 'Your sports.', 'Sign in to your workspace'),
                     ('permission_denied', 'This account cannot open the sports workspace', 'PERMISSION REQUIRED')]
            for scenario, heading, detail in cases:
                response = page.goto(f'http://127.0.0.1:{port}/?scenario={scenario}')
                assert response.status == 200
                expect(page.locator('.dh-workspace')).to_contain_text(heading)
                expect(page.locator('.dh-workspace')).to_contain_text(detail)
                if scenario == 'empty':
                    assert page.locator('[data-total]').all_text_contents() == ['0', '0', '0']
                screenshot = OUTPUT / (scenario + '.png')
                page.screenshot(path=str(screenshot), full_page=True)
                report['checks'].append({'name': scenario, 'status': 'PASS', 'http_status': 200,
                                         'screenshot': str(screenshot), 'sha256': hashlib.sha256(screenshot.read_bytes()).hexdigest()})
            page.set_viewport_size({'width': 390, 'height': 844})
            page.goto(f'http://127.0.0.1:{port}/?scenario=backend_unavailable')
            width = page.evaluate('({page:document.documentElement.scrollWidth, viewport:innerWidth})')
            assert width['page'] <= width['viewport'] + 1
            report['checks'].append({'name': 'mobile_failure_state_usable', 'status': 'PASS', 'width': width})
            assert not report['page_errors']
            browser.close()
        report['passed'] = True
    except Exception as failure:
        report['failure_class'] = type(failure).__name__
        report['raw_exception_emitted'] = False
    finally:
        server.terminate()
        try: server.wait(timeout=8)
        except subprocess.TimeoutExpired: server.kill(); server.wait(timeout=5)
        report['owned_fixture_process_stopped'] = True
        report['finished_at'] = datetime.now(timezone.utc).isoformat()
        (OUTPUT / 'verification.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'passed': report['passed'], 'checks': len(report['checks']), 'report': str(OUTPUT / 'verification.json')}))
    raise SystemExit(0 if report['passed'] else 1)


if __name__ == '__main__':
    main()
