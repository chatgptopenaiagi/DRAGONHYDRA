"""Verify optional local-model controls and real structured-package downloads.

Uses the running source server, real durable jobs and retained evidence. No
model responses are mocked and this script never starts or stops a server.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import sys
import time
import traceback
from urllib.parse import urlsplit

from playwright.sync_api import expect, sync_playwright


ROOT = Path(__file__).resolve().parents[2]
API = '/dragon/api/v1'


def run():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', required=True)
    parser.add_argument('--state', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--expect-local', choices=('not-configured', 'accepted'), default='not-configured')
    args = parser.parse_args()
    if sys.flags.optimize:
        raise RuntimeError('Run this verification with assertions enabled.')
    origin = args.url.rstrip('/')
    parsed = urlsplit(origin)
    assert parsed.scheme == 'http' and parsed.hostname == '127.0.0.1'
    assert not parsed.username and not parsed.password and parsed.path in ('', '/')
    assert not parsed.query and not parsed.fragment
    state, output = args.state.resolve(), args.output.resolve()
    assert state.is_relative_to(ROOT) and output.is_relative_to(ROOT)
    assert output.is_relative_to(ROOT/'build/connections/evidence') or output.is_relative_to(ROOT/'runtime/evidence')
    assert not (output/'journey.json').exists(), 'Choose a fresh evidence directory.'
    output.mkdir(parents=True, exist_ok=True)
    session = state/'client/local-session.json'
    if not session.exists():
        session = state/'local-session.json'
    token = json.loads(session.read_text(encoding='utf-8-sig'))['token']
    assert isinstance(token, str) and len(token) >= 20

    def safe(value):
        return str(value).replace(token, '[REDACTED]')

    groups, page_errors, console_errors, http_errors = [], [], [], []
    record = {'schema_version': 1, 'started_at': datetime.now(timezone.utc).isoformat(),
              'passed': False, 'url': origin, 'groups': groups, 'expected_local': args.expect_local,
              'browser': 'Installed Microsoft Edge / Playwright',
              'environment': {'os': platform.platform(), 'python': platform.python_version()},
              'scope': 'Source dashboard, actual durable jobs, retained evidence and JSON download; no native package claim',
              'page_errors': page_errors, 'console_errors': console_errors, 'http_errors': http_errors,
              'server_lifecycle_operations': False, 'mocked_model_output': False}

    def passed(name, **details):
        groups.append({'name': name, 'passed': True, **details})
        print(json.dumps({'passed': name}), flush=True)

    def monitor(target):
        target.on('pageerror', lambda error: page_errors.append(safe(error)))
        target.on('console', lambda message: console_errors.append(safe(message.text)) if message.type == 'error' else None)
        target.on('response', lambda response: http_errors.append({'url': safe(response.url), 'status': response.status}) if response.status >= 400 else None)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel='msedge', headless=True)
        context = browser.new_context(viewport={'width': 1500, 'height': 1100}, accept_downloads=True, reduced_motion='reduce')
        context.on('page', monitor)
        page = context.new_page()

        def api(path):
            response = context.request.get(origin+API+path, timeout=15000)
            assert response.status == 200, f'API returned HTTP {response.status}'
            return response.json()

        def explain(match_id, *, local=False):
            endpoint = '/local-explanations' if local else '/explanations'
            path = origin+API+'/matches/'+match_id+endpoint
            with page.expect_response(lambda response: response.url == path and response.request.method == 'POST', timeout=30000) as created:
                page.get_by_role('button', name='Use local model' if local else 'Explain this match', exact=True).click()
            assert created.value.status == 202
            identifier = created.value.json()['id']
            deadline = time.monotonic()+100
            while time.monotonic() < deadline:
                job = api('/jobs/'+identifier)
                if job['status'] in ('succeeded', 'failed', 'cancelled', 'interrupted'):
                    assert job['status'] == 'succeeded', safe(job.get('error'))
                    expect(page.locator('.job-progress')).to_have_count(0, timeout=30000)
                    return job
                time.sleep(.2)
            raise AssertionError('Explanation job did not finish within the verification deadline.')

        try:
            page.goto(origin+'/#token='+token, wait_until='domcontentloaded')
            expect(page.get_by_role('heading', name='Today’s football')).to_be_visible(timeout=30000)
            assert '#token=' not in page.url
            matches = api('/matches?provider=statsbomb&limit=1')['items']
            if not matches:
                matches = api('/matches?limit=1')['items']
            assert matches, 'A retained football match is required.'
            match_id = matches[0]['id']
            page.goto(origin+'/#match/'+match_id, wait_until='domcontentloaded')
            page.get_by_role('tab', name='Analysis', exact=True).click()
            expect(page.get_by_role('heading', name='Investigate the evidence')).to_be_visible()
            for name in ('Explain this match', 'Use local model', 'Export sports package'):
                expect(page.get_by_role('button', name=name, exact=True)).to_be_enabled()
            expect(page.get_by_text('The optional local model selects one supplied source fact;', exact=False)).to_be_visible()
            passed('Analysis preserves the default action and explains optional local-model scope', match_id=match_id)

            default = explain(match_id)
            assert default['kind'] == 'explanation' and default['result']['kind'] == 'deterministic'
            assert 'local_ai' not in default['result']
            target = page.locator('#explanation-result')
            expect(target.locator('.badge')).to_have_text('DETERMINISTIC EVIDENCE SUMMARY')
            expect(target.locator('.local-ai-diagnostic')).to_have_count(0)
            passed('Default explanation remains deterministic and never requests local inference', job_id=default['id'])

            with page.expect_download(timeout=30000) as downloaded:
                page.get_by_role('button', name='Export sports package', exact=True).click()
            download = downloaded.value
            assert download.suggested_filename == 'dragonhydra-sports-'+match_id[:12]+'.json'
            saved = output/download.suggested_filename
            download.save_as(str(saved))
            assert download.failure() is None
            package = json.loads(saved.read_text(encoding='utf-8'))
            assert package['schema_version'] == 'sports-evidence-package/2'
            assert package['event']['id'] == match_id
            canonical = json.dumps({key: value for key, value in package.items() if key != 'package_sha256'},
                                   ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(',', ':')).encode('utf-8')
            assert hashlib.sha256(canonical).hexdigest() == package['package_sha256']
            assert package == api('/matches/'+match_id+'/analysis-package')
            cited = package['evidence']['E1']
            evidence = api('/evidence/'+cited['id'])
            assert cited['source_sha256'] == (evidence.get('source_hash') or evidence.get('raw_sha256'))
            passed('Actual JSON download preserves the selected match, source evidence and independently recomputed package hash',
                   filename=download.suggested_filename, bytes=saved.stat().st_size,
                   package_sha256=package['package_sha256'], evidence_id=cited['id'])

            local = explain(match_id, local=True)
            result = local['result']
            assert local['kind'] == 'local_explanation'
            assert result['package_sha256'] == package['package_sha256']
            if args.expect_local == 'not-configured':
                assert result['kind'] == 'deterministic'
                assert result['local_ai']['code'] == 'AI_NOT_CONFIGURED'
                assert result['local_ai']['requested'] and not result['local_ai']['accepted']
                expect(target.locator('.badge')).to_have_text('DETERMINISTIC EVIDENCE SUMMARY')
                expect(target.locator('.local-ai-diagnostic')).to_contain_text('AI_NOT_CONFIGURED')
                expect(target.locator('.local-ai-diagnostic')).to_contain_text(result['local_ai']['message'])
                expect(target.locator('.local-ai-diagnostic')).to_contain_text('Check the offline model setup on this server')
                passed('Unconfigured local model returns an actionable deterministic fallback through a real job', job_id=local['id'])
            else:
                assert result['kind'] == 'local_llm' and result['mode'] == 'constrained_source_fact_selection'
                assert result['local_ai']['requested'] and result['local_ai']['accepted']
                assert len(result['observations']) == 1 and result['observations'][0] in package['allowed_observations']
                expect(target.locator('.badge')).to_have_text('LOCAL MODEL · SOURCE FACT SELECTION')
                expect(target.locator('.local-ai-diagnostic')).to_have_count(0)
                expect(target).to_contain_text(result['observations'][0])
                passed('Real local model selects one supplied fact with its limited scope labelled explicitly', job_id=local['id'])
            assert result['evidence'][0]['id'] == cited['id']
            with page.expect_popup() as opened:
                target.locator('.explanation-citation').first.click()
            citation = opened.value
            citation.wait_for_url(origin+API+'/evidence/'+cited['id'], timeout=15000)
            citation.wait_for_load_state('domcontentloaded')
            assert citation.url == origin+API+'/evidence/'+cited['id']
            citation.close()
            page.screenshot(path=str(output/'analysis-local-model.png'), full_page=True)
            passed('Explanation citation opens the actual retained evidence for the exported package')

            repeated = explain(match_id)
            assert repeated['result']['kind'] == 'deterministic' and 'local_ai' not in repeated['result']
            expect(target.locator('.local-ai-diagnostic')).to_have_count(0)
            expect(target.locator('.badge')).to_have_text('DETERMINISTIC EVIDENCE SUMMARY')
            page.get_by_role('link', name='Connections', exact=True).click()
            expect(page.get_by_role('heading', name='Connections', exact=True)).to_be_visible()
            page.get_by_role('link', name='Analysis', exact=True).click()
            expect(page.get_by_role('heading', name='Investigate the evidence')).to_be_visible()
            expect(page.get_by_role('button', name='Export sports package', exact=True)).to_be_enabled()
            passed('Default explanation can be repeated and selected-match navigation remains working')
            assert not page_errors, safe(page_errors)
            assert not console_errors, safe(console_errors)
            assert not http_errors, safe(http_errors)
            record['passed'] = True
        except Exception as error:
            record['error'] = safe(f'{type(error).__name__}: {error}')
            record['traceback'] = safe(traceback.format_exc())
            try:
                page.screenshot(path=str(output/'failure.png'), full_page=True)
            except Exception as capture:
                record['capture_error'] = safe(capture)
        finally:
            record['finished_at'] = datetime.now(timezone.utc).isoformat()
            record['unique_group_count'] = len(groups)
            context.close()
            browser.close()
            (output/'journey.json').write_text(safe(json.dumps(record, indent=2, ensure_ascii=False)), encoding='utf-8')
    print(json.dumps({'passed': record['passed'], 'groups': len(groups), 'error': record.get('error'),
                      'evidence': str(output/'journey.json')}, indent=2))
    return 0 if record['passed'] else 1


if __name__ == '__main__':
    sys.exit(run())
