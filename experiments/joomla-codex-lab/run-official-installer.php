<?php
declare(strict_types=1);
// Supported options were inspected in installation/joomla.php help install.
// Keep passwords out of shell arguments and redact console output defensively.
$site = 'C:/xampp/htdocs/joomla-codex-lab';
$credentials = json_decode(file_get_contents(__DIR__ . '/credentials.local.txt'), true, 512, JSON_THROW_ON_ERROR);
ob_start(static function (string $output) use ($credentials): string {
    return str_replace([$credentials['db_password'], $credentials['admin_password']], '[REDACTED]', $output);
});
$argv = [
    $site . '/installation/joomla.php',
    'install',
    '--site-name=Codex XAMPP Laboratory',
    '--admin-user=' . $credentials['admin_name'],
    '--admin-username=' . $credentials['admin_username'],
    '--admin-password=' . $credentials['admin_password'],
    '--admin-email=' . $credentials['admin_email'],
    '--db-type=mysqli',
    '--db-host=' . $credentials['db_host'] . ':' . $credentials['db_port'],
    '--db-user=' . $credentials['db_user'],
    '--db-pass=' . $credentials['db_password'],
    '--db-name=' . $credentials['db_name'],
    '--db-prefix=' . $credentials['db_prefix'],
    '--no-interaction',
    '--no-ansi',
];
$argc = count($argv);
$_SERVER['argv'] = $argv;
$_SERVER['argc'] = $argc;
$_SERVER['SCRIPT_FILENAME'] = $argv[0];
chdir($site);
require $site . '/installation/joomla.php';
