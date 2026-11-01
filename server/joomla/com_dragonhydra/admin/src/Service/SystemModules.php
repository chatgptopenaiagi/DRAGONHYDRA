<?php
namespace Dragonhydra\Component\Dragonhydra\Administrator\Service;
defined('_JEXEC') or die;

/** Read-only projection of the kernel registry; no configuration or status is stored by Joomla. */
final class SystemModules
{
    public const GROUPS = [
        'infra' => 'Infrastructure', 'data' => 'Data',
        'odds_prediction' => 'Odds and prediction', 'optional_ai' => 'Optional AI',
        'memory_evaluation' => 'Memory and evaluation',
    ];
    public const STATES = [
        'ready' => 'Ready', 'degraded' => 'Degraded', 'unavailable' => 'Unavailable',
        'configured_unverified' => 'Configured, unverified',
        'installed_not_configured' => 'Installed, not configured',
        'not_implemented' => 'Not implemented', 'not_applicable' => 'Not applicable',
    ];

    public static function load(callable $read, string $group = '', string $status = '', string $id = '', ?int $now = null): array
    {
        // Browser input never becomes a backend path, URL, method or operation.
        return self::project($read('/system/modules'), $group, $status, $id, $now);
    }

    public static function buildIdentity(array $system): array
    {
        $build = is_array($system['build'] ?? null) ? $system['build'] : [];
        $safeLabel = static fn($value): ?string => is_string($value) && preg_match('/^[A-Za-z0-9][A-Za-z0-9.+_-]{0,79}$/D', $value) ? $value : null;
        $hash = static fn($value, $length): ?string => is_string($value) && preg_match('/^[a-f0-9]{' . $length . '}$/D', $value) ? $value : null;
        return ['version'=>$safeLabel($build['version'] ?? $system['version'] ?? null),
            'build_kind'=>$safeLabel($build['build_kind'] ?? null),
            'source_sha'=>$hash($build['source_sha'] ?? null,40),
            'source_content_sha256'=>$hash($build['source_content_sha256'] ?? null,64)];
    }

    public static function project(array $registry, string $group = '', string $status = '', string $id = '', ?int $now = null): array
    {
        if (($registry['schema_version'] ?? null) !== 1 || !is_array($registry['modules'] ?? null)
            || count($registry['modules']) > 100 || ($registry['read_only'] ?? null) !== true) {
            throw new \RuntimeException('INVALID_MODULE_REGISTRY');
        }
        $now ??= time();
        $group = isset(self::GROUPS[$group]) ? $group : '';
        $status = isset(self::STATES[$status]) ? $status : '';
        $id = self::id($id);
        $modules = [];
        $counts = array_fill_keys(array_keys(self::STATES), 0);
        $groups = array_fill_keys(array_keys(self::GROUPS), 0);
        $coreReady = 0; $coreRequired = 0;
        foreach (array_slice($registry['modules'], 0, 100) as $raw) {
            if (!is_array($raw) || !is_array($raw['definition'] ?? null) || !is_array($raw['observation'] ?? null)) {
                throw new \RuntimeException('INVALID_MODULE_REGISTRY');
            }
            $definition = $raw['definition']; $observation = $raw['observation'];
            $moduleId = self::id(self::text($definition['module_id'] ?? ''));
            $category = self::text($definition['category'] ?? '');
            if (!$moduleId || isset($modules[$moduleId]) || !isset(self::GROUPS[$category])
                || ($observation['module_id'] ?? '') !== $moduleId
                || (isset($registry['installation_id']) && ($observation['installation_id'] ?? null) !== $registry['installation_id'])) {
                throw new \RuntimeException('INVALID_MODULE_REGISTRY');
            }
            $reported = self::state($observation['runtime_state'] ?? '');
            $expires = self::date($observation['evidence_expires_at'] ?? null);
            $observed = self::date($observation['observed_at'] ?? null);
            $fresh = $expires !== null && $observed !== null && strtotime($expires) >= $now
                && strtotime($observed) <= $now + 30 && strtotime($expires) >= strtotime($observed);
            $state = $reported;
            $reason = self::text($observation['reason'] ?? '', 1800);
            if (!$fresh && in_array($state, ['ready', 'degraded'], true)) {
                $state = 'configured_unverified';
                $reason = 'Current runtime readiness is unverified because its evidence is missing or expired. Refresh the registry. ' . $reason;
            }
            $dependencies = [];
            foreach (array_slice((array) ($raw['dependencies'] ?? []), 0, 50) as $dependency) {
                if (!is_array($dependency) || !($dependencyId = self::id(self::text($dependency['module_id'] ?? '')))) { continue; }
                $dependencies[] = ['module_id' => $dependencyId, 'required' => ($dependency['required'] ?? false) === true,
                    'runtime_state' => self::state($dependency['runtime_state'] ?? '')];
            }
            $operations = [];
            foreach (array_slice((array) ($raw['operations'] ?? []), 0, 25) as $operation) {
                if (!is_array($operation) || !($operationId = self::id(self::text($operation['operation_id'] ?? '')))) { continue; }
                $operations[] = ['operation_id' => $operationId, 'label' => self::text($operation['label'] ?? $operationId, 160),
                    'kind' => self::text($operation['kind'] ?? '', 20), 'read_only' => ($operation['read_only'] ?? false) === true,
                    'available' => ($operation['available'] ?? false) === true, 'reason' => self::text($operation['reason'] ?? '', 1000)];
            }
            $requirements = [];
            foreach (array_slice((array) ($definition['configuration_requirements'] ?? []), 0, 30) as $requirement) {
                if (!is_array($requirement)) { continue; }
                $requirements[] = ['reference' => self::text($requirement['reference'] ?? '', 160),
                    'required' => ($requirement['required'] ?? false) === true, 'description' => self::text($requirement['description'] ?? '', 700)];
            }
            $metrics = [];
            $safeMetrics = ['process_id','worker_alive','queued_jobs','running_jobs','stale_running_jobs','enabled_schedules',
                'retained_fixture_versions','connector_observations','raw_documents','cognitive_records','prediction_records',
                'outcome_records','evaluation_records','table_count','configured','core_store_ready','api_version',
                'probe_http_status','listener_present','authenticated','component_enabled','root_is_component','pid'];
            foreach ((array) ($observation['sanitized_metrics'] ?? []) as $key => $value) {
                if (in_array($key, $safeMetrics, true) && is_scalar($value)) { $metrics[$key] = is_bool($value) ? ($value ? 'Yes' : 'No') : self::text($value, 160); }
            }
            $required = ($definition['required_for_core'] ?? false) === true;
            $module = ['id' => $moduleId, 'name' => self::text($definition['display_name'] ?? $moduleId, 180),
                'category' => $category, 'kind' => self::text($definition['kind'] ?? '', 80),
                'description' => self::text($definition['description'] ?? '', 1800),
                'version' => self::text($definition['actual_build_or_module_version'] ?? 'Not reported', 160),
                'required_for_core' => $required, 'implementation_state' => self::text($observation['implementation_state'] ?? 'unknown', 80),
                'configuration_state' => self::text($observation['configuration_state'] ?? 'unknown', 80),
                'state' => $state, 'reported_state' => $reported, 'reason' => $reason,
                'reason_code' => self::text($observation['reason_code'] ?? '', 100),
                'observed_at' => $observed, 'expires_at' => $expires, 'fresh' => $fresh,
                'last_success_at' => self::date($observation['last_success_at'] ?? null),
                'capabilities' => self::strings($definition['implemented_capabilities'] ?? []),
                'data_domains' => self::strings($definition['data_domains'] ?? []),
                'implementation_refs' => self::strings($definition['implementation_reference'] ?? []),
                'verification_refs' => self::strings($definition['verification_refs'] ?? []),
                'evidence_refs' => self::strings($observation['evidence_reference'] ?? []),
                'requirements' => $requirements, 'dependencies' => $dependencies,
                'operations' => $operations, 'metrics' => $metrics];
            $modules[$moduleId] = $module;
            $counts[$state]++; $groups[$category]++;
            if ($required) { $coreRequired++; if ($state === 'ready') { $coreReady++; } }
        }
        foreach ($modules as &$module) {
            foreach ($module['dependencies'] as &$dependency) {
                $dependency['runtime_state'] = $modules[$dependency['module_id']]['state'] ?? 'configured_unverified';
            }
            unset($dependency);
        }
        unset($module);
        $visible = array_filter($modules, static fn(array $module): bool => (!$group || $module['category'] === $group) && (!$status || $module['state'] === $status));
        return ['as_of' => self::date($registry['as_of'] ?? null), 'registry_version' => self::text($registry['registry_version'] ?? '', 100),
            'core_state' => in_array($registry['core_state'] ?? '', ['ready','degraded','unavailable'], true) ? $registry['core_state'] : 'unavailable',
            'modules' => $modules, 'visible' => $visible, 'selected' => $modules[$id] ?? null, 'requested_id' => $id,
            'group' => $group, 'status' => $status, 'counts' => $counts, 'group_counts' => $groups,
            'total' => count($modules), 'core_required' => $coreRequired, 'core_ready' => $coreReady];
    }

    private static function id(string $value): string { return preg_match('/^[a-z][a-z0-9_]{0,79}$/D', $value) ? $value : ''; }
    private static function state(mixed $value): string { return is_string($value) && isset(self::STATES[$value]) ? $value : 'configured_unverified'; }
    private static function text(mixed $value, int $limit = 500): string { return is_scalar($value) ? substr((string) $value, 0, $limit) : ''; }
    private static function date(mixed $value): ?string
    {
        if (!is_string($value) || !preg_match('/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/D', $value) || strtotime($value) === false) { return null; }
        return $value;
    }
    private static function strings(mixed $values): array
    {
        return is_array($values) ? array_values(array_filter(array_map(static fn($value): string => self::text($value, 500), array_slice($values, 0, 40)))) : [];
    }
}
