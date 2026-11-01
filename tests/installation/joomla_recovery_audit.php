<?php
declare(strict_types=1);

/** Read-only, credential-redacted audit of the original test workstation only.
 * Execute outside the document root with its installed private PHP configuration.
 * This helper never authenticates a session, resets a password, or runs SQL writes.
 */
ini_set('display_errors', '0');
ini_set('log_errors', '0');
error_reporting(0);
ob_start();
$result = [
    'schema_version' => 1,
    'passed' => false,
    'scope' => 'Original DragonhydraWorkstationTest installation only',
    'keys_read_in_memory' => false,
    'output_secrets' => false,
    'sql_mutations_requested' => false,
    'session_or_user_mutations_requested' => false,
    'kernel_or_vault_read' => false,
    'stage' => 'scope',
];
$exitCode = 1;

function identifier(string $value): string
{
    if (!preg_match('/^[A-Za-z0-9_]+$/D', $value)) {
        throw new RuntimeException('INVALID_IDENTIFIER');
    }
    return '`' . $value . '`';
}

function selectRows(PDO $db, string $sql, array $parameters = []): array
{
    if (!preg_match('/^\s*(SELECT|SHOW)\b/i', $sql) || str_contains($sql, ';')) {
        throw new RuntimeException('READ_ONLY_SQL_REQUIRED');
    }
    $statement = $db->prepare($sql);
    $statement->execute($parameters);
    return $statement->fetchAll(PDO::FETCH_ASSOC);
}

function publicUrl(mixed $value): ?string
{
    if (!is_string($value)) {
        return null;
    }
    $parsed = parse_url($value);
    if (!$parsed || !in_array($parsed['scheme'] ?? '', ['http', 'https'], true)
        || isset($parsed['user']) || isset($parsed['pass']) || isset($parsed['query']) || isset($parsed['fragment'])) {
        return null;
    }
    return ($parsed['scheme'] ?? '') . '://' . ($parsed['host'] ?? '')
        . (isset($parsed['port']) ? ':' . (int) $parsed['port'] : '') . ($parsed['path'] ?? '');
}

function connectDatabase(string $host, int $port, string $name, string $user, string $password): PDO
{
    identifier($name);
    if (!in_array($host, ['127.0.0.1', 'localhost', '::1'], true) || $port !== 18741) {
        throw new RuntimeException('EXACT_DATABASE_BINDING_REQUIRED');
    }
    return new PDO('mysql:host=' . $host . ';port=' . $port . ';dbname=' . $name . ';charset=utf8mb4', $user, $password, [
        PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION,
        PDO::ATTR_TIMEOUT => 5,
        PDO::ATTR_EMULATE_PREPARES => false,
    ]);
}

try {
    if (PHP_SAPI !== 'cli' || PHP_OS_FAMILY !== 'Windows' || count($argv) !== 1) {
        throw new RuntimeException('WINDOWS_CLI_NO_ARGUMENTS_REQUIRED');
    }
    $root = dirname(__DIR__, 2);
    if (strcasecmp(str_replace('/', '\\', $root), 'C:\\xampp\\DRAGONHYDRA') !== 0) {
        throw new RuntimeException('EXACT_REPOSITORY_REQUIRED');
    }
    $state = $root . '/build/workstation/test-install/state data';
    $site = $state . '/site';
    $cfg = json_decode(file_get_contents($state . '/workstation.json'), true, 512, JSON_THROW_ON_ERROR);
    $normal = static fn(string $path): string => strtolower(str_replace('\\', '/', rtrim($path, '/\\')));
    if (($cfg['service_name'] ?? '') !== 'DragonhydraWorkstationTest'
        || $normal((string) ($cfg['state_root'] ?? '')) !== $normal($state)
        || (int) ($cfg['web_port'] ?? 0) !== 18740
        || (int) ($cfg['api_port'] ?? 0) !== 18744
        || (int) ($cfg['database_port'] ?? 0) !== 18741) {
        throw new RuntimeException('EXACT_WORKSTATION_BINDING_REQUIRED');
    }
    $result['keys_read_in_memory'] = true;
    $result['binding'] = ['service' => $cfg['service_name'], 'site' => $site,
        'web_port' => 18740, 'backend_port' => 18744, 'database_port' => 18741];
    $result['stage'] = 'configuration';
    define('_JEXEC', 1);
    define('JPATH_BASE', $site);
    require_once $site . '/includes/defines.php';
    require_once $site . '/configuration.php';
    $joomla = new JConfig();
    $host = (string) $joomla->host;
    $port = 18741;
    if (preg_match('/^(127\.0\.0\.1|localhost):(\d+)$/D', $host, $parts)) {
        $host = $parts[1];
        $port = (int) $parts[2];
    }
    $prefix = (string) $joomla->dbprefix;
    identifier($prefix . 'users');
    $result['stage'] = 'joomla_database';
    $db = connectDatabase($host, $port, (string) $joomla->db, (string) $joomla->user, (string) $joomla->password);
    $identity = selectRows($db, 'SELECT @@port AS port, @@datadir AS datadir, VERSION() AS version, DATABASE() AS selected_database')[0];
    $result['database'] = $identity + ['configuration_database_matches' => hash_equals((string) $joomla->db, (string) $identity['selected_database']),
        'expected_port_matches' => (int) $identity['port'] === 18741, 'table_prefix' => $prefix];
    if (!$result['database']['configuration_database_matches'] || !$result['database']['expected_port_matches']) {
        throw new RuntimeException('DATABASE_IDENTITY_MISMATCH');
    }
    $tables = selectRows($db, 'SELECT TABLE_NAME, ENGINE FROM information_schema.TABLES WHERE TABLE_SCHEMA = ? ORDER BY TABLE_NAME', [(string) $joomla->db]);
    $result['joomla_tables'] = $tables;
    $result['stage'] = 'accounts';
    $accounts = selectRows($db, 'SELECT u.id, u.username, u.block, u.activation, u.requireReset, g.id AS group_id, g.title AS group_title '
        . 'FROM ' . identifier($prefix . 'users') . ' u LEFT JOIN ' . identifier($prefix . 'user_usergroup_map') . ' m ON m.user_id=u.id '
        . 'LEFT JOIN ' . identifier($prefix . 'usergroups') . ' g ON g.id=m.group_id ORDER BY u.id, g.id');
    $users = [];
    foreach ($accounts as $row) {
        $id = (int) $row['id'];
        if (!isset($users[$id])) {
            $users[$id] = ['id' => $id, 'username' => (string) $row['username'], 'blocked' => (bool) $row['block'],
                'activation_present' => $row['activation'] !== '', 'require_reset' => (bool) $row['requireReset'], 'groups' => []];
        }
        if ($row['group_id'] !== null) {
            $users[$id]['groups'][] = ['id' => (int) $row['group_id'], 'title' => (string) $row['group_title']];
        }
    }
    $result['administrator_accounts'] = array_values(array_filter($users, static function (array $user) use ($cfg): bool {
        return $user['username'] === ($cfg['admin_user'] ?? '')
            || count(array_filter($user['groups'], static fn(array $group): bool => (bool) preg_match('/super|admin|manager/i', $group['title']))) > 0;
    }));
    $result['administrator_inventory_scope'] = 'Provisioned identity plus accounts mapped to administrator/manager/super-user named groups; runtime Joomla ACL is verified separately';
    $result['stage'] = 'password_verification';
    // Load Joomla libraries and password-handler DI only. Do not execute a CMS
    // application or create a session; zero user ID suppresses password rehash/save.
    require_once $site . '/libraries/bootstrap.php';
    ini_set('display_errors', '0');
    ini_set('log_errors', '0');
    error_reporting(0);
    $candidate = selectRows($db, 'SELECT id, password FROM ' . identifier($prefix . 'users') . ' WHERE username = ?', [(string) ($cfg['admin_user'] ?? '')]);
    $result['password_verification'] = ['candidate_source' => 'Existing owned workstation configuration in memory',
        'account_exists' => count($candidate) === 1, 'verified_with_joomla' => false, 'rehash_disabled_user_id' => 0];
    if (count($candidate) === 1 && is_string($cfg['admin_password'] ?? null)) {
        $result['password_verification']['verified_with_joomla'] = \Joomla\CMS\User\UserHelper::verifyPassword($cfg['admin_password'], $candidate[0]['password'], 0);
    }
    unset($candidate);
    $result['stage'] = 'plugins_sessions_extensions';
    $result['authentication_and_user_plugins'] = selectRows($db, 'SELECT extension_id, element, folder, enabled, client_id FROM '
        . identifier($prefix . 'extensions') . " WHERE type='plugin' AND folder IN ('authentication','user','multifactorauth') ORDER BY folder, element");
    $result['session_configuration'] = ['handler' => (string) ($joomla->session_handler ?? ''),
        'cookie_domain' => (string) ($joomla->cookie_domain ?? ''), 'cookie_path' => (string) ($joomla->cookie_path ?? ''),
        'force_ssl' => (int) ($joomla->force_ssl ?? 0), 'shared_session' => (bool) ($joomla->shared_session ?? false),
        'lifetime_minutes' => (int) ($joomla->lifetime ?? 0), 'php_save_path' => (string) ini_get('session.save_path'),
        'php_httponly' => (bool) ini_get('session.cookie_httponly'), 'php_samesite' => (string) ini_get('session.cookie_samesite'),
        'php_strict_mode' => (bool) ini_get('session.use_strict_mode')];
    $result['session_table_schema'] = selectRows($db, 'SHOW COLUMNS FROM ' . identifier($prefix . 'session'));
    $result['session_counts'] = selectRows($db, 'SELECT client_id, guest, COUNT(*) AS rows_count FROM ' . identifier($prefix . 'session') . ' GROUP BY client_id, guest ORDER BY client_id, guest');
    $extensions = selectRows($db, 'SELECT * FROM ' . identifier($prefix . 'extensions') . " WHERE element='com_dragonhydra' AND type='component'");
    $result['component_registration'] = [];
    foreach ($extensions as $extension) {
        $manifest = json_decode((string) ($extension['manifest_cache'] ?? '{}'), true) ?: [];
        $params = json_decode((string) ($extension['params'] ?? '{}'), true) ?: [];
        $bridgePath = (string) ($params['bridge_secret_path'] ?? '');
        $result['component_registration'][] = ['extension_id' => (int) $extension['extension_id'], 'name' => (string) $extension['name'],
            'element' => (string) $extension['element'], 'client_id' => (int) $extension['client_id'], 'enabled' => (bool) $extension['enabled'],
            'namespace' => (string) ($extension['namespace'] ?? $manifest['namespace'] ?? ''), 'manifest_version' => (string) ($manifest['version'] ?? ''),
            'params' => ['api_base' => publicUrl($params['api_base'] ?? null), 'dashboard_url' => publicUrl($params['dashboard_url'] ?? null),
                'bridge_secret_path' => $bridgePath, 'bridge_file_exists' => is_file($bridgePath), 'bridge_file_readable_from_cli' => is_readable($bridgePath)]];
    }
    $result['component_menu'] = selectRows($db, 'SELECT id, menutype, title, alias, link, type, published, parent_id, component_id, access, client_id FROM '
        . identifier($prefix . 'menu') . " WHERE client_id=1 AND (link LIKE 'index.php?option=com_dragonhydra%' OR link LIKE 'option=com_dragonhydra%') ORDER BY id");
    $result['component_and_root_asset_rules'] = selectRows($db, 'SELECT id, parent_id, name, rules FROM '
        . identifier($prefix . 'assets') . " WHERE name IN ('root.1','com_dragonhydra') ORDER BY id");
    $manifestXml = simplexml_load_file($site . '/administrator/components/com_dragonhydra/dragonhydra.xml');
    $result['installed_manifest'] = ['version' => (string) $manifestXml->version, 'namespace' => (string) $manifestXml->namespace,
        'namespace_path' => (string) $manifestXml->namespace['path'], 'type' => (string) $manifestXml['type']];
    $result['stage'] = 'reserved_core_database';
    $core = connectDatabase('127.0.0.1', 18741, (string) $cfg['core_db_name'], (string) $cfg['core_db_user'], (string) $cfg['core_db_password']);
    $result['core_database'] = ['name' => (string) $cfg['core_db_name'], 'sports_authority' => 'SQLite backend, not this reserved MariaDB database', 'tables' => []];
    foreach (selectRows($core, 'SELECT TABLE_NAME, TABLE_TYPE FROM information_schema.TABLES WHERE TABLE_SCHEMA = ? ORDER BY TABLE_NAME', [(string) $cfg['core_db_name']]) as $table) {
        $count = selectRows($core, 'SELECT COUNT(*) AS rows_count FROM ' . identifier((string) $table['TABLE_NAME']))[0]['rows_count'];
        $result['core_database']['tables'][] = ['name' => (string) $table['TABLE_NAME'], 'type' => (string) $table['TABLE_TYPE'], 'rows' => (int) $count];
    }
    $result['stage'] = 'complete';
    $result['passed'] = true;
    $exitCode = 0;
} catch (Throwable $error) {
    $result['exception_class'] = get_class($error);
    $result['exception_code'] = (string) $error->getCode();
    $result['error'] = 'SCOPED_READONLY_AUDIT_FAILED';
}
// Suppress library output and leave only the explicit safe allowlist above.
while (ob_get_level() > 0) {
    ob_end_clean();
}
echo json_encode($result, JSON_UNESCAPED_SLASHES | JSON_THROW_ON_ERROR), PHP_EOL;
exit($exitCode);
