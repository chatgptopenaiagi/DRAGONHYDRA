"""Regression tests for observed recovery-diagnostic mistakes, without live I/O."""
import unittest
from tests.installation.joomla_recovery import Inputs, component_renders, login_action


class JoomlaRecoveryDiagnosticsTests(unittest.TestCase):
    def test_normal_joomla_noscript_alert_does_not_mark_component_broken(self):
        response = ('<noscript><div class="alert alert-danger" role="alert">JavaScript required</div></noscript>'
                    '<div class="dragonhydra-administration"><h2>Data sources</h2><table>OpenFootball</table></div>')
        self.assertTrue(component_renders(response, "Data sources"))

    def test_actual_component_bridge_error_is_not_success(self):
        response = ('<div class="dragonhydra-administration">'
                    '<div class="alert alert-warning" role="alert">BRIDGE_NOT_CONFIGURED</div></div>')
        self.assertFalse(component_renders(response, "Data sources"))

    def test_anonymous_login_html_is_not_component_execution(self):
        self.assertFalse(component_renders('<input id="mod-login-username"><title>DRAGONHYDRA</title>', "DRAGONHYDRA"))

    def test_actual_form_action_and_hidden_fields_are_parsed(self):
        parsed = Inputs()
        parsed.feed('<form action="index.php" method="post" id="form-login"><input type="hidden" name="csrf" value="1"></form>')
        self.assertEqual(login_action('http://127.0.0.1:18740/administrator/', parsed),
                         'http://127.0.0.1:18740/administrator/index.php')
        self.assertEqual(parsed.hidden, {"csrf": "1"})

    def test_credentials_cannot_follow_form_to_another_profile(self):
        parsed = Inputs()
        parsed.feed('<form id="form-login" action="http://127.0.0.1:18750/administrator/index.php"></form>')
        with self.assertRaises(AssertionError):
            login_action('http://127.0.0.1:18740/administrator/', parsed)


if __name__ == '__main__':
    unittest.main()
