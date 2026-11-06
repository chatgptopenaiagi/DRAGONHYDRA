"""Static synthetic Research UI contracts and native JavaScript syntax only.

No browser, product server, provider, model, credentials or network is exercised.
Genuine web interaction acceptance is a separate owner-run phase.
"""
from pathlib import Path
import re
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / 'client/desktop/web'
MIRROR = ROOT / 'src/dragonhydra/resources/web'
NODE = Path(r'C:\Program Files\nodejs\node.exe')


class RealtimeWebContracts(unittest.TestCase):
    def setUp(self):
        self.script = (WEB / 'realtime.js').read_text(encoding='utf-8')

    def test_all_five_packaged_web_assets_match_desktop_mirrors(self):
        for name in ('app.js', 'index.html', 'style.css', 'realtime.js', 'realtime.css'):
            with self.subTest(asset=name):
                self.assertEqual((WEB/name).read_bytes(), (MIRROR/name).read_bytes())

    def test_research_navigation_is_additive_and_assets_are_local(self):
        app=(WEB/'app.js').read_text(encoding='utf-8')
        for key in ('live','today','teams','competitions','odds','analysis','connections','research'):
            self.assertRegex(app, r'\["'+key+r'",')
        self.assertIn('window.DragonRealtime.view({request})',app)
        self.assertIn('if(route[0]!=="research")window.DragonRealtime?.stop()',app)
        html=(WEB/'index.html').read_text(encoding='utf-8')
        self.assertLess(html.index('./realtime.js'),html.index('./app.js'))
        self.assertIn('./realtime.css',html)
        self.assertTrue(all(url.startswith('./') for url in re.findall(r'<script[^>]+src="([^"]+)"',html)))

    def test_synthetic_gate_and_visible_simulation_provenance(self):
        self.assertIn('SIMULATION · SYNTHETIC DATA ONLY',self.script)
        self.assertIn('snapshot?.synthetic !== true',self.script)
        self.assertIn('["DEMONSTRATION", "REPLAY"]',self.script)
        self.assertIn('item.synthetic === true',self.script)
        self.assertIn('source_mode: "DEMONSTRATION"',self.script)
        self.assertIn('Virtual credentials only',self.script)
        self.assertIn('No external provider or OpenAI calls',self.script)

    def test_only_scoped_existing_authenticated_transport_is_used(self):
        self.assertIn('const PREFIX = "/realtime"',self.script)
        self.assertIn('request(PREFIX + path',self.script)
        for forbidden in ('fetch(', 'XMLHttpRequest', 'WebSocket(', 'EventSource(', 'api.openai', 'https://', 'http://127.'):
            self.assertNotIn(forbidden,self.script)
        for forbidden in ('/forecasts','/evaluations','/research/archives','/connections/','/local-explanations','/exports'):
            self.assertNotIn(forbidden,self.script)
        self.assertIn('encodeURIComponent(selectedMatch)',self.script)

    def test_navigation_and_playback_polling_do_not_submit_mutations(self):
        startup=self.script[self.script.rindex('    try { model.status = await get("/status")'):]
        self.assertNotIn('post(',startup)
        poll=self.script.split('    function queuePoll()',1)[1].split('    async function loadList()',1)[0]
        self.assertIn('await refresh()',poll)
        self.assertNotIn('post(',poll)
        self.assertNotIn('setInterval(',self.script)
        for action in ('step','start','pause','resume'):
            self.assertIn('replay("'+action+'")',self.script)
        self.assertIn('!Number.isInteger(count) || count < 1 || count > 100',self.script)
        self.assertIn('rate < 1 || rate > 100',self.script)
        self.assertIn('version !== refreshVersion',self.script)

    def test_probabilities_are_fetched_without_fictional_numeric_fallbacks(self):
        self.assertIn('obj(record?.forecast)',self.script)
        self.assertIn('obj(forecast.full_time_result)',self.script)
        self.assertIn('typeof value === "number" && Number.isFinite(value)',self.script)
        self.assertNotIn('Math.random',self.script)
        self.assertNotRegex(self.script,r'(?:home|draw|away)\s*:\s*(?:0\.\d+|1\b)')
        self.assertIn('value === null',self.script)
        self.assertIn('Not supplied',self.script)
        for horizon in ('1','5','10','30','FULL_TIME'):
            self.assertIn('["'+horizon+'",',self.script)
        for field in ('next_goal_occurrence','next_goal_side','remaining_goals','score_distribution','tail_mass','effective_minutes','uncertainty'):
            self.assertIn(field,self.script)
        self.assertIn('remaining.distribution.map((p, goals)',self.script)
        self.assertIn('remaining.tail_bucket?.probability',self.script)
        self.assertIn('Expected remaining goals',self.script)
        self.assertIn('Next goal side (unconditional)',self.script)
        self.assertIn('Home given a goal',self.script)

    def test_revision_clock_delta_and_analysis_binding_are_explicit(self):
        for field in ('event_time','received_at','forecast_id','state_revision','reason_codes','evidence_ids','tool_results'):
            self.assertIn(field,self.script)
        self.assertIn('(value * 100).toFixed(2)} pp',self.script)
        self.assertIn('model.analysis && record && model.analysis.revision === record.revision',self.script)
        self.assertNotIn('model.analysis?.revision === record?.revision',self.script)
        self.assertIn('forecast_revision: record.revision',self.script)
        self.assertIn('Observed score and forecast distributions are separate',self.script)

    def test_virtual_worlds_branch_prefixes_and_relevance_are_explicit(self):
        for universe in ('constant','card_sensitive','tempo_signal','noisy_signal'):
            self.assertIn('"'+universe+'"',self.script)
        self.assertIn('at_revision: record.state_revision',self.script)
        self.assertNotIn('at_revision: record.revision',self.script)
        self.assertIn('/branches`',self.script)
        self.assertIn('Rewind into new branch',self.script)
        self.assertIn('Neither erases or rewrites the original history',self.script)
        self.assertIn('Select an earlier revision to branch from before full time',self.script)
        self.assertIn('get("/experiments")',self.script)
        self.assertIn('post("/experiments/relevance", {seed: selectedSeed(), cases: 400})',self.script)
        self.assertIn('observed_improvement',self.script)
        self.assertIn('Not observed',self.script)
        self.assertIn('heldout_brier_delta',self.script)
        self.assertIn('do not establish real-world forecasting accuracy',self.script)

    def test_dom_output_is_text_safe_and_inspection_redacts_credentials(self):
        for forbidden in ('innerHTML','outerHTML','insertAdjacentHTML','document.write','eval(','new Function'):
            self.assertNotIn(forbidden,self.script)
        self.assertIn('document.createTextNode(String(child))',self.script)
        self.assertIn('secret|credential|authorization|api.?key|token',self.script)
        self.assertIn('"[redacted]"',self.script)
        self.assertIn('"aria-label"',self.script)
        self.assertIn('mark.addEventListener("keydown"',self.script)

    @unittest.skipUnless(NODE.is_file(), 'Existing verified Windows Node executable unavailable')
    def test_existing_node_parses_both_javascript_assets(self):
        for name in ('app.js','realtime.js'):
            with self.subTest(asset=name):
                completed=subprocess.run([str(NODE),'--check',str(WEB/name)],capture_output=True,text=True,timeout=20)
                self.assertEqual(completed.returncode,0,completed.stderr)


if __name__ == '__main__': unittest.main()
