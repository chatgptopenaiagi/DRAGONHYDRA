"""Render the actual Joomla templates in isolated no-backend PHP fixtures."""
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
PHP = ROOT / 'build/workstation/test-install/application files/web/php/php.exe'
FIXTURE = ROOT / 'tests/installation/joomla_frontend_render_fixture.php'


@unittest.skipUnless(PHP.is_file(), 'Verified private Windows PHP runtime required')
class JoomlaFrontendTemplatesTests(unittest.TestCase):
    def render(self, scenario):
        result = subprocess.run([str(PHP), '-n', '-d', 'extension_dir=' + str(PHP.parent / 'ext'),
                                 '-d', 'extension=php_mbstring.dll', str(FIXTURE), scenario],
                                capture_output=True, text=True, encoding='utf-8', timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn('Fatal error', result.stdout)
        self.assertNotIn('Warning:', result.stdout)
        return result.stdout

    def test_anonymous_shell_has_no_private_totals_or_fixture_data(self):
        rendered = self.render('anonymous')
        self.assertIn('Sign in to your workspace', rendered)
        self.assertNotIn('data-total=', rendered)
        self.assertNotIn('SYNTHETIC fixture home', rendered)
        self.assertNotIn('Your retained workspace', rendered)

    def test_signed_in_unpermitted_identity_gets_honest_denial(self):
        rendered = self.render('permission_denied')
        self.assertIn('This account cannot open the sports workspace', rendered)
        self.assertIn('Sign out', rendered)
        self.assertNotIn('data-total=', rendered)

    def test_empty_dataset_does_not_invent_records(self):
        rendered = self.render('empty')
        for field in ('total_matches', 'total_teams', 'total_competitions'):
            self.assertIn('data-total="' + field + '">0</strong>', rendered)
        self.assertIn('No retained matches are available', rendered)
        self.assertIn('Not recorded', rendered)

    def test_backend_failure_has_bounded_message_and_retry(self):
        rendered = self.render('backend_unavailable')
        self.assertIn('The workspace is temporarily unavailable', rendered)
        self.assertIn('bounded request', rendered)
        self.assertIn('Try again', rendered)
        self.assertNotIn('data-total=', rendered)

    def test_finished_match_without_forecast_stays_unavailable(self):
        rendered = self.render('noanalysis')
        self.assertIn('No supported forecast is available', rendered)
        self.assertIn('No prospective forecast was retained for this finished match.', rendered)
        self.assertNotIn('dh-probabilities">', rendered)
        self.assertIn('SYNTHETIC fixture home', rendered)


if __name__ == '__main__':
    unittest.main()
