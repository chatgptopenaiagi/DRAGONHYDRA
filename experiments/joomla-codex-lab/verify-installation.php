<?php
declare(strict_types=1);
mysqli_report(MYSQLI_REPORT_ERROR | MYSQLI_REPORT_STRICT);
$site = 'C:/xampp/htdocs/joomla-codex-lab';
$secrets = json_decode(file_get_contents(__DIR__ . '/credentials.local.txt'), true, 512, JSON_THROW_ON_ERROR);
define('_JEXEC', 1);
require $site . '/defines.php';
require $site . '/configuration.php';
$config = new JConfig();
$db = new mysqli('127.0.0.1', $secrets['db_user'], $secrets['db_password'], $secrets['db_name'], 3306);
$prefix = $config->dbprefix;
if (!preg_match('/^[a-z][a-z0-9]*_$/', $prefix)) {
    throw new RuntimeException('Unsafe table prefix');
}
$tables = $db->query('SHOW TABLES')->fetch_all(MYSQLI_NUM);
$user = $db->query("SELECT u.username,u.password,u.block,g.title AS group_title FROM `{$prefix}users` u JOIN `{$prefix}user_usergroup_map` m ON m.user_id=u.id JOIN `{$prefix}usergroups` g ON g.id=m.group_id WHERE g.title='Super Users'")->fetch_assoc();
$otherDbDenied = false;
try {
    $db->query('SELECT 1 FROM mysql.user LIMIT 0');
} catch (mysqli_sql_exception $e) {
    $otherDbDenied = in_array($e->getCode(), [1044, 1142], true);
}
$webrootSecretMatches = [];
foreach (new RecursiveIteratorIterator(new RecursiveDirectoryIterator($site, FilesystemIterator::SKIP_DOTS)) as $file) {
    if (!$file->isFile()) {
        continue;
    }
    $data = file_get_contents($file->getPathname());
    if (str_contains($data, $secrets['db_password']) || str_contains($data, $secrets['admin_password'])) {
        $webrootSecretMatches[] = $file->getPathname();
    }
}
$result = [
    'checked_utc' => gmdate('c'),
    'configuration_exists' => is_file($site . '/configuration.php'),
    'private_configuration_exists' => is_file(JPATH_CONFIGURATION . '/configuration.php'),
    'configuration_directory' => JPATH_CONFIGURATION,
    'installation_directory_removed' => !is_dir($site . '/installation'),
    'database_connected_as' => $db->query('SELECT CURRENT_USER()')->fetch_row()[0],
    'database' => $db->query('SELECT DATABASE()')->fetch_row()[0],
    'table_count' => count($tables),
    'table_prefix' => $prefix,
    'all_tables_have_expected_prefix' => count(array_filter($tables, static fn($row) => !str_starts_with($row[0], $prefix))) === 0,
    'extension_records' => (int) $db->query("SELECT COUNT(*) FROM `{$prefix}extensions`")->fetch_row()[0],
    'super_user_created' => $user !== null && $user['username'] === $secrets['admin_username'],
    'super_user_password_hash_verified' => $user !== null && password_verify($secrets['admin_password'], $user['password']),
    'super_user_enabled' => $user !== null && (int) $user['block'] === 0,
    'unrelated_mysql_database_read_denied' => $otherDbDenied,
    'webroot_plaintext_secret_matches' => $webrootSecretMatches,
    'site_name' => $config->sitename,
];
$passed = $result['configuration_exists'] && $result['private_configuration_exists']
    && $result['installation_directory_removed'] && $result['table_count'] > 50
    && $result['all_tables_have_expected_prefix'] && $result['super_user_created']
    && $result['super_user_password_hash_verified'] && $result['super_user_enabled']
    && $otherDbDenied && !$webrootSecretMatches;
$result['passed'] = $passed;
$json = json_encode($result, JSON_PRETTY_PRINT | JSON_THROW_ON_ERROR);
file_put_contents(__DIR__ . '/evidence/installation-verification.json', $json . "\n");
echo $json . "\n";
exit($passed ? 0 : 1);
