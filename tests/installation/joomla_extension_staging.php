<?php
/**
 * LocalService regression probe. No extension installation, service actions or DB writes.
 * Usage: private php -c private.ini joomla_extension_staging.php private.json output.json
 * Output must remain in the protected state directory. Run only under SID S-1-5-19.
 */
declare(strict_types=1);

if (PHP_SAPI !== 'cli') { exit(1); }
ini_set('display_errors', '0');
ini_set('zend.exception_ignore_args', '1');
error_reporting(E_ALL);
$report = ['schema_version' => 1, 'started_utc' => gmdate('c'), 'passed' => false,
    'database_mutations' => false, 'extension_installation_attempted' => false, 'service_actions' => false];
$cfg = []; $phase = 'bootstrap'; $diagnostics = []; $ownedDirectory = null; $outputPath = $argv[2] ?? '';

function cleanValue(mixed $value, array $cfg): mixed {
    if (is_array($value)) { foreach ($value as $key => $item) { $value[$key] = cleanValue($item, $cfg); } return $value; }
    if (!is_string($value)) { return $value; }
    foreach (['root_password', 'db_password', 'core_db_password', 'admin_password'] as $key) {
        if (is_string($cfg[$key] ?? null) && $cfg[$key] !== '') { $value = str_replace($cfg[$key], '[REDACTED]', $value); }
    }
    return $value;
}
function normalized(string $path): string { return rtrim(str_replace('\\', '/', $path), '/'); }
function inside(string $path, string $parent): bool {
    return str_starts_with(strtolower(normalized($path) . '/'), strtolower(normalized($parent) . '/'));
}
function exceptionDetails(Throwable $exception): array {
    return ['class' => get_class($exception), 'message' => $exception->getMessage(), 'file' => $exception->getFile(),
        'line' => $exception->getLine(), 'trace' => $exception->getTraceAsString()];
}
function removeOwnedTree(string $directory, string $expected): void {
    if (normalized($directory) !== normalized($expected) || is_link($directory)) { throw new RuntimeException('CLEANUP_OWNERSHIP_MISMATCH'); }
    if (!is_dir($directory)) { return; }
    $iterator = new RecursiveIteratorIterator(new RecursiveDirectoryIterator($directory, FilesystemIterator::SKIP_DOTS), RecursiveIteratorIterator::CHILD_FIRST);
    foreach ($iterator as $item) {
        if ($item->isLink() || $item->isFile()) { if (!unlink($item->getPathname())) { throw new RuntimeException('OWNED_FILE_CLEANUP_FAILED'); } }
        elseif (!rmdir($item->getPathname())) { throw new RuntimeException('OWNED_DIRECTORY_CLEANUP_FAILED'); }
    }
    if (!rmdir($directory)) { throw new RuntimeException('OWNED_ROOT_CLEANUP_FAILED'); }
}
function actualIdentity(): array {
    $executable = (getenv('SystemRoot') ?: 'C:/Windows') . '/System32/whoami.exe';
    $process = proc_open([$executable, '/user', '/fo', 'csv', '/nh'],
        [0 => ['file', 'NUL', 'r'], 1 => ['pipe', 'w'], 2 => ['pipe', 'w']], $pipes, null, null, ['bypass_shell' => true]);
    if (!is_resource($process)) { throw new RuntimeException('IDENTITY_PROBE_START_FAILED'); }
    $deadline = microtime(true) + 15;
    do { $status = proc_get_status($process); if (!$status['running']) { break; } usleep(100000); } while (microtime(true) < $deadline);
    if ($status['running']) { proc_terminate($process); throw new RuntimeException('IDENTITY_PROBE_TIMEOUT'); }
    $stdout = stream_get_contents($pipes[1]); $stderr = stream_get_contents($pipes[2]);
    fclose($pipes[1]); fclose($pipes[2]); $exit = proc_close($process);
    if ($exit === -1) { $exit = $status['exitcode']; }
    if ($exit !== 0) { throw new RuntimeException('IDENTITY_PROBE_FAILED'); }
    $fields = str_getcsv(trim($stdout), ',', '"', '');
    return ['logon_name' => $fields[0] ?? null, 'sid' => $fields[1] ?? null,
        'method' => 'Windows whoami /user /fo csv /nh (actual process token)', 'exit_code' => $exit, 'stderr' => $stderr];
}

$warningHandler = function (int $severity, string $message, string $file, int $line) use (&$diagnostics, &$phase): bool {
    $diagnostics[] = ['phase' => $phase, 'kind' => 'php_warning', 'severity' => $severity, 'message' => $message,
        'file' => $file, 'line' => $line, 'masked_by_php_at_operator' => !(bool) (error_reporting() & $severity)];
    return true;
};
set_error_handler($warningHandler);

try {
    if (count($argv) !== 3 || !is_file($argv[1])) { throw new RuntimeException('USAGE_PRIVATE_CONFIGURATION_OUTPUT_JSON'); }
    $cfg = json_decode((string) file_get_contents($argv[1]), true, 64, JSON_THROW_ON_ERROR);
    $state = normalized((string) realpath($cfg['state_root']));
    $install = normalized((string) realpath($cfg['install_root']));
    $site = $state . '/site'; $immutable = $install . '/web/extension.zip';
    $outputParent = realpath(dirname($outputPath));
    if (!$outputParent || !inside($outputParent, $state) || !is_file($site . '/configuration.php')) { throw new RuntimeException('PROTECTED_INSTALLED_STATE_REQUIRED'); }
    $outputPath = normalized($outputParent) . '/' . basename($outputPath);
    $report['identity'] = actualIdentity();
    if (($report['identity']['sid'] ?? '') !== 'S-1-5-19') { throw new RuntimeException('RUN_ONLY_AS_LOCAL_SERVICE'); }
    $expected = '66529fd54fd913b3fc90ef5b21e5b8c972956379c16a48b8d9a94419e60ed585';
    $originalHash = hash_file('sha256', $immutable);
    if ($originalHash !== $expected) { throw new RuntimeException('IMMUTABLE_EXTENSION_HASH_MISMATCH'); }
    $zip = new ZipArchive();
    if ($zip->open($immutable) !== true) { throw new RuntimeException('EXTENSION_ZIP_INVALID'); }
    $members = []; for ($index = 0; $index < $zip->numFiles; $index++) { $members[] = $zip->getNameIndex($index); }
    $packageXml = $zip->getFromName('pkg_dragonhydra.xml');
    $nestedBytes = $zip->getFromName('constituents/com_dragonhydra.zip'); $zip->close();
    if (!$packageXml || !$nestedBytes) { throw new RuntimeException('EXTENSION_REQUIRED_MEMBERS_MISSING'); }
    $xml = simplexml_load_string($packageXml);
    if (!$xml || (string) $xml['type'] !== 'package' || (string) $xml->packagename !== 'dragonhydra') { throw new RuntimeException('PACKAGE_MANIFEST_IDENTITY_MISMATCH'); }
    $report['immutable_package'] = ['path' => $immutable, 'sha256' => $originalHash, 'expected_sha256' => $expected,
        'hash_matches' => true, 'bytes' => filesize($immutable), 'members' => $members,
        'manifest' => ['type' => (string) $xml['type'], 'name' => (string) $xml->packagename, 'version' => (string) $xml->version],
        'nested_component_zip_sha256' => hash('sha256', $nestedBytes)];
    $report['configuration_schema'] = ['required_fields_present' => !array_diff(['install_root', 'state_root', 'database_port', 'db_name', 'db_user', 'db_password'], array_keys($cfg)),
        'database_name' => $cfg['db_name'], 'database_user' => $cfg['db_user'], 'database_port' => $cfg['database_port']];
    $runId = 'extension-staging-regression-' . bin2hex(random_bytes(12));
    $ownedDirectory = $state . '/web-temp/' . $runId;
    if (!mkdir($ownedDirectory, 0700, true)) { throw new RuntimeException('OWNED_STAGING_DIRECTORY_FAILED'); }

    // Boot the same installed CMS and console application used by cli/joomla.php, without execute().
    define('_JEXEC', 1); define('JPATH_BASE', $site);
    require_once $site . '/includes/defines.php'; require_once $site . '/includes/framework.php';
    $container = Joomla\CMS\Factory::getContainer();
    $container->alias('session', 'session.cli')->alias('JSession', 'session.cli')
        ->alias(Joomla\CMS\Session\Session::class, 'session.cli')->alias(Joomla\Session\Session::class, 'session.cli')
        ->alias(Joomla\Session\SessionInterface::class, 'session.cli');
    $app = $container->get(Joomla\Console\Application::class); Joomla\CMS\Factory::$application = $app;
    Joomla\CMS\Log\Log::addLogger(['logger' => 'callback', 'callback' => function ($entry) use (&$diagnostics, &$phase): void {
        $diagnostics[] = ['phase' => $phase, 'kind' => 'joomla_log', 'priority' => $entry->priority,
            'category' => $entry->category, 'message' => $entry->message];
    }], Joomla\CMS\Log\Log::ALL);
    // Joomla bootstrap installs its own handlers. Observe the actual @mkdir warning too.
    set_error_handler($warningHandler);
    $before = scandir(dirname($immutable));
    $phase = 'original_installer_helper_unpack';
    try { $originalResult = Joomla\CMS\Installer\InstallerHelper::unpack($immutable, true); }
    catch (Throwable $failure) { $originalResult = ['type' => false]; $report['original_helper_exception'] = exceptionDetails($failure); }
    $report['original_helper'] = ['method' => 'Joomla\\CMS\\Installer\\InstallerHelper::unpack', 'result' => $originalResult,
        'failed_as_expected' => ($originalResult['type'] ?? false) === false,
        'internal_exception_catch' => 'The installed CMS helper catches Archive exceptions and returns type=false; underlying adapter probe below preserves the original exception'];
    if (($originalResult['type'] ?? false) !== false || $before !== scandir(dirname($immutable))) { throw new RuntimeException('IMMUTABLE_DIRECTORY_NOT_READ_ONLY'); }
    $phase = 'underlying_original_joomla_archive_exception';
    // Exact adapter call made by InstallerHelper, outside its catch so the real vendor exception is observable.
    try {
        $archive = new Joomla\Archive\Archive(['tmp_path' => $app->get('tmp_path')]);
        $archive->extract($immutable, dirname($immutable) . '/' . $runId);
        throw new RuntimeException('IMMUTABLE_ARCHIVE_EXTRACTION_UNEXPECTEDLY_SUCCEEDED');
    } catch (Throwable $failure) { $report['underlying_original_joomla_exception'] = exceptionDetails($failure); }
    $vendorDirectoryFailure = str_starts_with($report['underlying_original_joomla_exception']['class'], 'Joomla\\Filesystem\\')
        && str_contains($report['underlying_original_joomla_exception']['message'], 'Could not create directory');
    $permissionDenied = false;
    foreach ($diagnostics as $diagnostic) {
        if (in_array($diagnostic['phase'], ['original_installer_helper_unpack', 'underlying_original_joomla_archive_exception'], true)
            && preg_match('/permission denied|access is denied|access denied/i', $diagnostic['message'])) { $permissionDenied = true; }
    }
    $report['original_helper']['actual_vendor_directory_exception_confirmed'] = $vendorDirectoryFailure;
    $report['original_helper']['actual_permission_denied_warning_observed'] = $permissionDenied;
    if (!$vendorDirectoryFailure || !$permissionDenied) { throw new RuntimeException('ORIGINAL_PERMISSION_FAILURE_NOT_CONFIRMED'); }
    if ($before !== scandir(dirname($immutable))) { throw new RuntimeException('IMMUTABLE_DIRECTORY_CHANGED'); }

    $phase = 'verified_writable_staging';
    $staged = $ownedDirectory . '/package.zip';
    if (!copy($immutable, $staged) || hash_file('sha256', $staged) !== $expected) { throw new RuntimeException('STAGING_COPY_HASH_MISMATCH'); }
    // Inspect the embedded component itself using only files inside this owned test directory.
    $nestedPath = $ownedDirectory . '/component-inspection.zip'; file_put_contents($nestedPath, $nestedBytes);
    $nested = new ZipArchive(); if ($nested->open($nestedPath) !== true) { throw new RuntimeException('NESTED_COMPONENT_ZIP_INVALID'); }
    $componentXml = $nested->getFromName('dragonhydra.xml');
    $componentMembers = []; for ($index = 0; $index < $nested->numFiles; $index++) { $componentMembers[] = $nested->getNameIndex($index); }
    $nested->close();
    if (!$componentXml) { throw new RuntimeException('COMPONENT_MANIFEST_MISSING'); }
    $component = simplexml_load_string($componentXml);
    if (!$component || (string) $component['type'] !== 'component') { throw new RuntimeException('COMPONENT_MANIFEST_TYPE_MISMATCH'); }
    $stagedResult = Joomla\CMS\Installer\InstallerHelper::unpack($staged, true);
    $success = ($stagedResult['type'] ?? false) === 'package' && is_file(($stagedResult['extractdir'] ?? '') . '/pkg_dragonhydra.xml')
        && is_file(($stagedResult['extractdir'] ?? '') . '/constituents/com_dragonhydra.zip');
    $report['staged_helper'] = ['method' => 'Joomla\\CMS\\Installer\\InstallerHelper::unpack', 'verified_copy_sha256' => hash_file('sha256', $staged),
        'result' => $stagedResult, 'success' => $success, 'nested_component_manifest_type' => (string) $component['type'],
        'nested_component_version' => (string) $component->version, 'nested_component_members' => $componentMembers];
    if (!$success || !inside($stagedResult['extractdir'], $ownedDirectory)) { throw new RuntimeException('STAGED_EXTRACTION_NOT_CONFIRMED'); }

    $phase = 'readonly_database_permission_probe';
    try {
        mysqli_report(MYSQLI_REPORT_ERROR | MYSQLI_REPORT_STRICT);
        $db = mysqli_init(); $db->options(MYSQLI_OPT_CONNECT_TIMEOUT, 3);
        $db->real_connect('127.0.0.1', $cfg['db_user'], $cfg['db_password'], $cfg['db_name'], (int) $cfg['database_port']);
        $identity = $db->query('SELECT DATABASE(),CURRENT_USER(),VERSION()')->fetch_row();
        $grants = array_column($db->query('SHOW GRANTS FOR CURRENT_USER')->fetch_all(MYSQLI_NUM), 0);
        $report['database_permission_readback'] = ['status' => 'verified', 'database' => $identity[0], 'authenticated_user' => $identity[1], 'server_version' => $identity[2],
            'grant_count' => count($grants), 'grant_text_included' => false, 'grants_sha256' => hash('sha256', json_encode($grants, JSON_THROW_ON_ERROR)),
            'statements' => ['SELECT DATABASE(),CURRENT_USER(),VERSION()', 'SHOW GRANTS FOR CURRENT_USER']];
        $db->close();
    } catch (Throwable $failure) { $report['database_permission_readback'] = ['status' => 'unavailable_no_service_started', 'exception' => exceptionDetails($failure)]; }
    $report['historical_installation_logs'] = [];
    foreach (['web-install.log', 'web-logs/extension-install.stdout.log', 'web-logs/extension-install.stderr.log', 'web-logs/php-error.log'] as $name) {
        if (is_file($state . '/' . $name)) { $report['historical_installation_logs'][$name] = file_get_contents($state . '/' . $name); }
    }
    $report['immutable_package']['hash_unchanged_after_probes'] = hash_file('sha256', $immutable) === $expected;
    $report['immutable_directory_unchanged'] = $before === scandir(dirname($immutable));
    $report['passed'] = $report['original_helper']['failed_as_expected'] && $success && $report['immutable_directory_unchanged'] && $report['immutable_package']['hash_unchanged_after_probes'];
} catch (Throwable $failure) { $report['failure'] = exceptionDetails($failure); }
finally {
    $phase = 'cleanup';
    if ($ownedDirectory && is_dir($ownedDirectory)) {
        try { removeOwnedTree($ownedDirectory, $ownedDirectory); $report['owned_staging_cleanup'] = true; }
        catch (Throwable $failure) { $report['owned_staging_cleanup'] = false; $report['cleanup_exception'] = exceptionDetails($failure); $report['passed'] = false; }
    }
    $report['diagnostics'] = $diagnostics; $report['finished_utc'] = gmdate('c');
    $report = cleanValue($report, $cfg);
    if ($outputPath) { file_put_contents($outputPath, json_encode($report, JSON_THROW_ON_ERROR | JSON_UNESCAPED_SLASHES | JSON_PRETTY_PRINT) . "\n"); }
}
echo json_encode(['passed' => $report['passed'], 'output' => $outputPath, 'identity_sid' => $report['identity']['sid'] ?? null,
    'original_helper_failed' => $report['original_helper']['failed_as_expected'] ?? null, 'staged_unpack_succeeded' => $report['staged_helper']['success'] ?? null], JSON_THROW_ON_ERROR | JSON_UNESCAPED_SLASHES) . "\n";
exit($report['passed'] ? 0 : 1);
