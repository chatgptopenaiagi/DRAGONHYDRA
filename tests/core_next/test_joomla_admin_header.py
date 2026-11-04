"""Real Atum CSS/header structure in isolated Edge; no installed app requests."""
from pathlib import Path
import importlib.util
import unittest

ROOT=Path(__file__).resolve().parents[2]
_lab_spec=importlib.util.spec_from_file_location('registered_fixture_release',ROOT/'scripts/core_next/release.py')
_lab_release=importlib.util.module_from_spec(_lab_spec)
_lab_spec.loader.exec_module(_lab_release)
LAB=_lab_release.canonical_lab(ROOT)
EDGE=Path(r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe')
ATUM=LAB/'baseline-payload/web/joomla-base/media/templates/administrator/atum/css/template.css'
COMPONENT=ROOT/'server/joomla/com_dragonhydra/media/css/control-center.css'


@unittest.skipUnless(EDGE.is_file() and ATUM.is_file(),'Existing Edge and public locked Atum CSS fixture required')
class JoomlaAdminHeaderTests(unittest.TestCase):
    def exercise(self,component_css):
        from playwright.sync_api import sync_playwright
        with sync_playwright() as playwright:
            browser=playwright.chromium.launch(executable_path=str(EDGE),headless=True)
            try:
                page=browser.new_page(viewport={'width':390,'height':844})
                page.route('**/*',lambda route:route.abort())
                # Same nested header markup as Atum index.php + mod_title.
                page.set_content('''<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"></head>
                <body class="admin com_dragonhydra view-dashboard"><header id="header" class="header"><div class="header-inside">
                  <div class="header-title d-flex"><div class="d-flex align-items-center"><a class="logo small" href="#fixture">D</a></div>
                    <div class="d-flex align-items-center"><div class="container-title"><h1 class="page-title">DRAGONHYDRA CORE NEXT · System Control Center</h1></div></div>
                  </div></div></header>
                <main><div class="dhcn-control-center"><span data-fixture="zero">0</span><div><strong data-fixture="nested">Retained <span>0</span></strong></div></div></main>
                </body></html>''')
                page.add_style_tag(content=ATUM.read_text())
                page.add_style_tag(content=component_css)
                original_text=page.locator('.dhcn-control-center').text_content()
                narrow=page.evaluate('({width:innerWidth,page:document.documentElement.scrollWidth,titleWhiteSpace:getComputedStyle(document.querySelector("#header .page-title")).whiteSpace})')
                self.assertLessEqual(narrow['page'],narrow['width']+2)
                self.assertEqual(narrow['titleWhiteSpace'],'normal')
                self.assertEqual(page.locator('[data-fixture="zero"]').inner_text(),'0')
                self.assertEqual(page.locator('[data-fixture="nested"]').inner_text(),'Retained 0')
                self.assertEqual(page.locator('.dhcn-control-center').text_content(),original_text)
                page.evaluate('document.body.classList.replace("com_dragonhydra","com_unrelated_fixture")')
                unrelated=page.evaluate('({page:document.documentElement.scrollWidth,whiteSpace:getComputedStyle(document.querySelector("#header .page-title")).whiteSpace})')
                self.assertEqual(unrelated['whiteSpace'],'nowrap')
                self.assertGreater(unrelated['page'],390)
                page.evaluate('document.body.classList.replace("com_unrelated_fixture","com_dragonhydra")')
                page.set_viewport_size({'width':1440,'height':1000})
                self.assertEqual(page.locator('#header .page-title').evaluate('(n)=>getComputedStyle(n).whiteSpace'),'nowrap')
                self.assertEqual(page.locator('.dhcn-control-center').text_content(),original_text)
                return narrow
            finally:browser.close()

    def test_scoped_narrow_header_preserves_desktop_unrelated_and_nested_zero_content(self):
        self.exercise(COMPONENT.read_text())


if __name__=='__main__':unittest.main()
