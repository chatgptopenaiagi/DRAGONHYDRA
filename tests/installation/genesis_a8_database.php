<?php
declare(strict_types=1);

/* One bounded SELECT against the dedicated A8 Joomla database. Credentials
 * remain in PHP memory; only the discovered port, version, answer and database
 * name hash are returned. No application/kernel/vault database is opened.
 */
ini_set('display_errors', '0');
ini_set('log_errors', '0');
set_error_handler(static function (): never {
    throw new RuntimeException('PHP_PROBE_WARNING');
});

$result = [
    'schema_version' => 1,
    'passed' => false,
    'scope' => 'Read-only SELECT through installed private PHP PDO_MYSQL to the owned A8 Joomla MariaDB database',
    'profile' => 'DragonhydraGenesisA8Test',
    'sql_mutations_requested' => false,
    'kernel_or_vault_read' => false,
    'credential_values_emitted' => false,
];
$exit = 1;
try {
    if (PHP_SAPI !== 'cli' || PHP_OS_FAMILY !== 'Windows' || count($argv) !== 2) {
        throw new RuntimeException('EXACT_WINDOWS_CLI_ARGUMENTS_REQUIRED');
    }
    $root = dirname(__DIR__, 2);
    if (strcasecmp($root, 'C:\\xampp\\DRAGONHYDRA') !== 0) {
        throw new RuntimeException('EXACT_PROJECT_REQUIRED');
    }
    $profile = $root . '\\build\\workstation\\test-install\\genesis-a8';
    $state = $profile . '\\state data';
    $install = $profile . '\\application files';
    $expectedConfig = realpath($state . '\\workstation.json');
    if ($expectedConfig === false || realpath($argv[1]) !== $expectedConfig) {
        throw new RuntimeException('EXACT_OWNED_CONFIG_REQUIRED');
    }
    $cfg = json_decode(file_get_contents($expectedConfig), true, 512, JSON_THROW_ON_ERROR);
    if (($cfg['service_name'] ?? null) !== 'DragonhydraGenesisA8Test'
        || ($cfg['install_root'] ?? null) !== $install
        || ($cfg['state_root'] ?? null) !== $state) {
        throw new RuntimeException('EXACT_PROFILE_BINDING_REQUIRED');
    }
    $port = filter_var($cfg['database_port'] ?? null, FILTER_VALIDATE_INT,
                       ['options' => ['min_range' => 1024, 'max_range' => 65535]]);
    if ($port === false || $port === (int)($cfg['api_port'] ?? 0)
        || $port === (int)($cfg['web_port'] ?? 0)) {
        throw new RuntimeException('INVALID_OWNED_DATABASE_PORT');
    }
    if (!extension_loaded('pdo_mysql')) {
        throw new RuntimeException('PDO_MYSQL_UNAVAILABLE');
    }
    foreach (['db_name', 'db_user', 'db_password'] as $key) {
        if (!is_string($cfg[$key] ?? null) || $cfg[$key] === '') {
            throw new RuntimeException('REQUIRED_OWNED_CONFIGURATION_UNAVAILABLE');
        }
    }
    // Keep user/database values out of SQL. This fixed literal is the sole SQL
    // statement; it neither reads football records nor changes schemas or data.
    $query = 'SELECT VERSION() AS server_version, 6*7 AS answer, DATABASE() AS database_name';
    $db = new PDO('mysql:host=127.0.0.1;port=' . $port . ';dbname=' . $cfg['db_name'],
                  $cfg['db_user'], $cfg['db_password'], [
        PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION,
        PDO::ATTR_TIMEOUT => 5,
        PDO::ATTR_EMULATE_PREPARES => false,
    ]);
    $row = $db->query($query)->fetch(PDO::FETCH_ASSOC);
    if (!$row || (int)$row['answer'] !== 42
        || !hash_equals($cfg['db_name'], (string)$row['database_name'])) {
        throw new RuntimeException('DATABASE_ASSERTION_FAILED');
    }
    $result += [
        'port' => $port,
        'server_version' => (string)$row['server_version'],
        'answer' => (int)$row['answer'],
        'database_name_sha256' => hash('sha256', (string)$row['database_name']),
        'selected_database_matches_owned_configuration' => true,
        'sql_statement_sha256' => hash('sha256', $query),
        'sql_statements_executed' => 1,
    ];
    $result['passed'] = true;
    $db = null;
    unset($cfg, $row);
    $exit = 0;
} catch (Throwable $error) {
    $allowed = ['EXACT_WINDOWS_CLI_ARGUMENTS_REQUIRED', 'EXACT_PROJECT_REQUIRED',
                'EXACT_OWNED_CONFIG_REQUIRED', 'EXACT_PROFILE_BINDING_REQUIRED',
                'INVALID_OWNED_DATABASE_PORT', 'PDO_MYSQL_UNAVAILABLE',
                'REQUIRED_OWNED_CONFIGURATION_UNAVAILABLE', 'DATABASE_ASSERTION_FAILED',
                'PHP_PROBE_WARNING'];
    $result['error_code'] = in_array($error->getMessage(), $allowed, true)
        ? $error->getMessage() : 'OWNED_DATABASE_READONLY_PROBE_FAILED';
    $result['exception_type'] = get_class($error);
}
restore_error_handler();
echo json_encode($result, JSON_UNESCAPED_SLASHES | JSON_THROW_ON_ERROR), PHP_EOL;
exit($exit);
