"""Source mirrors, strict public UI contracts and a disposable Node DOM probe."""
import json
from pathlib import Path
import subprocess
import unittest

ROOT=Path(__file__).absolute().parents[1]
NODE=Path(r'C:\Program Files\nodejs\node.exe')


class FutureWebTests(unittest.TestCase):
    def setUp(self): self.script=(ROOT/'client/desktop/web/future.js').read_text(encoding='utf-8')

    def test_training_has_bounded_longer_timeout_without_automatic_replay(self):
        app=(ROOT/'client/desktop/web/app.js').read_text(encoding='utf-8')
        function=next(line for line in app.splitlines() if line.startswith('async function request('))
        probe=r'''
const vm=require('node:vm'),assert=require('node:assert/strict');
const waits=[],cleared=[];let calls=0,fail=false;
const sandbox={API:'/dragon/api/v1',AbortController,setTimeout:(fn,ms)=>{waits.push(ms);return waits.length;},clearTimeout:id=>cleared.push(id),state:{},showLogin(){},fetch:async()=>{calls++;if(fail){const e=new Error('virtual timeout');e.name='AbortError';throw e;}return {ok:true,json:async()=>({synthetic:true})};}};
vm.createContext(sandbox);vm.runInContext(FUNCTION+';this.request=request;',sandbox);
(async()=>{await sandbox.request('/future/training');await sandbox.request('/future/status');assert.deepEqual(waits,[300000,20000]);fail=true;await assert.rejects(sandbox.request('/future/training'),/Refresh retained experiment results/);assert.equal(calls,3);assert.equal(cleared.length,3);})().catch(e=>{console.error(e);process.exitCode=1;});
'''.replace('FUNCTION',json.dumps(function))
        # Execute the real request helper with fake timers and no network.
        result=subprocess.run([str(NODE),'-e',probe],capture_output=True,text=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)

    def test_exact_local_mirrors_and_additive_navigation(self):
        for name in ('future.js','future.css','app.js','index.html'):
            self.assertEqual((ROOT/'client/desktop/web'/name).read_bytes(),(ROOT/'src/dragonhydra/resources/web'/name).read_bytes())
        app=(ROOT/'client/desktop/web/app.js').read_text(encoding='utf-8')
        html=(ROOT/'client/desktop/web/index.html').read_text(encoding='utf-8')
        self.assertIn('DragonRealtime.view({request})',app)
        self.assertIn('DragonFuture.view({request})',app)
        self.assertIn('Future relevance research',app)
        self.assertIn('./future.js',html);self.assertIn('./future.css',html)
        self.assertIn('./realtime.js',html)
        self.assertNotIn('https://',html)

    def test_virtual_disclosures_and_public_only_data_binding(self):
        for text in ('SYNTHETIC FUTURE RELEVANCE ONLY','not calibrated real-world value','No external API calls',
                     'value?.synthetic !== true','current_forecast','e?.estimates','s.acquired','s.candidates',
                     'policy_comparison','evaluations','snapshot?.revision','available_at','budget_remaining'):
            self.assertIn(text,self.script)
        self.assertIn('family.?rules',self.script)
        self.assertNotIn('innerHTML',self.script)
        self.assertNotIn('eval(',self.script)
        self.assertNotIn('localStorage',self.script)
        self.assertNotIn('Authorization',self.script)
        self.assertNotIn('fetch(',self.script)
        self.assertNotIn('http://',self.script)

    def test_targets_policies_time_and_revision_actions_are_explicit(self):
        for text in ('GOAL_OCCURRENCE','FULL_TIME_RESULT','NEXT_GOAL_SIDE','REMAINING_GOALS',
                     'possession_inverse','late_card_interaction','acquire_all','acquire_none','random','handcrafted','learned',
                     'model.target === "FULL_TIME_RESULT" ? ["FULL_TIME"]','crypto.randomUUID()',
                     'expected_revision','/decisions','/advance','/training','Before acquisition','After acquisition',
                     'Acquisition cost','Computation cost','Paired net utility improvement vs none',
                     'brier_score','mean_acquisition_cost','paired_vs_acquire_none'):
            self.assertIn(text,self.script)
        self.assertNotIn('setInterval(',self.script)
        self.assertNotIn('setTimeout(',self.script)

    @unittest.skipUnless(NODE.is_file(),'Existing verified Node runtime required')
    def test_existing_node_parses_assets(self):
        for name in ('future.js','app.js'):
            result=subprocess.run([str(NODE),'--check',str(ROOT/'client/desktop/web'/name)],capture_output=True,text=True,timeout=15)
            self.assertEqual(result.returncode,0,result.stderr)

    @unittest.skipUnless(NODE.is_file(),'Existing verified Node runtime required')
    def test_passive_navigation_and_revision_bound_explicit_action_dom_probe(self):
        probe=r'''
const fs=require('fs'),vm=require('vm'),assert=require('assert');
class N {constructor(tag,text=''){this.tag=tag;this.text=text;this.children=[];this.attrs={};this.handlers={};}append(...x){this.children.push(...x);}replaceChildren(...x){this.children=x;}setAttribute(k,v){this.attrs[k]=v;}addEventListener(k,v){this.handlers[k]=v;}contains(){return false;}}
global.Node=N;global.window={};global.document={activeElement:null,createElement:t=>new N(t),createTextNode:t=>new N('#text',t),getElementById:()=>null};
global.crypto=require('crypto').webcrypto;
vm.runInThisContext(fs.readFileSync(process.argv[1],'utf8'));
const calls=[],episode='future-fixture-episode';let created=false;
const snapshot={synthetic:true,episode_id:episode,snapshot:{revision:3,now_minute:60,acquired:{},candidates:[]},current_forecast:{target:'GOAL_OCCURRENCE',horizon:'10',probabilities:{goal:0.25,no_goal:0.75}},estimates:[],decisions:[],evaluations:[]};
async function request(path,opts={}){calls.push([path,opts.method||'GET',opts.body?JSON.parse(opts.body):null]);
if(opts.method==='POST'){if(path==='/future/episodes'){created=true;return{synthetic:true,episode_id:episode};}return{synthetic:true};}
if(path==='/future/status')return{synthetic:true};if(path==='/future/episodes')return{synthetic:true,items:created?[{episode_id:episode}]:[]};
if(path==='/future/episodes/'+episode)return snapshot;return{synthetic:true,items:[]};}
function all(n){return[n,...n.children.flatMap(all)];}
(async()=>{let root=await window.DragonFuture.view({request});assert(calls.length===4);assert(calls.every(c=>c[1]==='GET'));assert(!all(root).some(n=>n.text==='25.00%'));
await all(root).find(n=>n.attrs['data-action']==='future-create').handlers.click();assert(calls.filter(c=>c[1]==='POST').length===1);assert(all(root).some(n=>n.text==='25.00%'));
await all(root).find(n=>n.attrs['data-action']==='future-decide').handlers.click();let decisions=calls.filter(c=>c[0].endsWith('/decisions'));assert(decisions.length===1);assert(decisions[0][2].expected_revision===3);assert(/^future-request-/.test(decisions[0][2].request_id));assert(!('outcome'in decisions[0][2]));
window.DragonFuture.stop();console.log('PASS_PASSIVE_OPEN_AND_EXPLICIT_REVISION_ACTION');})().catch(e=>{console.error(e);process.exitCode=1;});
'''
        result=subprocess.run([str(NODE),'-e',probe,str(ROOT/'client/desktop/web/future.js')],capture_output=True,text=True,timeout=15)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('PASS_PASSIVE_OPEN_AND_EXPLICIT_REVISION_ACTION',result.stdout)


if __name__=='__main__':unittest.main()
