"""Exercise actual public Joomla → sports → team → standings browser controls."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright, expect


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--url', required=True)
    parser.add_argument('--output', type=Path, default=Path(__file__).resolve().parents[1] / 'state/evidence/browser')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    assertions, errors, responses, checks, failed_requests, browser_warnings = [], [], [], [], [], []
    started = datetime.now(timezone.utc).isoformat()
    base = args.url.rstrip('/')
    origin = urlsplit(base).netloc
    with sync_playwright() as p:
        browser = p.chromium.launch(channel='msedge', headless=True)
        context = browser.new_context(viewport={'width': 1440, 'height': 1050}, ignore_https_errors=False)
        page = context.new_page()
        # Deliver the actual unfiltered API response slightly later. This creates
        # overlap when a user returns to the library and immediately searches,
        # without replacing any server data or fabricating a source response.
        page.add_init_script("""(() => {
          const original = window.fetch.bind(window);
          window.fetch = async (...args) => {
            const response = await original(...args);
            const url = new URL(typeof args[0] === 'string' ? args[0] : args[0].url, location.origin);
            if (url.pathname.endsWith('/matches') && !url.searchParams.get('search')) {
              await new Promise(resolve => setTimeout(resolve, 450));
            }
            return response;
          };
        })();""")
        def page_error(err):
            message = str(err)
            # Joomla's optional cross-document transition is aborted when the
            # destination sports shell has not opted in. Preserve this browser
            # diagnostic separately; it does not prevent navigation or data use.
            if message == 'Transition was aborted because of invalid state. ViewTransition opt-in disabled':
                browser_warnings.append(message)
            else:
                errors.append(message)
        page.on('pageerror', page_error)
        page.on('requestfailed', lambda request: failed_requests.append({'url': request.url, 'failure': request.failure,
            'type': request.resource_type}) if urlsplit(request.url).netloc == origin else None)
        page.on('response', lambda response: responses.append({'url': response.url, 'status': response.status,
            'type': response.request.resource_type}) if urlsplit(response.url).netloc == origin else None)
        try:
            page.goto(base + '/', wait_until='networkidle')
            expect(page.locator('.dragon-public-nav')).to_be_visible()
            expect(page.get_by_role('link', name='Browse DRAGONHYDRA matches', exact=True)).to_be_visible()
            page.screenshot(path=str(args.output / 'joomla-home.png'), full_page=True)
            styles = [r for r in responses if r['type'] == 'stylesheet']
            assert styles, 'The Joomla homepage must load actual CSS assets'
            assert all(r['status'] == 200 for r in styles), styles
            assert any('/media/' in r['url'] for r in styles), 'Joomla template CSS must load; injected gateway CSS alone is insufficient'
            failed_assets = [r for r in responses if r['type'] in ('stylesheet', 'script', 'image', 'font') and r['status'] >= 400]
            failed_assets += [r for r in failed_requests if r['type'] in ('stylesheet', 'script', 'image', 'font')]
            assert not failed_assets, failed_assets
            assertions.append('Actual Joomla homepage loaded with working stylesheet/script/image/font requests')
            page.get_by_role('link', name='Browse DRAGONHYDRA matches', exact=True).click()
            expect(page.get_by_role('heading', name='DRAGONHYDRA public matches', exact=True)).to_be_visible()
            expect(page.locator('.cards article a').first).to_be_visible(timeout=20000)
            page.screenshot(path=str(args.output / 'sports-library.png'), full_page=True)
            first = page.locator('.cards article a').first
            title, match_path = first.inner_text(), first.get_attribute('href')
            first.click()
            expect(page.get_by_role('heading', name=title, exact=True)).to_be_visible()
            expect(page.get_by_role('heading', name='Statistical model probabilities', exact=True)).to_be_visible()
            page.screenshot(path=str(args.output / 'sports-match.png'), full_page=True)
            team_link = page.locator('section a[href*="/sports/teams/"]').first
            team_name = team_link.inner_text()
            team_link.click()
            expect(page.get_by_role('heading', name=team_name, exact=True)).to_be_visible()
            expect(page.get_by_role('heading', name='Recent form', exact=True)).to_be_visible()
            page.screenshot(path=str(args.output / 'sports-team.png'), full_page=True)
            page.go_back()
            expect(page.get_by_role('heading', name=title, exact=True)).to_be_visible()
            assert urlsplit(page.url).path == urlsplit(match_path).path
            page.get_by_role('link', name='Open standings', exact=True).click()
            expect(page.get_by_role('table')).to_be_visible()
            expect(page.get_by_text('Unofficial reconstructed table', exact=False)).to_be_visible()
            page.screenshot(path=str(args.output / 'sports-standings.png'), full_page=True)
            assertions.append('Sports library → actual canonical match → team → browser return → reconstructed standings')
            page.get_by_role('link', name='← Match library', exact=True).click()
            expect(page.get_by_role('heading', name='DRAGONHYDRA public matches', exact=True)).to_be_visible()
            page.get_by_role('searchbox', name='Search teams', exact=True).fill(team_name)
            page.get_by_role('button', name='Search', exact=True).click()
            expect(page.locator('.cards article a').first).to_be_visible(timeout=20000)
            assert all(team_name in s for s in page.locator('.cards article a').all_text_contents()), 'Superseded unfiltered cards must not appear in search results'
            page.wait_for_timeout(550)
            assert all(team_name in s for s in page.locator('.cards article a').all_text_contents()), 'A late unfiltered response must not append cards after search'
            assert page.locator('.cards').count() == 1, 'The current search must own the one visible results container'
            assertions.append('A spaced team name searches through the signed API; delayed superseded responses cannot append stale cards')
            for path in ('/administrator/', '/phpmyadmin/', '/configuration.php', '/dragon/api/v1/jobs', '/dragon/api/v1/session'):
                response = page.request.get(base + path)
                checks.append({'path': path, 'status': response.status})
                assert response.status == 403, checks[-1]
            assertions.append('Public browser cannot reach administration, phpMyAdmin, configuration, jobs or sessions')
            response = page.request.post(base + '/dragon/api/v1/jobs', data={'kind': 'import_public'})
            assert response.status == 403
            assertions.append('Public state-changing command is denied')
            page.set_viewport_size({'width': 420, 'height': 900})
            page.screenshot(path=str(args.output / 'sports-narrow.png'), full_page=True)
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 2')
            assertions.append('Public sports browser remains readable in a narrow viewport')
            result = 'passed'
        except Exception as exc:
            errors.append(str(exc))
            page.screenshot(path=str(args.output / 'failure.png'), full_page=True)
            result = 'failed'
        finally:
            context.close()
            browser.close()
    evidence = {'started_at': started, 'finished_at': datetime.now(timezone.utc).isoformat(), 'url': base,
        'browser': 'Installed Microsoft Edge via Playwright', 'status': result, 'assertions': assertions,
        'latency_probe': 'Actual unfiltered API responses delayed 450ms in browser to exercise overlapping navigation/search; no data replaced',
        'page_errors': errors, 'browser_warnings': browser_warnings, 'responses': responses, 'failed_requests': failed_requests, 'blocked_route_checks': checks,
        'not_run': ['Native packaged application', 'External VPS deployment unless this URL is its actual endpoint']}
    path = args.output / 'journey.json'
    path.write_text(json.dumps(evidence, indent=2), encoding='utf-8')
    print(json.dumps({'status': result, 'assertions': len(assertions), 'page_errors': errors, 'evidence': str(path)}, indent=2))
    return 0 if result == 'passed' and not errors else 1


if __name__ == '__main__':
    raise SystemExit(main())
