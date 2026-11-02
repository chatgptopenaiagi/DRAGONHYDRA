"""Real Edge against synthetic intercepted API/assets; never an installed profile."""
import json
from pathlib import Path
import unittest
from urllib.parse import urlsplit

ROOT=Path(__file__).resolve().parents[2]
EDGE=Path(r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe')
ORIGIN='http://127.0.0.1:18999'
COMPETITION='c'*64


@unittest.skipUnless(EDGE.is_file(),'Existing Windows Edge required; no download')
class DashboardSkipTests(unittest.TestCase):
    def exercise(self,assets,script_override=None):
        from playwright.sync_api import sync_playwright
        mutations=[]
        standing={'competition':'Synthetic skip-link league','season':None,'label':'Synthetic retained FT table',
                  'official':False,'source_id':'synthetic-skip-only','as_of':None,
                  'limitations':['Synthetic limitation rendered as a paragraph.'],
                  'items':[{'team_id':'d'*64,'team':'Synthetic zero team','played':1,'won':0,'drawn':1,
                            'lost':0,'goals_for':0,'goals_against':0,'points':1}]}
        with sync_playwright() as playwright:
            browser=playwright.chromium.launch(executable_path=str(EDGE),headless=True)
            try:
                context=browser.new_context(viewport={'width':1440,'height':1000})
                def route(handler):
                    request=handler.request;parsed=urlsplit(request.url)
                    if parsed.hostname=='example.invalid':
                        return handler.fulfill(status=200,content_type='text/plain',body='Synthetic external handoff only')
                    if request.method!='GET':
                        mutations.append({'method':request.method,'path':parsed.path})
                        return handler.fulfill(status=403,body='Synthetic fixture forbids mutation')
                    if parsed.path.startswith('/dragon/api/v1/'):
                        path=parsed.path.removeprefix('/dragon/api/v1')
                        if path=='/health/live':
                            body={'status':'alive','product':'DRAGONHYDRA CORE NEXT',
                                  'installation':{'edition':'CORE NEXT','installation_id':'core-next-synthetic-skip'}}
                        elif path=='/health/ready':body={'status':'ready','version':'synthetic-fixture','backend':'sqlite'}
                        elif path=='/competitions/'+COMPETITION+'/standings':body=standing
                        elif path=='/updates':return handler.fulfill(status=200,content_type='text/event-stream',body='')
                        else:return handler.fulfill(status=404,content_type='application/json',body='{}')
                        return handler.fulfill(status=200,content_type='application/json',body=json.dumps(body))
                    name='index.html' if parsed.path=='/' else parsed.path.lstrip('/')
                    file=assets/name
                    if not file.is_relative_to(assets) or not file.is_file():
                        return handler.fulfill(status=404,body='Synthetic asset missing')
                    content=script_override.read_bytes() if name=='app.js' and script_override else file.read_bytes()
                    mime={'.js':'text/javascript','.css':'text/css','.html':'text/html','.svg':'image/svg+xml'}.get(file.suffix,'application/octet-stream')
                    return handler.fulfill(status=200,content_type=mime,body=content)
                context.route('**/*',route)
                page=context.new_page()
                page.goto(ORIGIN+'/#standings/'+COMPETITION,wait_until='domcontentloaded')
                page.locator('#main table tbody tr').wait_for(state='visible')
                expected='#standings/'+COMPETITION
                page.locator('a.skip[href="#main"]').focus()
                page.keyboard.press('Enter')
                page.wait_for_timeout(100)
                self.assertEqual(page.evaluate('location.hash'),expected)
                self.assertEqual(page.evaluate('document.activeElement.id'),'main')
                self.assertEqual(page.locator('#main table tbody tr').count(),1)
                page.keyboard.press('Tab')
                self.assertTrue(page.evaluate('document.activeElement.matches(":focus-visible")'))
                self.assertEqual(page.locator('#main table tbody tr td').all_text_contents(),
                                 ['Synthetic zero team','1','0','1','0','0','0','1'])
                for address in ('https://example.invalid/register','http://example.invalid/docs'):
                    page.evaluate('(address)=>main.append(link("Synthetic provider",address))',address)
                    anchor=page.get_by_role('link',name='Synthetic provider',exact=True)
                    self.assertEqual(anchor.get_attribute('target'),'_blank')
                    self.assertIn('noopener',anchor.get_attribute('rel'))
                    with page.expect_popup() as event:anchor.click()
                    popup=event.value;popup.wait_for_url(address,wait_until='domcontentloaded')
                    self.assertEqual(popup.url,address);popup.close()
                    self.assertEqual(page.evaluate('location.hash'),expected)
                    self.assertEqual(page.locator('#main table tbody tr').count(),1)
                    anchor.evaluate('(node)=>node.remove()')
                page.locator('#refresh').click()
                page.locator('#main table tbody tr').wait_for(state='visible')
                page.reload(wait_until='domcontentloaded')
                page.locator('#main table tbody tr').wait_for(state='visible')
                self.assertEqual(page.evaluate('location.hash'),expected)
                self.assertEqual(page.locator('#main table tbody tr').count(),1)
                self.assertNotIn('[object HTMLParagraphElement]',page.locator('#main').inner_text())
                self.assertEqual(mutations,[])
                context.close()
            finally:browser.close()

    def test_keyboard_skip_keeps_standings_and_external_links_in_both_clients(self):
        for relative in ('src/dragonhydra/resources/web','client/desktop/web'):
            with self.subTest(client=relative):self.exercise(ROOT/relative)


if __name__=='__main__':unittest.main()
