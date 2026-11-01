<?php
/** Pure deployment binding validation, shared by provisioning and its tests. */
declare(strict_types=1);
function coreNextProfile(array $cfg): array {
    $id = $cfg['installation_id'] ?? '';
    if (($cfg['product'] ?? '') !== 'DRAGONHYDRA CORE NEXT' || ($cfg['edition'] ?? '') !== 'CORE NEXT'
        || !is_string($id) || !preg_match('/^core-next-[a-f0-9]{32}$/D', $id)
        || !in_array($cfg['environment_id'] ?? '', ['baseline', 'candidate'], true)) {
        throw new RuntimeException('CORE_NEXT_PROFILE_IDENTITY_REQUIRED');
    }
    $suffix = substr($id, -12);
    $base = 'C:/xampp/DRAGONHYDRA-CORE-NEXT-LAB/profiles/' . $id;
    $normalize = static fn(string $value): string => strtolower(rtrim(str_replace('\\', '/', $value), '/'));
    foreach (['install_root' => '/application', 'state_root' => '/state', 'browser_user_data' => '/browser', 'profile_path' => '/installation-profile.json'] as $key => $tail) {
        if (!is_string($cfg[$key] ?? null) || $normalize($cfg[$key]) !== $normalize($base . $tail)) {
            throw new RuntimeException('CORE_NEXT_PROFILE_PATH_IDENTITY_MISMATCH');
        }
    }
    $profile = json_decode((string) file_get_contents($cfg['profile_path']), true, 64, JSON_THROW_ON_ERROR);
    foreach (['product','edition','installation_id','environment_id','install_root','state_root','browser_user_data','service_name','cookie_name','joomla_session_suffix'] as $key) {
        if (($cfg[$key] ?? null) !== ($profile[$key] ?? null)) { throw new RuntimeException('CORE_NEXT_PERSISTED_BINDING_MISMATCH'); }
    }
    if ($cfg['service_name'] !== 'DragonhydraCoreNext' . $cfg['environment_id'] . $suffix
        || $cfg['cookie_name'] !== 'dhcn_' . $suffix || $cfg['joomla_session_suffix'] !== $id) {
        throw new RuntimeException('CORE_NEXT_SERVICE_OR_SESSION_IDENTITY_MISMATCH');
    }
    foreach (['api_port' => 'api','web_port' => 'web','database_port' => 'database'] as $key => $port) {
        if (!is_int($cfg[$key] ?? null) || $cfg[$key] < 18800 || $cfg[$key] > 65535 || $cfg[$key] !== ($profile['ports'][$port] ?? null)) {
            throw new RuntimeException('CORE_NEXT_PERSISTED_PORT_MISMATCH');
        }
    }
    foreach (['db_name'=>'dhcn_admin_','db_user'=>'dhcn_admin_','core_db_name'=>'dhcn_core_','core_db_user'=>'dhcn_core_'] as $key => $prefix) {
        if (($cfg[$key] ?? '') !== $prefix . $suffix) { throw new RuntimeException('CORE_NEXT_DATABASE_IDENTITY_MISMATCH'); }
    }
    return $cfg;
}
