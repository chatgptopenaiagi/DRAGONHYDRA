import unittest
from tests.installation.joomla_frontend_menu_contract import NATIVE_DEFAULTS, normalize_home_params, site_menus_equivalent


class ManagedHomeMenuContractTests(unittest.TestCase):
    def setUp(self):
        self.minimal = {'show_page_heading': '0', 'page_title': 'DRAGONHYDRA | Sports intelligence',
                        'pageclass_sfx': ' dragonhydra-workspace-page', 'dragonhydra_workspace_home': 1}
        self.native = NATIVE_DEFAULTS | {k: v for k, v in self.minimal.items() if k != 'dragonhydra_workspace_home'}
        self.before = [{'id': 101, 'client_id': 0, 'home': 0, 'title': 'Home', 'params_sha256': 'original'},
                       {'id': 142, 'client_id': 0, 'home': 1, 'title': 'DRAGONHYDRA', 'template_style_id': 13, 'params_sha256': 'minimal'}]
        self.after = [dict(row) for row in self.before]
        self.after[1]['params_sha256'] = 'native'

    def equivalent(self):
        return site_menus_equivalent(self.before, self.after, 142, self.minimal, self.native)

    def test_only_known_native_defaults_and_unused_marker_normalize(self):
        self.assertTrue(self.equivalent())

    def test_changed_visible_home_title_is_still_a_failure(self):
        self.native['page_title'] = 'Unexpected title'
        self.assertFalse(self.equivalent())

    def test_changed_native_visibility_is_not_ignored(self):
        self.native['menu_show'] = '0'
        self.assertFalse(self.equivalent())

    def test_unrelated_original_menu_modification_is_not_ignored(self):
        self.after[0]['params_sha256'] = 'unexpected'
        self.assertFalse(self.equivalent())

    def test_duplicate_or_additional_menu_is_not_ignored(self):
        self.after.append({'id': 143, 'client_id': 0, 'home': 1})
        self.assertFalse(self.equivalent())

    def test_unknown_non_default_parameters_are_not_discarded(self):
        self.native['custom_setting'] = 'unexpected'
        self.assertFalse(self.equivalent())

    def test_unexpected_marker_value_is_rejected(self):
        with self.assertRaises(ValueError):
            normalize_home_params({'dragonhydra_workspace_home': 0})


if __name__ == '__main__':
    unittest.main()
