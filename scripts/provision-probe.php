<?php
declare(strict_types=1);
// One-time provisioning only. Runtime Python never uses root or Joomla credentials.
mysqli_report(MYSQLI_REPORT_ERROR | MYSQLI_REPORT_STRICT);
$root = dirname(__DIR__);
$secretPath = $root . '/runtime/secrets/dragonhydra-probe.local.json';
try {
    if (file_exists($secretPath)) {
        throw new RuntimeException('Existing probe credential file: refusing overwrite.');
    }
    $db = new mysqli('127.0.0.1', 'root', '', '', 3306);
    if ((int)$db->query("SELECT COUNT(*) FROM mysql.user WHERE User='dragonhydra_probe'")->fetch_row()[0] !== 0) {
        throw new RuntimeException('Existing probe account: refusing modification.');
    }
    if ((int)$db->query("SELECT COUNT(*) FROM information_schema.SCHEMATA WHERE SCHEMA_NAME='joomla_codex_lab'")->fetch_row()[0] !== 1) {
        throw new RuntimeException('Controlled Joomla source database is absent.');
    }
    $password = 'Aa9!' . rtrim(strtr(base64_encode(random_bytes(32)), '+/', '-_'), '=');
    $secrets = [
        'notice' => ['LOCAL TEST SECRET', 'DO NOT COMMIT', 'DO NOT COPY TO WEB ROOT'],
        'purpose' => 'DRAGONHYDRA genesis SELECT-only XAMPP capability proof',
        'created_utc' => gmdate('c'),
        'username' => 'dragonhydra_probe',
        'password' => $password,
    ];
    $stream = fopen($secretPath, 'x');
    if ($stream === false) {
        throw new RuntimeException('Cannot create protected credential file.');
    }
    fwrite($stream, json_encode($secrets, JSON_PRETTY_PRINT | JSON_THROW_ON_ERROR) . "\n");
    fclose($stream);
    $escaped = $db->real_escape_string($password);
    $db->query("CREATE USER 'dragonhydra_probe'@'localhost' IDENTIFIED BY '$escaped'");
    $db->query("GRANT SELECT ON `joomla\\_codex\\_lab`.* TO 'dragonhydra_probe'@'localhost'");
    $grants = $db->query("SELECT TABLE_SCHEMA,PRIVILEGE_TYPE,IS_GRANTABLE FROM information_schema.SCHEMA_PRIVILEGES WHERE GRANTEE=\"'dragonhydra_probe'@'localhost'\"")->fetch_all(MYSQLI_ASSOC);
    echo json_encode([
        'created_utc' => gmdate('c'),
        'account' => 'dragonhydra_probe@localhost',
        'grants' => $grants,
        'credential_file' => 'runtime/secrets/dragonhydra-probe.local.json',
        'joomla_data_modified' => false,
        'root_password_changed' => false,
    ], JSON_PRETTY_PRINT | JSON_THROW_ON_ERROR) . "\n";
} catch (Throwable $error) {
    // SQL error text could contain credentials, so never echo it.
    fwrite(STDERR, 'Provision failed (' . get_class($error) . ', code ' . $error->getCode() . "). Check collision/prerequisite state; nothing was dropped.\n");
    exit(1);
}
