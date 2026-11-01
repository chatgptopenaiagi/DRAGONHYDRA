"""Complete provider-link inventory and real native-page acceptance for A8.

The coordinator supplies an already paired, owned Tauri page. This module does
not launch clients, retrieve provider data, change settings, or create accounts.
Default-browser window receipts reuse the previous verified Windows inspection.
"""
from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import time
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[2]
API = '/dragon/api/v1'
EXPECTED_PROVIDERS = frozenset((
    'api-football', 'the-odds-api', 'sportmonks', 'football-data-org',
    'football-data-couk', 'openfootball', 'statsbomb', 'nflverse', 'moneypuck',
    'cricsheet',
))
TITLE_PATTERNS = {
    'api-football': re.compile(r'API[- ]Football|API[- ]SPORTS|api-football\.com', re.I),
    'the-odds-api': re.compile(r'The Odds API|Odds API|the-odds-api\.com', re.I),
    'sportmonks': re.compile(r'Sportmonks|Fixtures.*API 3\.0|Fixtures.*Football API', re.I),
    'football-data-org': re.compile(r'football-data\.org|Football Data API', re.I),
    'football-data-couk': re.compile(r'football[- ]data\.co\.uk|Football Data|Football Results', re.I),
    'openfootball': re.compile(r'openfootball[/ :].*football\.json|football\.json.*openfootball', re.I),
    'statsbomb': re.compile(r'(statsbomb|hudl)[/ :].*open-data|open-data.*(statsbomb|hudl)', re.I),
    'nflverse': re.compile(r'nflverse[/ :].*nflverse-data|nflverse-data.*nflverse', re.I),
    'moneypuck': re.compile(r'MoneyPuck|moneypuck\.com', re.I),
    'cricsheet': re.compile(r'Cricsheet|cricsheet\.org', re.I),
}


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False,
                      separators=(',', ':'), allow_nan=False).encode()


def ensure_public_https(url):
    """Only the existing public, credential-free provider destinations qualify."""
    parsed = urlsplit(url)
    if (parsed.scheme != 'https' or not parsed.hostname or parsed.username
            or parsed.password or parsed.query or parsed.fragment):
        raise AssertionError('Provider destination must be public HTTPS without credentials, query, or fragment')
    return url


def literal_assignment(path, variable):
    tree = ast.parse(Path(path).read_text(encoding='utf-8'))
    for entry in tree.body:
        if isinstance(entry, ast.Assign) and any(
                isinstance(target, ast.Name) and target.id == variable
                for target in entry.targets):
            return ast.literal_eval(entry.value)
    raise AssertionError('Registry assignment missing: '+variable)


def inventory():
    targets = literal_assignment(ROOT/'src/dragonhydra/jobs.py', 'TARGETS')
    providers = [{'id': key, 'name': name, 'url': ensure_public_https(url),
                  'authentication': auth,
                  'rendered_label': 'Source documentation ↗' if auth == 'none'
                                    else 'Register / get API key ↗'}
                 for key, name, url, auth in targets]
    if {item['id'] for item in providers} != EXPECTED_PROVIDERS:
        raise AssertionError('Update A8 coverage for the changed provider registry')
    specifications = {}
    for name in ('football', 'research', 'multisport'):
        specifications.update(literal_assignment(
            ROOT/f'src/dragonhydra/connectors/{name}.py', 'SPECS'))
    adapter_docs = [{'provider': key, 'url': ensure_public_https(spec['documentation_url']),
                     'separately_rendered_in_connections': False}
                    for key, spec in sorted(specifications.items())]
    return {
        'providers': providers,
        'connection_link_count': len(providers),
        'adapter_documentation_metadata': adapter_docs,
        'provider_account_management_links': [],
        'account_management_scope': 'No separate provider account-management links are exposed by the current dashboard.',
        'other_link_surfaces': ['Retained source provenance links',
                                'Local Joomla Administration window.open action',
                                'Authenticated same-window export downloads'],
    }


def settings_fingerprint(data):
    # The API returns only credential presence, never a stored API-key value.
    values = [{key: item.get(key) for key in
               ('id', 'config', 'interval_seconds', 'credential_configured')}
              for item in data['items']]
    values.sort(key=lambda item: item['id'])
    return hashlib.sha256(canonical(values)).hexdigest()


def load_windows_helpers():
    spec = importlib.util.spec_from_file_location(
        'a8_verified_browser_receipts', ROOT/'tests/installation/desktop_external_links.py')
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def verify_connection_links(page, windows, report, *, process=None, browser=None,
                            timeout_seconds=25, on_check=None):
    """Click all actual rendered provider links in an already owned native page.

    The caller has proved the page belongs to its launched Tauri process and is
    responsible for cleanup. ``process`` is optional and is only polled, never
    terminated. ``report`` receives independent evidence under ``external_links``.
    This creates ten normal provider tabs in the registered default browser.
    """
    helpers = load_windows_helpers()
    browser = browser or helpers.default_browser()
    evidence = {'passed': False, 'default_browser': browser,
                'harness_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                'inventory': inventory(), 'checks': [],
                'provider_api_requests_requested': False,
                'credential_or_settings_writes_requested': False}
    report['external_links'] = evidence
    page.get_by_role('link', name='Connections', exact=True).click()
    page.locator('[data-provider="api-football"]').wait_for(state='visible')
    original_route = page.url
    if '#connections' not in original_route:
        raise AssertionError('Connections route is not active')
    before = page.evaluate("async()=>await (await fetch('/dragon/api/v1/connections')).json()")
    by_id = {item['id']: item for item in before['items']}
    if set(by_id) != EXPECTED_PROVIDERS:
        raise AssertionError('Installed registry differs from the inventoried ten providers')
    expected = {item['id']: item for item in evidence['inventory']['providers']}
    for key, item in by_id.items():
        if ensure_public_https(item['registration_url']) != expected[key]['url']:
            raise AssertionError('Installed provider destination differs: '+key)
        if item.get('account_management_url') or item.get('account_url'):
            raise AssertionError('New account-management links require explicit inventory and coverage')
    actual_anchors = page.locator('[data-provider] a[href]').evaluate_all(
        '(nodes)=>nodes.map(a=>({provider:a.closest("[data-provider]").dataset.provider, href:a.href, target:a.target, rel:a.rel}))')
    if len(actual_anchors) != len(expected):
        raise AssertionError('A rendered provider link is missing or not inventoried')
    for anchor in actual_anchors:
        if (anchor['href'] != expected[anchor['provider']]['url']
                or anchor['target'] != '_blank'
                or 'noreferrer' not in anchor['rel'] or 'noopener' not in anchor['rel']):
            raise AssertionError('Rendered provider link is not a credential-free external URL')
    cdp = page.context.new_cdp_session(page)
    listeners = cdp.send('Runtime.evaluate', {
        'expression': 'getEventListeners(window).click.map(e=>String(e.listener))',
        'includeCommandLineAPI': True, 'returnByValue': True})['result'].get('value', [])
    if not any('plugin:opener|open_url' in listener for listener in listeners):
        raise AssertionError('The real native opener click handler is absent')
    page.evaluate("""()=>{
      window.__dragonA8Links=[];
      window.addEventListener('click', event=>{
        const a=event.composedPath().find(n=>n instanceof Node&&n.nodeName==='A');
        if(a?.target==='_blank') window.__dragonA8Links.push({url:a.href,defaultPrevented:event.defaultPrevented});
      });
    }""")
    evidence['settings_before_sha256'] = settings_fingerprint(before)
    evidence['record_counts_before'] = {key: item['record_count'] for key,item in by_id.items()}
    for item in evidence['inventory']['providers']:
        provider, url = item['id'], item['url']
        link = page.locator(f'[data-provider="{provider}"]').get_by_role(
            'link', name=item['rendered_label'], exact=True)
        if link.get_attribute('href') != url:
            raise AssertionError('Provider URL changed before click: '+provider)
        previous = helpers.browser_window_receipts(windows, browser, TITLE_PATTERNS[provider])
        link.click()  # Normal, unmodified mouse click in the real native WebView.
        deadline = time.monotonic()+timeout_seconds
        receipts, events = [], []
        while time.monotonic() < deadline:
            events = [event for event in page.evaluate('window.__dragonA8Links')
                      if event['url'] == url]
            receipts = helpers.browser_window_receipts(windows, browser, TITLE_PATTERNS[provider])
            if receipts and receipts != previous:
                break
            page.wait_for_timeout(100)
        if not events or not events[-1]['defaultPrevented']:
            raise AssertionError('Native opener did not handle the real click: '+provider)
        if not receipts or receipts == previous:
            raise AssertionError('No new registered-default-browser provider window receipt: '+provider)
        if page.url != original_route or (process is not None and process.poll() is not None):
            raise AssertionError('Native application navigated or closed: '+provider)
        result = {'provider': provider, 'expected_url': url,
                  'click_default_prevented_by_native_opener': True,
                  'default_browser_windows_before': previous,
                  'default_browser_window_receipts': receipts,
                  'application_route_unchanged': True, 'application_still_open': True}
        evidence['checks'].append(result)
        if on_check is not None:
            on_check('external_link_'+provider, result)
    after = page.evaluate("async()=>await (await fetch('/dragon/api/v1/connections')).json()")
    evidence['settings_after_sha256'] = settings_fingerprint(after)
    evidence['record_counts_after'] = {item['id']: item['record_count'] for item in after['items']}
    if (evidence['settings_before_sha256'] != evidence['settings_after_sha256']
            or evidence['record_counts_before'] != evidence['record_counts_after']):
        raise AssertionError('Connection settings or retained records changed during link checks')
    evidence.update(passed=True, official_opener_click_handler_present=True,
                    normal_native_mouse_clicks=len(evidence['checks']),
                    connection_settings_and_counts_unchanged=True,
                    browser_evidence_scope='Exact native clicked URLs plus registered default-browser title receipts; address bars are a separate visual check')
    return evidence


if __name__ == '__main__':
    print(json.dumps(inventory(), indent=2))
