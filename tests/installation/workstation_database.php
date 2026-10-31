<?php
/** Read-only proof against the installed private MariaDB, never a host database. */
declare(strict_types=1);
if (PHP_SAPI !== 'cli') { exit(1); }
$cfg = json_decode(file_get_contents($argv[1]), true, 64, JSON_THROW_ON_ERROR);
$output = $argv[2];
$expected = rtrim(str_replace('\\', '/', $cfg['state_root']), '/') . '/mysql-data';
$record = ['passed' => false, 'database_mutations' => false];
mysqli_report(MYSQLI_REPORT_ERROR | MYSQLI_REPORT_STRICT);
try {
    $db = new mysqli('127.0.0.1', 'root', $cfg['root_password'], '', $cfg['database_port']);
    $db->set_charset('utf8mb4');
    $actual = $db->query('SELECT @@version AS version, @@port AS port, @@datadir AS datadir, @@basedir AS basedir, @@bind_address AS bind_address, CURRENT_USER() AS authenticated_identity')->fetch_assoc();
    if (strcasecmp(rtrim(str_replace('\\', '/', $actual['datadir']), '/'), $expected) !== 0
        || (int) $actual['port'] !== (int) $cfg['database_port'] || $actual['bind_address'] !== '127.0.0.1') {
        throw new RuntimeException('DATABASE_INSTANCE_OWNERSHIP_MISMATCH');
    }
    $record['server'] = $actual;
    $stmt = $db->prepare('SELECT SCHEMA_NAME FROM information_schema.SCHEMATA WHERE SCHEMA_NAME IN (?,?) ORDER BY SCHEMA_NAME');
    $stmt->bind_param('ss', $cfg['db_name'], $cfg['core_db_name']); $stmt->execute();
    $record['schemas'] = array_column($stmt->get_result()->fetch_all(MYSQLI_ASSOC), 'SCHEMA_NAME');
    if (count($record['schemas']) !== 2) { throw new RuntimeException('SCHEMA_NOT_INITIALIZED'); }
    $app = new mysqli('127.0.0.1', $cfg['db_user'], $cfg['db_password'], $cfg['db_name'], $cfg['database_port']);
    $app->set_charset('utf8mb4');
    $record['joomla_connection'] = $app->query('SELECT CURRENT_USER() AS identity, DATABASE() AS selected_schema')->fetch_assoc();
    $record['joomla_users'] = (int) $app->query('SELECT COUNT(*) FROM dh_users')->fetch_row()[0];
    $record['extension'] = $app->query("SELECT extension_id,element,enabled,manifest_cache,params FROM dh_extensions WHERE element='com_dragonhydra' AND type='component'")->fetch_assoc();
    if (!$record['extension'] || (int) $record['extension']['enabled'] !== 1) { throw new RuntimeException('EXTENSION_NOT_ENABLED'); }
    $record['extension']['version'] = json_decode($record['extension']['manifest_cache'], true, 64, JSON_THROW_ON_ERROR)['version'];
    $record['extension']['configuration_sha256'] = hash('sha256', $record['extension']['params']);
    unset($record['extension']['manifest_cache'], $record['extension']['params']);
    $record['kernel_authority'] = 'sqlite';
    $record['mariadb_core_reserved_only'] = true;
    $record['passed'] = true;
} catch (Throwable $failure) {
    $record['exception_class'] = get_class($failure);
    $record['error'] = 'Read-only private database verification failed; credentials are omitted.';
}
$record['verified_at'] = gmdate('c');
file_put_contents($output, json_encode($record, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES | JSON_THROW_ON_ERROR));
echo json_encode(['passed' => $record['passed'], 'port' => $cfg['database_port'], 'schema' => $cfg['db_name'], 'extension_version' => $record['extension']['version'] ?? null]) . "\n";
exit($record['passed'] ? 0 : 1);
