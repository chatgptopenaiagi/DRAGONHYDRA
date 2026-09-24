<?php
declare(strict_types=1);
// Local experiment helper. Never prints passwords or root account details.
mysqli_report(MYSQLI_REPORT_ERROR | MYSQLI_REPORT_STRICT);
$secretPath = __DIR__ . '/credentials.local.txt';
try {
    if (!is_file($secretPath) || filesize($secretPath) !== 0) {
        throw new RuntimeException('Expected an empty, ACL-protected credentials file.');
    }
    $db = new mysqli('127.0.0.1', 'root', '', '', 3306);
    $db->set_charset('utf8mb4');
    if ((int) $db->query("SELECT COUNT(*) FROM information_schema.SCHEMATA WHERE SCHEMA_NAME='joomla_codex_lab'")->fetch_row()[0] !== 0
        || (int) $db->query("SELECT COUNT(*) FROM mysql.user WHERE User='joomla_codex'")->fetch_row()[0] !== 0) {
        throw new RuntimeException('Database/account collision; refusing to overwrite.');
    }
    $password = static fn(): string => 'Aa9!' . rtrim(strtr(base64_encode(random_bytes(32)), '+/', '-_'), '=');
    $secrets = [
        'warnings' => ['LOCAL TEST SECRET', 'DO NOT COMMIT', 'DO NOT COPY TO WEB ROOT'],
        'created_utc' => gmdate('c'),
        'site_url' => 'http://localhost/joomla-codex-lab/',
        'db_host' => '127.0.0.1',
        'db_port' => 3306,
        'db_name' => 'joomla_codex_lab',
        'db_user' => 'joomla_codex',
        'db_password' => $password(),
        'db_prefix' => 'j' . bin2hex(random_bytes(3)) . '_',
        'admin_name' => 'Codex Laboratory Operator',
        'admin_username' => 'lab_operator_' . bin2hex(random_bytes(4)),
        'admin_email' => 'operator@joomla-codex.test',
        'admin_password' => $password(),
    ];
    if (file_put_contents($secretPath, json_encode($secrets, JSON_PRETTY_PRINT | JSON_THROW_ON_ERROR) . "\n", LOCK_EX) === false) {
        throw new RuntimeException('Cannot persist credentials; aborting.');
    }
    $db->query('CREATE DATABASE `joomla_codex_lab` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci');
    $escaped = $db->real_escape_string($secrets['db_password']);
    $db->query("CREATE USER 'joomla_codex'@'localhost' IDENTIFIED BY '$escaped'");
    // Escape underscores so the database grant matches this exact database only.
    $db->query("GRANT ALL PRIVILEGES ON `joomla\\_codex\\_lab`.* TO 'joomla_codex'@'localhost'");
    $app = new mysqli('127.0.0.1', $secrets['db_user'], $secrets['db_password'], $secrets['db_name'], 3306);
    $result = [
        'server_version' => $app->server_info,
        'database' => $app->query('SELECT DATABASE()')->fetch_row()[0],
        'matched_account' => $app->query('SELECT CURRENT_USER()')->fetch_row()[0],
        'prefix' => $secrets['db_prefix'],
        'schema_grants' => $db->query("SELECT TABLE_SCHEMA,PRIVILEGE_TYPE,IS_GRANTABLE FROM information_schema.SCHEMA_PRIVILEGES WHERE GRANTEE=\"'joomla_codex'@'localhost'\"")->fetch_all(MYSQLI_ASSOC),
        'global_privileges' => $db->query("SELECT PRIVILEGE_TYPE,IS_GRANTABLE FROM information_schema.USER_PRIVILEGES WHERE GRANTEE=\"'joomla_codex'@'localhost'\"")->fetch_all(MYSQLI_ASSOC),
    ];
    file_put_contents(__DIR__ . '/evidence/database-provision.json', json_encode($result, JSON_PRETTY_PRINT | JSON_THROW_ON_ERROR));
    echo "Dedicated database and localhost account created; application connection verified.\n";
} catch (Throwable $e) {
    // Avoid logging exception text from SQL that might contain generated credentials.
    fwrite(STDERR, 'Provisioning failed: ' . get_class($e) . ', code ' . $e->getCode() . ". No existing objects were dropped.\n");
    exit(1);
}
