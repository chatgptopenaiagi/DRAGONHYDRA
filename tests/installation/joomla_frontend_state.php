<?php
/** Read-only, fixed-profile presentation snapshot; no credentials are emitted. */
declare(strict_types=1);
if (PHP_SAPI !== 'cli') { exit(1); }
define('_JEXEC', 1);
$root = dirname(__DIR__, 2);
$state = $root . '/build/workstation/test-install/state data';
$cfg = json_decode(file_get_contents($state . '/workstation.json'), true, 64, JSON_THROW_ON_ERROR);
if ($cfg['service_name'] !== 'DragonhydraWorkstationTest' || $cfg['web_port'] !== 18740 || $cfg['api_port'] !== 18744) { exit(2); }
require $state . '/site/configuration.php';
$site = new JConfig();
$prefix = $site->dbprefix;
if (!preg_match('/^[A-Za-z0-9_]+$/D', $prefix)) { exit(3); }
try {
    $db = new PDO('mysql:host=127.0.0.1;port=' . $cfg['database_port'] . ';dbname=' . $site->db . ';charset=utf8mb4', $site->user, $site->password, [PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION]);
    $select = static fn(string $sql): array => $db->query($sql)->fetchAll(PDO::FETCH_ASSOC);
    $record = ['schema_version' => 1, 'passed' => true, 'verified_at' => gmdate('c'),
        'service' => $cfg['service_name'], 'web_port' => 18740, 'api_port' => 18744,
        'menus' => $select("SELECT id,title,alias,menutype,link,type,home,published,language,client_id,parent_id,template_style_id,access,SHA2(params,256) params_sha256 FROM {$prefix}menu ORDER BY id"),
        'modules' => $select("SELECT id,title,module,position,published,access,client_id,SHA2(params,256) params_sha256,SHA2(content,256) content_sha256 FROM {$prefix}modules ORDER BY id"),
        'module_assignments' => $select("SELECT moduleid,menuid FROM {$prefix}modules_menu ORDER BY moduleid,menuid"),
        'template_styles' => $select("SELECT id,template,client_id,home,title,SHA2(params,256) params_sha256 FROM {$prefix}template_styles ORDER BY id"),
        'component' => $select("SELECT extension_id,element,enabled,client_id,SHA2(params,256) params_sha256,manifest_cache FROM {$prefix}extensions WHERE element='com_dragonhydra' AND type='component'"),
        'articles' => $select("SELECT id,title,state,catid,SHA2(introtext,256) intro_sha256,SHA2(`fulltext`,256) body_sha256 FROM {$prefix}content ORDER BY id"),
        'user_identity_fingerprints' => $select("SELECT id,username,block,SHA2(password,256) password_fingerprint FROM {$prefix}users ORDER BY id"),
        'user_groups' => $select("SELECT user_id,group_id FROM {$prefix}user_usergroup_map ORDER BY user_id,group_id"),
        'secrets_emitted' => false, 'database_mutation' => false];
    foreach ($record['component'] as &$extension) {
        $extension['version'] = json_decode($extension['manifest_cache'], true)['version'] ?? null;
        unset($extension['manifest_cache']);
    }
    unset($extension);
    echo json_encode($record, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES | JSON_THROW_ON_ERROR);
} catch (Throwable $error) {
    echo json_encode(['passed' => false, 'error_class' => get_class($error), 'raw_message_emitted' => false]);
    exit(1);
}
