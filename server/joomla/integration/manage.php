<?php
/** Private integration harness. CLI-only; never copied inside the Joomla webroot. */
if (PHP_SAPI !== 'cli') { exit(1); }
$cfg = json_decode(file_get_contents($argv[1]), true, 64, JSON_THROW_ON_ERROR);
$action = $argv[2] ?? '';
mysqli_report(MYSQLI_REPORT_ERROR | MYSQLI_REPORT_STRICT);

if ($action === 'install') {
    $options = [
        'site-name' => 'DRAGONHYDRA integration', 'admin-user' => 'DRAGONHYDRA Integration Administrator',
        'admin-username' => $cfg['admin_username'], 'admin-password' => $cfg['admin_password'],
        'admin-email' => 'integration@dragonhydra.invalid', 'db-type' => 'mysqli',
        'db-host' => '127.0.0.1:' . $cfg['database_port'], 'db-user' => 'dragonhydra_admin',
        'db-pass' => $cfg['database_password'], 'db-name' => 'dragonhydra_admin', 'db-prefix' => 'dh_',
        'db-encryption' => '0', 'public-folder' => '',
    ];
    $argv = [$cfg['site'] . '/installation/joomla.php', 'install', '--no-interaction'];
    foreach ($options as $name => $value) { $argv[] = '--' . $name . '=' . $value; }
    $_SERVER['argv'] = $argv;
    $_SERVER['argc'] = count($argv);
    require $cfg['site'] . '/installation/joomla.php';
    exit;
}

$db = new mysqli('127.0.0.1', 'root', $cfg['root_password'], '', $cfg['database_port']);
$db->set_charset('utf8mb4');
if ($action === 'provision') {
    $db->query('CREATE DATABASE IF NOT EXISTS dragonhydra_admin CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci');
    $password = $db->real_escape_string($cfg['database_password']);
    $db->query("CREATE USER IF NOT EXISTS 'dragonhydra_admin'@'127.0.0.1' IDENTIFIED BY '$password'");
    $db->query("GRANT ALL ON dragonhydra_admin.* TO 'dragonhydra_admin'@'127.0.0.1'");
    echo json_encode(['database' => 'dragonhydra_admin', 'port' => $cfg['database_port'], 'provisioned' => true]) . "\n";
} elseif ($action === 'configure') {
    $db->select_db('dragonhydra_admin');
    $params = json_encode(['api_base' => $cfg['api_base'], 'bridge_secret_path' => $cfg['bridge_secret_path'], 'dashboard_url' => preg_replace('~/dragon/api/v1$~', '/', $cfg['api_base'])], JSON_THROW_ON_ERROR | JSON_UNESCAPED_SLASHES);
    $stmt = $db->prepare("UPDATE dh_extensions SET params=? WHERE element='com_dragonhydra' AND type='component'");
    $stmt->bind_param('s', $params); $stmt->execute();
    $group = $db->query("SELECT id,lft,rgt FROM dh_usergroups WHERE title='DRAGONHYDRA Reader'")->fetch_assoc();
    if (!$group || (int) $group['rgt'] === 0) {
        // The existing Manager group supplies administration login; component ACL denies mutation below.
        $db->begin_transaction();
        $boundary = (int) $db->query('SELECT rgt FROM dh_usergroups WHERE id=6 FOR UPDATE')->fetch_row()[0];
        $db->query('UPDATE dh_usergroups SET rgt=rgt+2 WHERE rgt>=' . $boundary);
        $db->query('UPDATE dh_usergroups SET lft=lft+2 WHERE lft>' . $boundary);
        if ($group) {
            $db->query('UPDATE dh_usergroups SET lft=' . $boundary . ',rgt=' . ($boundary+1) . ' WHERE id=' . (int) $group['id']);
        } else {
            $db->query("INSERT INTO dh_usergroups(parent_id,lft,rgt,title) VALUES(6,$boundary," . ($boundary+1) . ",'DRAGONHYDRA Reader')");
            $group = ['id' => $db->insert_id];
        }
        $db->commit();
    }
    $readerId = (int) $group['id'];
    $password = password_hash($cfg['reader_password'], PASSWORD_BCRYPT);
    $stmt = $db->prepare("SELECT id FROM dh_users WHERE username=?");
    $stmt->bind_param('s', $cfg['reader_username']); $stmt->execute(); $reader = $stmt->get_result()->fetch_assoc();
    if (!$reader) {
        $stmt = $db->prepare("INSERT INTO dh_users(name,username,email,password,block,sendEmail,registerDate,params) VALUES('DRAGONHYDRA Reader',?,'reader@dragonhydra.invalid',?,0,0,UTC_TIMESTAMP(),'{}')");
        $stmt->bind_param('ss', $cfg['reader_username'], $password); $stmt->execute();
        $userId = $db->insert_id;
        $stmt = $db->prepare('INSERT INTO dh_user_usergroup_map(user_id,group_id) VALUES(?,?)');
        $stmt->bind_param('ii', $userId, $readerId); $stmt->execute();
    }
    $rules = json_encode(['core.manage' => [(string) $readerId => 1], 'dragonhydra.import' => [(string) $readerId => 0, '8' => 1]]);
    $stmt = $db->prepare("UPDATE dh_assets SET rules=? WHERE name='com_dragonhydra'");
    $stmt->bind_param('s', $rules); $stmt->execute();
    echo json_encode(['configured' => true, 'reader_group' => $readerId, 'api_base' => $cfg['api_base']]) . "\n";
} elseif ($action === 'status') {
    $db->select_db('dragonhydra_admin');
    $extensions = $db->query("SELECT extension_id,type,element,enabled,manifest_cache,params FROM dh_extensions WHERE element IN ('com_dragonhydra','pkg_dragonhydra') ORDER BY type")->fetch_all(MYSQLI_ASSOC);
    foreach ($extensions as &$extension) {
        $manifest = json_decode($extension['manifest_cache'], true);
        $extension['version'] = $manifest['version'] ?? null;
        $extension['configuration_sha256'] = hash('sha256', $extension['params']);
        unset($extension['manifest_cache'], $extension['params']);
    }
    unset($extension);
    $users = (int) $db->query('SELECT COUNT(*) FROM dh_users')->fetch_row()[0];
    echo json_encode(['database_version' => $db->server_info, 'extensions' => $extensions, 'user_count' => $users]) . "\n";
} elseif ($action === 'shutdown') {
    $db->query('SHUTDOWN');
    echo "Owned MariaDB shutdown requested.\n";
} else {
    throw new RuntimeException('UNKNOWN_INTEGRATION_ACTION');
}
