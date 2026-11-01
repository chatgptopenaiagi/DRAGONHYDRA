"""Real browser execution against labelled synthetic backend identity fixtures."""
import json
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[2]
EDGE=Path(r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe')


@unittest.skipUnless(EDGE.is_file(),'Windows Edge browser fixture; Linux has separate server acceptance')
class DashboardPairingTests(unittest.TestCase):
    def exercise(self,product,edition):
        from playwright.sync_api import sync_playwright
        requests=[]
        assets=ROOT/'src'/'dragonhydra'/'resources'/'web'
        with sync_playwright() as playwright:
            browser=playwright.chromium.launch(executable_path=str(EDGE),headless=True)
            try:
                context=browser.new_context()
                def route(request):
                    path=request.request.url.split('18999',1)[-1].split('?',1)[0]
                    if path.startswith('/dragon/api/v1'):
                        name=path[len('/dragon/api/v1'):]
                        if name=='/health/live':body={'status':'alive','product':product,'installation':{'edition':edition,'installation_id':'fixture-core-next-a'}}
                        elif name=='/health/ready':body={'status':'ready','version':'0.5.0-dev.1','backend':'sqlite'}
                        elif name=='/session':
                            requests.append(json.loads(request.request.post_data));body={'user':'fixture','roles':['admin']}
                        elif name=='/matches':body={'items':[],'total':0,'limit':25,'offset':0}
                        elif name=='/updates':return request.fulfill(status=200,content_type='text/event-stream',body='')
                        else:body={}
                        return request.fulfill(status=200,content_type='application/json',body=json.dumps(body))
                    name='index.html' if path=='/' else path.lstrip('/')
                    file=assets/name
                    if not file.is_relative_to(assets) or not file.is_file():return request.fulfill(status=404,body='fixture missing')
                    mime={'.js':'text/javascript','.css':'text/css','.html':'text/html','.svg':'image/svg+xml'}.get(file.suffix,'application/octet-stream')
                    request.fulfill(status=200,content_type=mime,body=file.read_bytes())
                context.route('**/*',route)
                page=context.new_page()
                page.goto('http://127.0.0.1:18999/',wait_until='domcontentloaded')
                result=page.evaluate("async()=>{try{await login('CORE_NEXT_SYNTHETIC_TEST_ONLY');return {accepted:true}}catch(error){return {accepted:false,error:error.message}}}")
                context.close()
                return result,requests
            finally:browser.close()

    def test_original_backend_rejected_before_pairing_secret_is_sent(self):
        result,requests=self.exercise('DRAGONHYDRA','original')
        self.assertFalse(result['accepted'])
        self.assertIn('not a CORE NEXT backend',result['error'])
        self.assertEqual(requests,[])

    def test_matching_candidate_identity_allows_own_pairing(self):
        result,requests=self.exercise('DRAGONHYDRA CORE NEXT','CORE NEXT')
        self.assertTrue(result['accepted'],result)
        self.assertEqual(requests,[{'token':'CORE_NEXT_SYNTHETIC_TEST_ONLY'}])


if __name__=='__main__':unittest.main()
