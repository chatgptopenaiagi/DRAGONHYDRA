<?php
/** Product-owned CLI provisioning. This file is outside the Joomla document root. */
declare(strict_types=1);

if (PHP_SAPI !== 'cli') { http_response_code(404); exit(1); }
ini_set('display_errors', '0');
require_once __DIR__ . '/CoreNextProfile.php';

function output(array $value): void {
    echo json_encode($value, JSON_THROW_ON_ERROR | JSON_UNESCAPED_SLASHES) . "\n";
}
function slash(string $path): string { return str_replace('\\', '/', $path); }
function samePath(string $left, string $right): bool { return strcasecmp(rtrim(slash($left), '/'), rtrim(slash($right), '/')) === 0; }
function writeAtomic(string $path, string $content): void {
    $temp = $path . '.' . bin2hex(random_bytes(6)) . '.tmp';
    if (file_put_contents($temp, $content, LOCK_EX) !== strlen($content)) { throw new RuntimeException('WRITE_FAILED'); }
    if (!rename($temp, $path)) { @unlink($temp); throw new RuntimeException('CONFIG_COMMIT_FAILED'); }
}
function jsonFile(string $path): array {
    $value = json_decode((string) file_get_contents($path), true, 64, JSON_THROW_ON_ERROR);
    if (!is_array($value)) { throw new RuntimeException('INVALID_CONFIGURATION'); }
    return $value;
}
function identifier(string $value): string {
    if (!preg_match('/^[a-zA-Z][a-zA-Z0-9_]{0,63}$/D', $value)) { throw new RuntimeException('INVALID_DATABASE_IDENTIFIER'); }
    return $value;
}
function pathValue(mixed $value): string {
    if (!is_string($value) || !preg_match('~^(?:[a-zA-Z]:[\\\\/]|/)~', $value)
        || preg_match('/[\x00-\x1f"<>|]/', $value) || preg_match('~(?:^|[\\\\/])\.\.(?:[\\\\/]|$)~', $value)) {
        throw new RuntimeException('INVALID_ABSOLUTE_PATH');
    }
    return rtrim(slash($value), '/');
}
function configuration(string $path): array {
    $cfg = jsonFile($path);
    $cfg = coreNextProfile($cfg);
    foreach (['install_root', 'state_root', 'bridge_secret_path'] as $key) { $cfg[$key] = pathValue($cfg[$key] ?? null); }
    $cfg['payload'] = $cfg['install_root'] . '/web';
    if (!samePath(__DIR__, $cfg['payload'])) { throw new RuntimeException('PAYLOAD_LOCATION_MISMATCH'); }
    if (samePath($cfg['install_root'], $cfg['state_root'])
        || str_starts_with(strtolower($cfg['state_root'] . '/'), strtolower($cfg['payload'] . '/'))) {
        throw new RuntimeException('MUTABLE_STATE_MUST_BE_SEPARATE');
    }
    foreach (['web_port', 'database_port', 'api_port'] as $key) {
        if (filter_var($cfg[$key] ?? null, FILTER_VALIDATE_INT, ['options' => ['min_range' => 1024, 'max_range' => 65535]]) === false) {
            throw new RuntimeException('INVALID_PORT');
        }
        $cfg[$key] = (int) $cfg[$key];
    }
    if (count(array_unique([$cfg['web_port'], $cfg['database_port'], $cfg['api_port']])) !== 3) { throw new RuntimeException('PORTS_MUST_BE_DISTINCT'); }
    $api = parse_url((string) ($cfg['api_base'] ?? ''));
    if (!$api || ($api['scheme'] ?? '') !== 'http' || ($api['host'] ?? '') !== '127.0.0.1'
        || ($api['port'] ?? 80) !== $cfg['api_port'] || ($api['path'] ?? '') !== '/dragon/api/v1'
        || isset($api['user']) || isset($api['pass']) || isset($api['query']) || isset($api['fragment'])) {
        throw new RuntimeException('API_BASE_MUST_SELECT_LOCAL_VERSIONED_KERNEL');
    }
    $cfg['db_name'] = identifier((string) ($cfg['db_name'] ?? ''));
    $cfg['db_user'] = identifier((string) ($cfg['db_user'] ?? ''));
    $cfg['core_db_name'] = identifier((string) ($cfg['core_db_name'] ?? 'dragonhydra_core'));
    $cfg['core_db_user'] = identifier((string) ($cfg['core_db_user'] ?? 'dragonhydra_core'));
    if ($cfg['db_name'] === $cfg['core_db_name'] || $cfg['db_user'] === $cfg['core_db_user'] || in_array('root', [$cfg['db_user'], $cfg['core_db_user']], true)) {
        throw new RuntimeException('SEPARATE_DATABASE_IDENTITIES_REQUIRED');
    }
    foreach (['root_password', 'db_password', 'admin_password'] as $key) {
        if (!is_string($cfg[$key] ?? null) || strlen($cfg[$key]) < 12 || str_contains($cfg[$key], "\0")) { throw new RuntimeException('STRONG_INITIAL_PASSWORD_REQUIRED'); }
    }
    if (isset($cfg['core_db_password']) && (!is_string($cfg['core_db_password']) || strlen($cfg['core_db_password']) < 12 || str_contains($cfg['core_db_password'], "\0"))) {
        throw new RuntimeException('STRONG_CORE_PASSWORD_REQUIRED');
    }
    if (!is_string($cfg['admin_user'] ?? null) || !preg_match('/^[\pL\pN_.@-]{3,100}$/uD', $cfg['admin_user'])
        || !filter_var($cfg['admin_email'] ?? '', FILTER_VALIDATE_EMAIL)
        || !is_string($cfg['site_name'] ?? null) || trim($cfg['site_name']) === '') { throw new RuntimeException('INVALID_SITE_IDENTITY'); }
    foreach (['site', 'mysql-data', 'web-config', 'web-logs', 'web-temp', 'web-sessions'] as $directory) {
        $cfg[str_replace('-', '_', $directory)] = $cfg['state_root'] . '/' . $directory;
    }
    return $cfg;
}
function copyTree(string $source, string $destination): void {
    if (!is_dir($source)) { throw new RuntimeException('JOOMLA_BASE_MISSING'); }
    if (!is_dir($destination) && !mkdir($destination, 0770, true)) { throw new RuntimeException('SITE_DIRECTORY_FAILED'); }
    foreach (new DirectoryIterator($source) as $item) {
        if ($item->isDot()) { continue; }
        if ($item->isLink()) { throw new RuntimeException('SYMLINK_PAYLOAD_DENIED'); }
        $target = $destination . '/' . $item->getFilename();
        if ($item->isDir()) { copyTree($item->getPathname(), $target); }
        elseif (!is_file($target) && !copy($item->getPathname(), $target)) { throw new RuntimeException('SITE_COPY_FAILED'); }
    }
}
function prepare(array $cfg): void {
    foreach (['state_root', 'web_config', 'web_logs', 'web_temp', 'web_sessions'] as $key) {
        if (!is_dir($cfg[$key]) && !mkdir($cfg[$key], 0770, true)) { throw new RuntimeException('STATE_DIRECTORY_FAILED'); }
    }
    // A completed copy marker permits retry after interruption without resurrecting a removed installer.
    $sitePrepared = $cfg['web_config'] . '/site-prepared.json';
    if (!is_file($cfg['site'] . '/configuration.php') && !is_file($sitePrepared)) {
        copyTree($cfg['payload'] . '/joomla-base', $cfg['site']);
        writeAtomic($sitePrepared, json_encode(['prepared_utc' => gmdate('c')], JSON_THROW_ON_ERROR));
    }
    $marker = $cfg['web_config'] . '/database-initializing.json';
    if (!is_dir($cfg['mysql_data'] . '/mysql') && !is_file($marker)) {
        writeAtomic($marker, json_encode(['schema_version' => 1, 'state_root' => $cfg['state_root'], 'database_port' => $cfg['database_port'],
            'phase' => 'fresh_private_datadir', 'created_utc' => gmdate('c')], JSON_THROW_ON_ERROR));
    }
    $p = $cfg['payload'] . '/php'; $a = $cfg['payload'] . '/apache'; $s = $cfg['site']; $c = $cfg['web_config']; $logs = $cfg['web_logs'];
    $php = [
        '; Generated for the selected DRAGONHYDRA instance; no credentials.', 'extension_dir="' . $p . '/ext"',
        'extension=curl', 'extension=fileinfo', 'extension=gd', 'extension=intl', 'extension=mbstring',
        'extension=mysqli', 'extension=openssl', 'extension=pdo_mysql', 'extension=sodium', 'extension=zip',
        'date.timezone=UTC', 'memory_limit=256M', 'max_execution_time=120', 'max_input_time=120',
        'upload_max_filesize=64M', 'post_max_size=64M', 'display_errors=Off', 'log_errors=On',
        'error_log="' . $logs . '/php-error.log"', 'error_reporting=E_ALL', 'expose_php=Off',
        'session.use_strict_mode=1', 'session.cookie_httponly=1', 'session.cookie_samesite=Lax', 'session.name=' . $cfg['cookie_name'],
        'session.save_path="' . $cfg['web_sessions'] . '"', 'sys_temp_dir="' . $cfg['web_temp'] . '"',
        'upload_tmp_dir="' . $cfg['web_temp'] . '"',
    ];
    writeAtomic($c . '/php.ini', implode("\n", $php) . "\n");
    $apache = [
        '# Generated private DRAGONHYDRA Joomla origin; never includes XAMPP configuration.',
        'ServerRoot "' . $a . '"', 'Listen 127.0.0.1:' . $cfg['web_port'], 'ServerName 127.0.0.1:' . $cfg['web_port'],
        'PidFile "' . $c . '/apache.pid"', 'ErrorLog "' . $logs . '/apache-error.log"', 'LogLevel warn',
        'LoadModule authz_core_module modules/mod_authz_core.so', 'LoadModule authz_host_module modules/mod_authz_host.so',
        'LoadModule dir_module modules/mod_dir.so', 'LoadModule mime_module modules/mod_mime.so',
        'LoadModule log_config_module modules/mod_log_config.so', 'LoadModule headers_module modules/mod_headers.so',
        'LoadModule alias_module modules/mod_alias.so', 'LoadModule rewrite_module modules/mod_rewrite.so',
        'LoadModule proxy_module modules/mod_proxy.so', 'LoadModule proxy_http_module modules/mod_proxy_http.so',
        'LoadFile "' . $p . '/php8ts.dll"', 'LoadModule php_module "' . $p . '/php8apache2_4.dll"',
        'PHPIniDir "' . $c . '"', 'TypesConfig "' . $a . '/conf/mime.types"',
        '<FilesMatch "\\.php$">', 'SetHandler application/x-httpd-php', '</FilesMatch>',
        'DirectoryIndex index.php', 'DocumentRoot "' . $s . '"',
        '<Directory />', 'Require all denied', 'AllowOverride None', '</Directory>',
        '<Directory "' . $s . '">', 'AllowOverride None', 'Options -Indexes', 'Require local', '</Directory>',
        '<FilesMatch "^(?:configuration\\.php|\\..*|.*\\.(?:ini|log|sql|bak))$">', 'Require all denied', '</FilesMatch>',
        'ProxyRequests Off', 'ProxyPreserveHost On', 'ProxyPass /dragon/ http://127.0.0.1:' . $cfg['api_port'] . '/dragon/ connectiontimeout=3 timeout=120',
        'ProxyPassReverse /dragon/ http://127.0.0.1:' . $cfg['api_port'] . '/dragon/',
        'ServerTokens Prod', 'ServerSignature Off', 'TraceEnable Off', 'Header always set X-Content-Type-Options nosniff',
    ];
    writeAtomic($c . '/httpd.conf', implode("\n", $apache) . "\n");
    $mysql = ['# Generated private DRAGONHYDRA MariaDB instance.', '[mysqld]',
        'basedir="' . $cfg['payload'] . '/mariadb"', 'datadir="' . $cfg['mysql_data'] . '"',
        'port=' . $cfg['database_port'], 'bind-address=127.0.0.1', 'skip-name-resolve',
        'character-set-server=utf8mb4', 'collation-server=utf8mb4_unicode_ci',
        'max_connections=30', 'innodb_buffer_pool_size=64M', 'performance_schema=OFF',
        'pid-file="' . $c . '/mysql.pid"', 'log-error="' . $logs . '/mysql-error.log"'];
    writeAtomic($c . '/my.ini', implode("\n", $mysql) . "\n");
    output(['action' => 'prepare', 'prepared' => true, 'database_connection_attempted' => false,
        'site' => $cfg['site'], 'configuration_directory' => $c, 'bind_address' => '127.0.0.1']);
}
function rootConnection(array $cfg, bool $allowFresh = false): mysqli {
    try { return new mysqli('127.0.0.1', 'root', $cfg['root_password'], '', $cfg['database_port']); }
    catch (mysqli_sql_exception $failure) {
        $markerFile = $cfg['web_config'] . '/database-initializing.json';
        if (!$allowFresh || $failure->getCode() !== 1045 || !is_file($markerFile)) { throw new RuntimeException('ROOT_DATABASE_AUTHENTICATION_FAILED'); }
        $marker = jsonFile($markerFile);
        if (($marker['phase'] ?? '') !== 'fresh_private_datadir' || !samePath($marker['state_root'] ?? '', $cfg['state_root'])
            || ($marker['database_port'] ?? null) !== $cfg['database_port'] || !is_dir($cfg['mysql_data'] . '/mysql')) {
            throw new RuntimeException('FRESH_DATABASE_MARKER_MISMATCH');
        }
        $db = new mysqli('127.0.0.1', 'root', '', '', $cfg['database_port']);
        $db->set_charset('utf8mb4');
        $password = $db->real_escape_string($cfg['root_password']);
        // mysql_install_db creates root@localhost. Set the authenticated account itself.
        $current = $db->query('SELECT CURRENT_USER()')->fetch_row()[0];
        [$user, $host] = explode('@', $current, 2);
        if ($user !== 'root' || !in_array($host, ['localhost', '127.0.0.1'], true)) { throw new RuntimeException('UNEXPECTED_INITIAL_ROOT_IDENTITY'); }
        // Lock every local bootstrap root identity, not only the account used by TCP.
        foreach ($db->query("SELECT User,Host FROM mysql.user WHERE User='root' OR User=''")->fetch_all(MYSQLI_ASSOC) as $account) {
            $accountHost = $db->real_escape_string($account['Host']);
            if ($account['User'] === 'root' && in_array($account['Host'], ['localhost', '127.0.0.1', '::1'], true)) {
                $db->query("ALTER USER 'root'@'$accountHost' IDENTIFIED BY '$password'");
            } else {
                $db->query("DROP USER IF EXISTS '" . $db->real_escape_string($account['User']) . "'@'$accountHost'");
            }
        }
        $db->close();
        return new mysqli('127.0.0.1', 'root', $cfg['root_password'], '', $cfg['database_port']);
    }
}
function provision(array $cfg): void {
    if (!isset($cfg['core_db_password'])) { throw new RuntimeException('CORE_DATABASE_PASSWORD_REQUIRED'); }
    $db = rootConnection($cfg, true); $db->set_charset('utf8mb4');
    // Also remove anonymous identities if initialization succeeded with a configured password.
    foreach ($db->query("SELECT User,Host FROM mysql.user WHERE User=''")->fetch_all(MYSQLI_ASSOC) as $account) {
        $db->query("DROP USER IF EXISTS ''@'" . $db->real_escape_string($account['Host']) . "'");
    }
    foreach ([[$cfg['db_name'], $cfg['db_user'], $cfg['db_password']], [$cfg['core_db_name'], $cfg['core_db_user'], $cfg['core_db_password']]] as [$name, $user, $password]) {
        $db->query("CREATE DATABASE IF NOT EXISTS `$name` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci");
        $escaped = $db->real_escape_string($password);
        $db->query("CREATE USER IF NOT EXISTS '$user'@'127.0.0.1' IDENTIFIED BY '$escaped'");
        // Do not rotate a pre-existing database password during a repair; verify it below.
        $db->query("GRANT ALL PRIVILEGES ON `$name`.* TO '$user'@'127.0.0.1'");
        $test = new mysqli('127.0.0.1', $user, $password, $name, $cfg['database_port']); $test->close();
    }
    $marker = $cfg['web_config'] . '/database-initializing.json';
    if (is_file($marker)) { unlink($marker); }
    output(['action' => 'provision', 'provisioned' => true, 'administration_schema' => $cfg['db_name'],
        'reserved_core_schema' => $cfg['core_db_name'], 'core_authority_migrated' => false]);
}
function appConnection(array $cfg): mysqli {
    $db = new mysqli('127.0.0.1', $cfg['db_user'], $cfg['db_password'], $cfg['db_name'], $cfg['database_port']);
    $db->set_charset('utf8mb4'); return $db;
}
function runChild(array $cfg, array $arguments, string $name): void {
    $stdout = $cfg['web_logs'] . '/' . $name . '.stdout.log';
    $stderr = $cfg['web_logs'] . '/' . $name . '.stderr.log';
    $process = proc_open(array_merge([PHP_BINARY, '-c', $cfg['web_config'] . '/php.ini'], $arguments),
        [0 => ['file', 'NUL', 'r'], 1 => ['file', $stdout, 'w'], 2 => ['file', $stderr, 'w']], $pipes, $cfg['site'], null, ['bypass_shell' => true]);
    if (!is_resource($process)) { throw new RuntimeException('JOOMLA_CHILD_START_FAILED'); }
    if (proc_close($process) !== 0) { throw new RuntimeException('JOOMLA_' . strtoupper($name) . '_FAILED'); }
}
function extensionRecord(mysqli $db): ?array {
    $result = $db->query("SELECT extension_id,enabled,manifest_cache,params FROM dh_extensions WHERE element='com_dragonhydra' AND type='component'")->fetch_assoc();
    return $result ?: null;
}
function install(array $cfg, string $configPath): void {
    $coreInstalled = is_file($cfg['site'] . '/configuration.php');
    if (!$coreInstalled) {
        if (!is_file($cfg['site'] . '/installation/joomla.php')) { throw new RuntimeException('JOOMLA_INSTALLER_MISSING'); }
        runChild($cfg, [__FILE__, $configPath, '_install-core'], 'core-install');
        if (!is_file($cfg['site'] . '/configuration.php')) { throw new RuntimeException('JOOMLA_INSTALLATION_NOT_CONFIRMED'); }
    }
    $package = $cfg['payload'] . '/extension.zip';
    $hash = hash_file('sha256', $package);
    $receiptPath = $cfg['web_config'] . '/extension-installed.json';
    $receipt = is_file($receiptPath) ? jsonFile($receiptPath) : [];
    $db = appConnection($cfg); $record = extensionRecord($db);
    $changed = !$record || ($receipt['package_sha256'] ?? '') !== $hash;
    if ($changed) {
        // Joomla unpacks beside its input ZIP. Keep installation binaries read-only
        // and give its installer only this verified, product-owned temporary copy.
        $stagedPackage = $cfg['web_temp'] . '/extension-' . bin2hex(random_bytes(12)) . '.zip';
        try {
            if (!copy($package, $stagedPackage) || hash_file('sha256', $stagedPackage) !== $hash) {
                throw new RuntimeException('EXTENSION_STAGING_INTEGRITY_FAILED');
            }
            runChild($cfg, [$cfg['site'] . '/cli/joomla.php', 'extension:install', '--path=' . $stagedPackage, '--no-interaction'], 'extension-install');
        } finally {
            if (is_file($stagedPackage)) { unlink($stagedPackage); }
        }
        $record = extensionRecord($db);
        if (!$record || !(int) $record['enabled']) { throw new RuntimeException('EXTENSION_INSTALLATION_NOT_CONFIRMED'); }
        writeAtomic($receiptPath, json_encode(['package_sha256' => $hash, 'installed_utc' => gmdate('c')], JSON_THROW_ON_ERROR));
    }
    output(['action' => 'install', 'installed' => true, 'core_created' => !$coreInstalled, 'extension_updated' => $changed, 'extension_package_sha256' => $hash]);
}
function configure(array $cfg, string $configPath): void {
    $joomlaConfiguration = $cfg['site'] . '/configuration.php';
    require_once $joomlaConfiguration;
    $site = new \JConfig();
    if ($site->db !== $cfg['db_name'] || $site->user !== $cfg['db_user'] || $site->host !== '127.0.0.1:' . $cfg['database_port']) {
        throw new RuntimeException('CORE_NEXT_JOOMLA_DATABASE_BINDING_MISMATCH');
    }
    if (isset($site->core_next_installation_id) && $site->core_next_installation_id !== $cfg['installation_id']) {
        throw new RuntimeException('CORE_NEXT_JOOMLA_SESSION_BINDING_MISMATCH');
    }
    if (!isset($site->core_next_installation_id)) {
        // Keep Joomla's separate Site/Administrator class seeds; bind its fresh
        // random secret to this installation once, then retain it on repairs.
        $values = get_object_vars($site);
        $values['secret'] = hash_hmac('sha256', $cfg['joomla_session_suffix'], $site->secret);
        $values['core_next_installation_id'] = $cfg['installation_id'];
        $values['core_next_session_suffix'] = $cfg['joomla_session_suffix'];
        $values['cookie_domain'] = ''; $values['cookie_path'] = '/';
        $text = "<?php\nclass JConfig {\n";
        foreach ($values as $key => $value) {
            if (!preg_match('/^[a-zA-Z_][a-zA-Z0-9_]*$/D', $key)) { throw new RuntimeException('INVALID_JOOMLA_CONFIGURATION_PROPERTY'); }
            $text .= 'public $' . $key . ' = ' . var_export($value, true) . ";\n";
        }
        writeAtomic($joomlaConfiguration, $text . "}\n");
    }
    $db = appConnection($cfg); $record = extensionRecord($db);
    if (!$record) { throw new RuntimeException('DRAGONHYDRA_EXTENSION_MISSING'); }
    if (!is_file($cfg['bridge_secret_path'])) { throw new RuntimeException('KERNEL_IDENTITY_BRIDGE_MISSING'); }
    $bridge = jsonFile($cfg['bridge_secret_path']);
    if (!is_string($bridge['secret'] ?? null) || strlen($bridge['secret']) < 32) { throw new RuntimeException('KERNEL_IDENTITY_BRIDGE_INVALID'); }
    $params = json_decode($record['params'], true, 64, JSON_THROW_ON_ERROR) ?: [];
    $params['api_base'] = $cfg['api_base']; $params['bridge_secret_path'] = $cfg['bridge_secret_path'];
    $params['dashboard_url'] = 'http://127.0.0.1:' . $cfg['api_port'] . '/';
    $params['core_next_installation_id'] = $cfg['installation_id'];
    $encoded = json_encode($params, JSON_THROW_ON_ERROR | JSON_UNESCAPED_SLASHES);
    $statement = $db->prepare("UPDATE dh_extensions SET params=? WHERE element='com_dragonhydra' AND type='component'");
    $statement->bind_param('s', $encoded); $statement->execute();
    // Reapply the extension's own idempotent Home/template migration on repair.
    // This child bootstraps the matching Joomla installation, not an arbitrary site.
    runChild($cfg, [__FILE__, $configPath, '_configure-frontend'], 'frontend-configure');
    output(['action' => 'configure', 'configured' => true, 'api_base' => $cfg['api_base'], 'configuration_sha256' => hash('sha256', $encoded)]);
}
function status(array $cfg): void {
    $manifest = jsonFile($cfg['payload'] . '/payload-manifest.json');
    $result = ['action' => 'status', 'php_version' => PHP_VERSION, 'php_thread_safe' => (bool) PHP_ZTS,
        'source_sha' => $manifest['source_sha'] ?? null, 'site_configured' => is_file($cfg['site'] . '/configuration.php'),
        'joomla_url' => 'http://127.0.0.1:' . $cfg['web_port'] . '/', 'administration_url' => 'http://127.0.0.1:' . $cfg['web_port'] . '/administrator/',
        'api_base' => $cfg['api_base'], 'sports_database_backend' => 'sqlite', 'reserved_core_authority_active' => false];
    $db = appConnection($cfg); $result['database_version'] = $db->server_info;
    if ($result['site_configured']) {
        $record = extensionRecord($db);
        if ($record) {
            $cached = json_decode($record['manifest_cache'], true);
            $result['extension'] = ['identity' => 'com_dragonhydra', 'enabled' => (bool) $record['enabled'],
                'version' => $cached['version'] ?? null, 'configuration_sha256' => hash('sha256', $record['params'])];
        }
    }
    output($result);
}

try {
    if (!isset($argv[1], $argv[2]) || !is_file($argv[1])) { throw new RuntimeException('USAGE_MANAGE_CONFIGURATION_ACTION'); }
    $configPath = pathValue((string) realpath($argv[1]));
    $cfg = configuration($configPath); $action = $argv[2];
    if ($action === 'prepare') { prepare($cfg); exit; }
    mysqli_report(MYSQLI_REPORT_ERROR | MYSQLI_REPORT_STRICT);
    if ($action === 'provision') { provision($cfg); }
    elseif ($action === 'install') { install($cfg, $configPath); }
    elseif ($action === 'configure') { configure($cfg, $configPath); }
    elseif ($action === 'status') { status($cfg); }
    elseif ($action === 'shutdown') { $db = rootConnection($cfg); $db->query('SHUTDOWN'); output(['action' => 'shutdown', 'shutdown_requested' => true]); }
    elseif ($action === '_configure-frontend') {
        if (!is_file($cfg['site'] . '/configuration.php')) { throw new RuntimeException('JOOMLA_CONFIGURATION_MISSING'); }
        define('_JEXEC', 1); define('JPATH_BASE', $cfg['site']);
        require_once JPATH_BASE . '/includes/defines.php';
        require_once JPATH_BASE . '/includes/framework.php';
        $container = \Joomla\CMS\Factory::getContainer();
        $container->alias('session', 'session.cli')
            ->alias(\Joomla\CMS\Session\Session::class, 'session.cli')
            ->alias(\Joomla\Session\Session::class, 'session.cli')
            ->alias(\Joomla\Session\SessionInterface::class, 'session.cli');
        \Joomla\CMS\Factory::$application = $container->get(\Joomla\Console\Application::class);
        $setup = JPATH_ADMINISTRATOR . '/components/com_dragonhydra/src/Service/FrontendSetup.php';
        if (!is_file($setup)) { throw new RuntimeException('WORKSPACE_FRONTEND_SETUP_MISSING'); }
        require_once $setup;
        output(['action' => 'configure-frontend', 'frontend' => \Dragonhydra\Component\Dragonhydra\Administrator\Service\FrontendSetup::apply()]);
    }
    elseif ($action === '_install-core') {
        if (is_file($cfg['site'] . '/configuration.php')) { output(['already_installed' => true]); exit; }
        $options = ['site-name' => $cfg['site_name'], 'admin-user' => 'DRAGONHYDRA Administrator',
            'admin-username' => $cfg['admin_user'], 'admin-password' => $cfg['admin_password'], 'admin-email' => $cfg['admin_email'],
            'db-type' => 'mysqli', 'db-host' => '127.0.0.1:' . $cfg['database_port'], 'db-user' => $cfg['db_user'],
            'db-pass' => $cfg['db_password'], 'db-name' => $cfg['db_name'], 'db-prefix' => 'dh_', 'db-encryption' => '0', 'public-folder' => ''];
        $argv = [$cfg['site'] . '/installation/joomla.php', 'install', '--no-interaction'];
        foreach ($options as $name => $value) { $argv[] = '--' . $name . '=' . $value; }
        $_SERVER['argv'] = $argv; $_SERVER['argc'] = count($argv);
        require $cfg['site'] . '/installation/joomla.php';
    } else { throw new RuntimeException('UNKNOWN_WORKSTATION_WEB_ACTION'); }
} catch (Throwable $failure) {
    // Never echo vendor messages: they may contain connection strings or credentials.
    $code = $failure instanceof RuntimeException && preg_match('/^[A-Z0-9_]+$/D', $failure->getMessage()) ? $failure->getMessage() : 'WORKSTATION_WEB_OPERATION_FAILED';
    output(['ok' => false, 'error' => ['code' => $code, 'operation' => $argv[2] ?? null]]);
    exit(1);
}
