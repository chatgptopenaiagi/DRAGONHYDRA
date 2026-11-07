"""Local source contracts and Node DOM probe; no browser/server/network."""
from pathlib import Path
import subprocess
import unittest

ROOT=Path(__file__).absolute().parents[1]
NODE=Path(r'C:\Program Files\nodejs\node.exe')

class LogisticsWebTests(unittest.TestCase):
    def setUp(self):self.script=(ROOT/'client/desktop/web/logistics.js').read_text(encoding='utf-8')
    def test_exact_mirrors_and_additive_pages(self):
        for name in ('app.js','index.html','logistics.js','logistics.css'):
            self.assertEqual((ROOT/'client/desktop/web'/name).read_bytes(),(ROOT/'src/dragonhydra/resources/web'/name).read_bytes())
        app=(ROOT/'client/desktop/web/app.js').read_text(encoding='utf-8');html=(ROOT/'client/desktop/web/index.html').read_text(encoding='utf-8')
        for symbol in ('DragonRealtime.view','DragonFuture.view','DragonLogistics.view'):self.assertIn(symbol,app)
        for name in ('./realtime.js','./future.js','./logistics.js','./logistics.css'):self.assertIn(name,html)
        self.assertNotIn('https://',html)
        self.assertIn('const logisticsTraining=path==="/logistics/training"',app)
        self.assertIn('logisticsTraining?600000:path==="/future/training"?300000:20000',app)
        self.assertIn('refresh retained experiment results before retrying',app)
    def test_all_seven_domain_sections_and_visible_virtual_contract(self):
        for section in ('inventory','demand','replenishment','network','relevance','analytics','time'):
            self.assertIn(f'panel("{section}"',self.script)
        for text in ('SYNTHETIC COGNITIVE LOGISTICS','Fictional companies, SKUs','value?.synthetic !== true',
                     'by_location','inventory_position','backorder','lost_sales','current_forecasts','Observed sales',
                     'Expected total horizon units','Expected daily units','Uncalibrated synthetic predictive interval',
                     'distribution.tail_probability','Actual conservation evidence','available_day','policy_comparison'):
            self.assertIn(text,self.script)
    def test_explicit_bounded_actions_and_text_safe_output(self):
        for text in ('crypto.randomUUID()','expected_revision: revision()','/decisions','/advance','/training','/analyses',
                     'reorder_point','order_up_to','base_stock','s_S','probabilistic_cost','handcrafted','learned',
                     'compare_methods','bounded_method_search','counterfactual','paired_cost_vs_baseline'):
            self.assertIn(text,self.script)
        for forbidden in ('innerHTML','eval(','fetch(','Authorization','localStorage','setInterval(','setTimeout('):
            self.assertNotIn(forbidden,self.script)
        self.assertIn('future_demand',self.script)
        self.assertIn('actual_arrival',self.script)
    @unittest.skipUnless(NODE.is_file(),'Existing verified Node required')
    def test_node_parses_both_assets(self):
        for name in ('logistics.js','app.js'):
            r=subprocess.run([str(NODE),'--check',str(ROOT/'client/desktop/web'/name)],capture_output=True,text=True,timeout=15)
            self.assertEqual(r.returncode,0,r.stderr)
    @unittest.skipUnless(NODE.is_file(),'Existing verified Node required')
    def test_passive_open_full_dashboard_and_one_shot_revision_bound_decision(self):
        code=r'''
const fs=require('fs'),vm=require('vm'),assert=require('assert');
class N{constructor(tag,text=''){this.tag=tag;this.text=text;this.children=[];this.attrs={};this.handlers={};}append(...x){this.children.push(...x);}replaceChildren(...x){this.children=x;}setAttribute(k,v){this.attrs[k]=v;}addEventListener(k,v){this.handlers[k]=v;}querySelectorAll(){return [];}querySelector(){return null;}}
global.Node=N;global.window={};global.document={createElement:t=>new N(t),createElementNS:(ns,t)=>new N(t),createTextNode:t=>new N('#text',t),getElementById:()=>null};global.crypto=require('crypto').webcrypto;
vm.runInThisContext(fs.readFileSync(process.argv[1],'utf8'));let created=false;const calls=[],id='virtual-logistics-fixture';
const view={synthetic:true,episode_id:id,snapshot:{revision:7,day:28,days_remaining:60,demand_mode:'lost_sales',inventory:{by_location:{retail_a:{SKU_VIRTUAL_1:{on_hand:23,on_order:0,backorder:0,reserved:0,atp:23,in_transit:0,inventory_position:23,capacity:100}}},conservation:{passed:true}},history:{retail_a:[]},candidates:[],acquired:{},budget_remaining:10},current_forecasts:{retail_a:{horizon:5,mean:15,daily_mean:3,variance:15,method:'naive',interval90:[9,22],distribution:{support:[0,1],probabilities:[.2,.8],tail_probability:0}}},decisions:[],evaluations:[],network:{nodes:{supplier:{kind:'supplier',capacity:100},retail_a:{kind:'retail',capacity:100}},edges:[{id:'edge',source:'supplier',dest:'retail_a',lead_time:2}],shipments:[]},metrics:{},analyses:[]};
async function request(path,opts={}){calls.push([path,opts.method||'GET',opts.body?JSON.parse(opts.body):null]);if(opts.method==='POST'){if(path==='/logistics/episodes'){created=true;return{episode_id:id,synthetic:true};}return{synthetic:true};}if(path==='/logistics/status')return{synthetic:true};if(path==='/logistics/episodes')return{synthetic:true,items:created?[{episode_id:id}]:[]};if(path==='/logistics/episodes/'+id)return view;return{synthetic:true,items:[]};}
function all(n){return[n,...n.children.flatMap(all)];}
(async()=>{const root=await window.DragonLogistics.view({request});assert(calls.length===4&&calls.every(c=>c[1]==='GET'));await all(root).find(n=>n.attrs['data-action']==='logistics-create').handlers.click();assert(calls.filter(c=>c[1]==='POST').length===1);assert(calls.find(c=>c[1]==='POST')[2].demand_mode==='lost_sales');for(const s of ['inventory','demand','replenishment','network','relevance','analytics','time'])assert(all(root).some(n=>n.attrs.id==='logistics-'+s));assert(all(root).some(n=>n.text==='23'));
const button=all(root).find(n=>n.attrs['data-action']==='logistics-decide');await Promise.all([button.handlers.click(),button.handlers.click()]);const d=calls.filter(c=>c[0].endsWith('/decisions'));assert(d.length===1);assert(d[0][2].expected_revision===7&&d[0][2].policy==='order_up_to'&&d[0][2].acquisition==='none');assert(/^logistics-request-/.test(d[0][2].request_id));assert(!('actual_demand'in d[0][2]));window.DragonLogistics.stop();console.log('PASS_PASSIVE_OPEN_SEVEN_SECTIONS_EXPLICIT_DECISION');})().catch(e=>{console.error(e);process.exitCode=1;});
'''
        r=subprocess.run([str(NODE),'-e',code,str(ROOT/'client/desktop/web/logistics.js')],capture_output=True,text=True,timeout=15)
        self.assertEqual(r.returncode,0,r.stderr);self.assertIn('PASS_PASSIVE_OPEN_SEVEN_SECTIONS_EXPLICIT_DECISION',r.stdout)

if __name__=='__main__':unittest.main()
