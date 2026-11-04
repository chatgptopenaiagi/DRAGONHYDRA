"""All-provider regression using the actual dashboard and pinned opener code."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('a8_provider_links', ROOT/'tests/installation/genesis_a8_links.py')
links = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(links)


class A8ProviderLinksTests(unittest.TestCase):
    def test_complete_rendered_registry_is_https_without_credentials(self):
        inventory = links.inventory()
        self.assertEqual(inventory['connection_link_count'], 10)
        self.assertEqual({item['id'] for item in inventory['providers']}, links.EXPECTED_PROVIDERS)
        self.assertEqual(inventory['provider_account_management_links'], [])
        self.assertEqual(len(inventory['adapter_documentation_metadata']), 9)
        for item in inventory['providers']:
            self.assertEqual(links.ensure_public_https(item['url']), item['url'])

    def test_unreviewed_credentials_and_non_https_destinations_are_rejected(self):
        for url in ('http://example.test/', 'https://secret@example.test/',
                    'https://user:password@example.test/',
                    'https://example.test/?api_key=secret', 'https://example.test/#token=secret',
                    'javascript:alert(1)', 'file:///C:/private'):
            with self.subTest(url=url), self.assertRaises(AssertionError):
                links.ensure_public_https(url)

    def test_all_ten_actual_dashboard_links_use_real_opener_and_retain_route(self):
        node = shutil.which('node')
        cargo = Path(os.environ.get('CARGO_HOME', Path.home()/'.cargo'))
        matches = list((cargo/'registry/src').glob('*/tauri-plugin-opener-2.7.2/src/init-iife.js'))
        if not node or len(matches) != 1:
            self.skipTest('Use installed Node and the already-pinned opener Cargo cache')
        canonical = ROOT/'src/dragonhydra/resources/web/app.js'
        mirror = ROOT/'client/desktop/web/app.js'
        self.assertEqual(canonical.read_bytes(), mirror.read_bytes())
        script = r'''
const fs=require('node:fs'), vm=require('node:vm'), assert=require('node:assert/strict');
const input=JSON.parse(fs.readFileSync(0,'utf8'));
class Node {constructor(tag){this.nodeName=tag.toUpperCase();this.children=[];} setAttribute(k,v){this[k]=v;}addEventListener(){}append(n){this.children.push(n);}}
const listeners={},calls=[];
const document={createElement:t=>new Node(t),createTextNode:t=>({text:t})};
const location={origin:'http://127.0.0.1:19000',href:'http://127.0.0.1:19000/#connections'};
const window={addEventListener:(k,f)=>listeners[k]=f,__TAURI_INTERNALS__:{invoke:(cmd,args)=>{calls.push({cmd,url:String(args.url)});return Promise.resolve();}}};
const context=vm.createContext({Node,document,location,window,URL});
const app=fs.readFileSync(input.dashboard,'utf8');
const helpers=['contentNodes','el','safeUrl','link'].map(name=>{const line=app.split('\n').find(x=>x.startsWith('function '+name+'('));assert.ok(line);return line;}).join('\n');
vm.runInContext(helpers,context);vm.runInContext(fs.readFileSync(input.plugin,'utf8'),context);
for(const provider of input.providers){
 context.destination=provider.url;context.label=provider.rendered_label;
 const a=vm.runInContext('link(label,destination)',context);
 assert.equal(a.nodeName,'A');assert.equal(a.href,provider.url);assert.equal(a.target,'_blank');
 assert.ok(a.rel.includes('noreferrer'));assert.ok(a.rel.includes('noopener'));
 const event={defaultPrevented:false,button:0,metaKey:false,altKey:false,ctrlKey:false,shiftKey:false,composedPath:()=>[new Node('span'),a],preventDefault(){this.defaultPrevented=true;}};
 const previous=calls.length;listeners.click(event);
 assert.equal(event.defaultPrevented,true);assert.equal(calls.length,previous+1);
 assert.equal(calls.at(-1).cmd,'plugin:opener|open_url');assert.equal(calls.at(-1).url,provider.url);
 assert.equal(location.href,'http://127.0.0.1:19000/#connections');
}
console.log(JSON.stringify({passed:true,providers:calls.length,route_unchanged:true}));
'''
        result = subprocess.run([node, '-e', script], input=json.dumps({
            'dashboard': str(mirror), 'plugin': str(matches[0]),
            'providers': links.inventory()['providers']}), capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), {'passed': True, 'providers': 10, 'route_unchanged': True})


if __name__ == '__main__':
    unittest.main()
