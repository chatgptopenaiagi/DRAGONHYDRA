"""Desktop opener wiring and real injected-click regression, without a browser.

Native browser delivery is verified separately in the Windows client. These
tests execute the pinned plugin's actual injected JS and the dashboard's real
link helpers; neither the application nor a provider service is launched.
"""
import ast
import json
import os
from pathlib import Path
import shutil
import subprocess
import tomllib
import unittest


ROOT = Path(__file__).resolve().parents[1]
TAURI = ROOT / 'client/desktop/src-tauri'
VERSION = '2.7.2'


class DesktopExternalLinkTests(unittest.TestCase):
    def test_native_opener_is_pinned_and_initialized(self):
        cargo = tomllib.loads((TAURI / 'Cargo.toml').read_text())
        self.assertEqual(cargo['dependencies']['tauri-plugin-opener'], '=' + VERSION)
        lock = tomllib.loads((TAURI / 'Cargo.lock').read_text())
        installed = [p for p in lock['package'] if p['name'] == 'tauri-plugin-opener']
        self.assertEqual([p['version'] for p in installed], [VERSION])
        self.assertIn('.plugin(tauri_plugin_opener::init())', (TAURI / 'src/main.rs').read_text())

    def test_permission_is_only_web_urls_from_main_loopback_dashboard(self):
        config = json.loads((TAURI / 'tauri.conf.json').read_text())
        self.assertEqual(config['app']['security']['capabilities'], ['external-browser'])
        capability = json.loads((TAURI / 'capabilities/external-browser.json').read_text())
        self.assertEqual(capability['windows'], ['main'])
        self.assertEqual(capability['remote']['urls'], ['http://127.0.0.1:*'])
        self.assertEqual(capability['permissions'], [{
            'identifier': 'opener:allow-open-url',
            'allow': [{'url': 'https://*'}, {'url': 'http://*'}],
        }])
        # Omitting the scope's `app` property permits only the OS default;
        # no arbitrary application, path, reveal-file or shell command is granted.

    def test_provider_clicks_dispatch_actual_plugin_and_preserve_application(self):
        cargo_home = Path(os.environ.get('CARGO_HOME', Path.home() / '.cargo'))
        matches = list((cargo_home / 'registry/src').glob(
            '*/tauri-plugin-opener-' + VERSION + '/src/init-iife.js'))
        if len(matches) != 1:
            self.skipTest('Fetch the pinned desktop Cargo dependencies to run injected JS regression')
        node = shutil.which('node')
        if not node:
            self.skipTest('Installed Node.js is required for injected JS regression')
        canonical = ROOT / 'src/dragonhydra/resources/web/app.js'
        mirror = ROOT / 'client/desktop/web/app.js'
        self.assertEqual(canonical.read_bytes(), mirror.read_bytes())
        tree = ast.parse((ROOT / 'src/dragonhydra/jobs.py').read_text())
        targets = next(ast.literal_eval(n.value) for n in tree.body
                       if isinstance(n, ast.Assign)
                       and any(isinstance(t, ast.Name) and t.id == 'TARGETS' for t in n.targets))
        providers = {p[0]: p[2] for p in targets
                     if p[0] in ('api-football', 'the-odds-api', 'sportmonks')}
        self.assertEqual(len(providers), 3)
        script = r'''
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
class Node {
  constructor(tag) { this.nodeName = tag.toUpperCase(); this.children = []; }
  setAttribute(key, value) { this[key] = value; }
  addEventListener() {}
  append(child) { this.children.push(child); }
}
const listeners = {}, calls = [];
const location = {origin: 'http://127.0.0.1:18746', href: 'http://127.0.0.1:18746/#connections'};
const document = {createElement: tag => new Node(tag), createTextNode: text => ({text})};
const window = {
  addEventListener: (type, callback) => {listeners[type] = callback;},
  __TAURI_INTERNALS__: {invoke: (command, args) => {calls.push({command, url: String(args.url)}); return Promise.resolve();}}
};
const context = vm.createContext({Node, document, window, location, URL});
const app = fs.readFileSync(input.dashboard, 'utf8');
// Load the real child normalizer used by el as well; the complete application
// already defines it before el. Omitting that dependency is a harness failure.
const helpers = ['contentNodes', 'el', 'safeUrl', 'link'].map(name => {
  const line = app.split('\n').find(line => line.startsWith('function ' + name + '('));
  assert.ok(line, 'Actual dashboard helper missing: ' + name);
  return line;
}).join('\n');
vm.runInContext(helpers, context);
vm.runInContext(fs.readFileSync(input.plugin, 'utf8'), context);
assert.equal(typeof listeners.click, 'function', 'Pinned opener did not install click handler');
for (const [provider, url] of Object.entries(input.providers)) {
  context.testUrl = url;
  const anchor = vm.runInContext('link("Register / get API key ↗", testUrl)', context);
  assert.equal(anchor.nodeName, 'A');
  assert.equal(anchor.target, '_blank');
  assert.equal(anchor.rel, 'noopener noreferrer');
  const event = {defaultPrevented: false, button: 0, metaKey: false, altKey: false,
    ctrlKey: false, shiftKey: false, composedPath: () => [new Node('span'), anchor],
    preventDefault() {this.defaultPrevented = true;}};
  const before = calls.length;
  listeners.click(event);
  assert.equal(event.defaultPrevented, true, provider + ': app navigation was not prevented');
  assert.equal(calls.length, before + 1, provider + ': default-browser dispatch missing/duplicated');
  assert.equal(calls.at(-1).command, 'plugin:opener|open_url');
  assert.equal(calls.at(-1).url, url);
  assert.equal(location.href, 'http://127.0.0.1:18746/#connections');
}
for (const invalid of ['javascript:alert(1)', 'file:///C:/Windows/notepad.exe', 'data:text/html,bad', 'cmd:calc', 'mailto:a@example.test']) {
  context.testUrl = invalid;
  const element = vm.runInContext('link("invalid", testUrl)', context);
  assert.equal(element.nodeName, 'SPAN', 'Unsupported scheme became an executable link: ' + invalid);
}
// Capability remote origins follow URLPattern. Exercise the same standardized
// pattern against an owned origin and unrelated web/file origins.
const pattern = new URLPattern('http://127.0.0.1:*');
assert.equal(pattern.test(location.href), true);
for (const denied of ['https://example.test/', 'http://localhost:18746/', 'http://127.0.0.2:18746/', 'file:///C:/test']) {
  assert.equal(pattern.test(denied), false, 'Unrelated origin matched loopback capability: ' + denied);
}
console.log(JSON.stringify({provider_clicks: Object.keys(input.providers).length, calls,
  rejected_schemes: 5, unrelated_origins_rejected: 4, app_url_unchanged: true}));
'''
        result = subprocess.run([node, '-e', script], input=json.dumps({
            'dashboard': str(mirror), 'plugin': str(matches[0]), 'providers': providers,
        }), text=True, capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        evidence = json.loads(result.stdout)
        self.assertEqual(evidence['provider_clicks'], 3)
        self.assertTrue(evidence['app_url_unchanged'])


if __name__ == '__main__':
    unittest.main()
