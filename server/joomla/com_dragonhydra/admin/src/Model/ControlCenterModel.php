<?php
namespace Dragonhydra\Component\Dragonhydra\Administrator\Model;
defined('_JEXEC') or die;
use Dragonhydra\Component\Dragonhydra\Administrator\Service\ControlWorkflow;

/** Presentation adapter for the kernel's registry; never stores status or runs an operation. */
final class ControlCenterModel
{
    public function __construct(private string $expectedInstallationId = '') {}
    public const PRODUCT = 'DRAGONHYDRA CORE NEXT';
    public const STATES = ['NOT_IMPLEMENTED', 'NOT_CONFIGURED', 'UNVERIFIED', 'READY', 'DEGRADED', 'UNAVAILABLE', 'NOT_APPLICABLE', 'UNKNOWN', 'EXPIRED', 'STOPPED'];
    public const SECTIONS = ['overview', 'infrastructure', 'sources', 'matches', 'odds', 'prediction', 'ai', 'memory', 'evaluation', 'modules', 'jobs'];

    public static function section(string $value): string
    {
        $aliases = ['system'=>'overview', 'databases'=>'infrastructure', 'models'=>'ai', 'research'=>'memory'];
        $value = $aliases[$value] ?? $value;
        return in_array($value, self::SECTIONS, true) ? $value : 'overview';
    }

    public static function identifier(string $value): string
    {
        if (!preg_match('/^[a-zA-Z0-9_-]{1,80}$/D', $value)) {
            throw new \InvalidArgumentException('INVALID_CONTROL_SELECTION');
        }
        return $value;
    }

    public static function tone(string $state): string
    {
        return match ($state) {
            'READY' => 'green', 'DEGRADED' => 'amber',
            'UNAVAILABLE','STOPPED' => 'red',
            'NOT_CONFIGURED','UNVERIFIED','EXPIRED','UNKNOWN','NOT_APPLICABLE' => 'neutral', default => 'neutral',
        };
    }

    public static function stateLabel(string $state): string
    {
        return in_array($state,self::STATES,true) ? ucfirst(strtolower(str_replace('_',' ',$state))) : 'Unknown';
    }

    /** Navigation to existing views only; backend paths never become links. */
    public static function operationReadView(array $operation, string $moduleId): array
    {
        $disabled = static fn(string $reason): array => ['query'=>null, 'label'=>'Disabled here', 'reason'=>$reason];
        $reportedReason = is_string($operation['reason'] ?? null) && trim($operation['reason']) !== '' ? $operation['reason'] : null;
        if (($operation['enabled'] ?? false) !== true) {
            return $disabled($reportedReason ?? 'This operation is disabled for this account or installation.');
        }
        if (($operation['method'] ?? '') !== 'GET') {
            return $disabled($reportedReason ?? 'This operation requires an explicit supported form; it cannot run from a read link.');
        }
        $views = [
            'read_modules'=>['section=modules','Browse modules'],
            'read_system'=>['section=infrastructure','Open infrastructure'],
            'read_matches'=>['section=matches','Browse retained matches'],
            'read_connections'=>['section=sources','Open data sources'],
            'read_predictions'=>['section=prediction','Open predictions read view'],
            'read_cognition_history'=>['section=memory','Open retained memory view'],
            'read_analysis_package'=>['section=ai','Open AI evidence view'],
        ];
        $id = $operation['id'] ?? null;
        if ($id === 'status' && preg_match('/^[a-zA-Z0-9_-]{1,80}$/D', $moduleId)) {
            return ['query'=>'section=modules&module=' . rawurlencode($moduleId), 'label'=>'Inspect module',
                'reason'=>'Read this module’s retained definition and evidence. No job or background check is started.'];
        }
        if (is_string($id) && isset($views[$id])) {
            return ['query'=>$views[$id][0], 'label'=>$views[$id][1],
                'reason'=>'Open the existing protected read view. This does not run the advertised engine operation.'];
        }
        return $disabled($reportedReason ?? 'No supported Joomla read view is registered for this operation.');
    }

    private static function identity(array $value): array
    {
        if (($value['product'] ?? '') !== self::PRODUCT || empty($value['installation_id'])) {
            throw new \RuntimeException('CORE_NEXT_IDENTITY_REQUIRED');
        }
        return array_intersect_key($value, array_flip(['product', 'edition', 'installation_id', 'environment_id', 'build_id', 'source_commit', 'version']));
    }

    private static function serviceIdentity(array $module, array $installation, float $now): ?array
    {
        if (($module['id'] ?? '') !== 'runtime_supervisor'
            || !is_array($module['service_identity'] ?? null)
            || !is_array($module['observation'] ?? null)
            || !is_array($module['observation']['service_identity'] ?? null)) { return null; }
        if (isset($module['installation']) && !is_array($module['installation'])) { return null; }
        $fields = array_flip(['service_name','installation_id','source_commit','build_id','observed_at','evidence_expires_at','verification_scope']);
        $identity = array_intersect_key($module['service_identity'], $fields);
        $observedCopy = array_intersect_key($module['observation']['service_identity'], $fields);
        ksort($identity); ksort($observedCopy);
        if ($identity !== $observedCopy || count($identity) !== count($fields)
            || !is_string($identity['service_name']) || !preg_match('/^Dragonhydra[A-Za-z0-9_-]{0,60}$/D', $identity['service_name'])
            || ($identity['verification_scope'] ?? '') !== 'BOUND_SUPERVISOR_SERVICE_IDENTITY_ONLY') { return null; }
        foreach (['installation_id','source_commit','build_id'] as $key) {
            if (!is_string($identity[$key]) || $identity[$key] !== ($installation[$key] ?? null)) { return null; }
            if (isset($module['installation']) && $identity[$key] !== ($module['installation'][$key] ?? null)) { return null; }
        }
        if (!preg_match('/^[a-f0-9]{40}$/D', $identity['source_commit'])
            || !preg_match('/^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$/D', $identity['installation_id'])
            || !preg_match('/^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$/D', $identity['build_id'])
            || (isset($module['installation_id']) && $module['installation_id'] !== $identity['installation_id'])) { return null; }
        $timestamp = static function ($value): ?float {
            if (!is_string($value) || !preg_match('/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z$/D', $value)) { return null; }
            try {
                $date = new \DateTimeImmutable($value);
                $errors = \DateTimeImmutable::getLastErrors();
                if ($errors !== false && ($errors['warning_count'] || $errors['error_count'])) { return null; }
                return (float)$date->format('U.u');
            } catch (\Exception $error) { return null; }
        };
        $observed = $timestamp($identity['observed_at']);
        $expiry = $timestamp($identity['evidence_expires_at']);
        if ($observed === null || $expiry === null || $observed > $now || $expiry <= $now
            || $expiry <= $observed || $expiry-$observed > 90) { return null; }
        return $identity;
    }

    private static function module(array $value, int $now, array $installation, float $serviceClock): array
    {
        self::identifier((string) ($value['id'] ?? ''));
        $serviceIdentity = self::serviceIdentity($value, $installation, $serviceClock);
        $value = array_intersect_key($value, array_flip(['id', 'name', 'version', 'state', 'description', 'category', 'origin', 'observed_at', 'expires_at', 'reason', 'dependencies', 'dependency_status', 'capabilities', 'capability_status', 'operations', 'observation', 'optional_dependency_status', 'configuration_requirements', 'data_domains', 'verification_references', 'implementation_reference', 'implementation_state', 'configuration_state', 'runtime_state', 'reason_code', 'human_readable_reason', 'last_success_at', 'evidence_expires_at', 'actual_version_or_build', 'display_name', 'responsibility', 'kind', 'layer', 'runtime_owner', 'observation_id', 'observer_identity', 'build_identity', 'verification_scope']));
        if (is_array($value['observation'] ?? null)) { unset($value['observation']['service_identity']); }
        if ($serviceIdentity !== null) {
            $value['service_identity'] = $serviceIdentity;
            $value['observation']['service_identity'] = $serviceIdentity;
        }
        $value['layer'] = in_array($value['layer'] ?? '', ['engine','supporting'],true) ? $value['layer'] : 'unclassified';
        if (!in_array($value['state'] ?? '', self::STATES, true)) {
            $value['state'] = 'UNKNOWN';
            $value['reason'] = 'The registry did not provide a recognized state.';
        }
        $expiry = isset($value['expires_at']) ? strtotime((string) $value['expires_at']) : false;
        $observed = isset($value['observed_at']) ? strtotime((string) $value['observed_at']) : false;
        if ($value['state'] === 'READY' && ($expiry === false || $observed === false || $observed > $now + 60)) {
            $value['state'] = 'UNKNOWN';
            $value['reason'] = 'A bounded current observation was not supplied. Module presence does not establish readiness.';
        }
        if ($expiry !== false && $expiry <= $now && !in_array($value['state'], ['UNAVAILABLE', 'STOPPED'], true)) {
            $value['state'] = 'EXPIRED';
            $value['reason'] = 'The last observation has expired. No new probe was run by opening this page.';
        }
        $value['evidence_age_seconds'] = $observed !== false && $observed <= $now ? $now-$observed : null;
        $value['evidence_remaining_seconds'] = $expiry !== false ? $expiry-$now : null;
        return $value;
    }

    public function build(array $input, bool $authorised, callable $read, ?int $now = null): array
    {
        $section = self::section((string) ($input['section'] ?? 'overview'));
        $result = ['section'=>$section, 'installation'=>[], 'modules'=>[], 'visible_modules'=>[], 'module'=>null,
            'inventory'=>['engines'=>0,'supporting'=>0,'total'=>0,'unclassified'=>0], 'categories'=>[], 'filters'=>['layer'=>'','category'=>'','status'=>''],
            'system'=>[], 'data'=>[], 'job_id'=>'', 'workflow'=>null,'workflow_error'=>null, 'error'=>null];
        if (!$authorised) {
            $result['error'] = 'An authorized Joomla administrator session is required.';
            return $result;
        }
        try {
            if ($this->expectedInstallationId === '') {
                throw new \RuntimeException('CORE_NEXT_INSTALLATION_BINDING_REQUIRED');
            }
            $registry = $read('/modules?scope=all');
            if (($registry['schema_version'] ?? '') !== 'core-next.modules/1' || !is_array($registry['items'] ?? null)) {
                throw new \RuntimeException('INVALID_MODULE_REGISTRY');
            }
            $result['installation'] = self::identity((array) ($registry['installation'] ?? []));
            if ($result['installation']['installation_id'] !== $this->expectedInstallationId) {
                $result['installation'] = [];
                throw new \RuntimeException('CORE_NEXT_INSTALLATION_MISMATCH');
            }
            foreach ($registry['items'] as $module) {
                $module = self::module((array) $module, $now ?? time(), $result['installation'], $now === null ? microtime(true) : (float)$now);
                if (isset($result['modules'][$module['id']])) {
                    throw new \RuntimeException('DUPLICATE_MODULE_ID');
                }
                $result['modules'][$module['id']] = $module;
            }
            foreach ($result['modules'] as $module) {
                $key = $module['layer'] === 'engine' ? 'engines' : $module['layer'];
                $result['inventory'][$key]++;
                $result['inventory']['total']++;
                if (is_string($module['category'] ?? null) && $module['category'] !== '') { $result['categories'][$module['category']] = $module['category']; }
            }
            if (isset($registry['inventory'])) {
                foreach (['engines','supporting','total'] as $key) {
                    if (($registry['inventory'][$key] ?? null) !== $result['inventory'][$key]) { throw new \RuntimeException('INVENTORY_COUNT_MISMATCH'); }
                }
            }
            ksort($result['categories']);
            $layer = (string) ($input['layer'] ?? '');
            $category = (string) ($input['category'] ?? '');
            $status = (string) ($input['status'] ?? '');
            $result['filters'] = ['layer'=>in_array($layer,['engine','supporting'],true) ? $layer : '',
                'category'=>isset($result['categories'][$category]) ? $category : '',
                'status'=>in_array($status,self::STATES,true) ? $status : ''];
            $result['visible_modules'] = array_filter($result['modules'], static fn($module): bool =>
                (!$result['filters']['layer'] || $module['layer'] === $result['filters']['layer'])
                && (!$result['filters']['category'] || ($module['category'] ?? '') === $result['filters']['category'])
                && (!$result['filters']['status'] || $module['state'] === $result['filters']['status']));
            $selected = (string) ($input['module'] ?? '');
            if (!$selected && in_array($section, ['odds', 'prediction', 'ai', 'memory', 'evaluation'], true)) {
                $selected = $section;
            }
            if ($selected !== '') {
                self::identifier($selected);
                if (!isset($result['modules'][$selected])) {
                    throw new \InvalidArgumentException('MODULE_NOT_REGISTERED');
                }
                $detail = $read('/modules/' . rawurlencode($selected));
                $identity = self::identity((array) ($detail['installation'] ?? []));
                if ($identity['installation_id'] !== $result['installation']['installation_id'] || ($detail['id'] ?? '') !== $selected) {
                    throw new \RuntimeException('MODULE_IDENTITY_MISMATCH');
                }
                $result['module'] = self::module($detail, $now ?? time(), $result['installation'], $now === null ? microtime(true) : (float)$now);
            }
            if (in_array($section, ['overview', 'infrastructure'], true)) {
                $result['system'] = $read('/system');
                $identity = self::identity((array) ($result['system']['installation'] ?? []));
                if ($identity['installation_id'] !== $result['installation']['installation_id']) {
                    throw new \RuntimeException('SYSTEM_IDENTITY_MISMATCH');
                }
            } elseif ($section === 'sources') {
                $result['data'] = $read('/connections');
            } elseif ($section === 'matches') {
                $id = (string) ($input['match_id'] ?? '');
                $offset = max(0, (int) ($input['offset'] ?? 0));
                $result['data'] = $id ? ['match'=>$read('/matches/' . rawurlencode(self::identifier($id)))] : $read('/matches?limit=50&offset=' . $offset);
            } elseif ($section === 'jobs') {
                $result['job_id'] = self::identifier((string) ($input['job_id'] ?? ''));
                $result['data'] = $read('/jobs/' . rawurlencode($result['job_id']));
            }
            $workflowMatch = (string)($input['match_id'] ?? '');
            if ($workflowMatch !== '' && in_array($section,['overview','prediction','memory','evaluation','modules'],true)) {
                try {
                    $result['workflow'] = ControlWorkflow::load($read,$workflowMatch,$this->expectedInstallationId);
                } catch (\Throwable $error) {
                    $result['workflow_error'] = 'Retained workflow history is unavailable for this selected match in this installation. No forecast or evaluation was started.';
                }
            }
        } catch (\Throwable $error) {
            // Transport details, configuration paths and arbitrary backend errors stay server-side.
            $result['data'] = [];
            $result['system'] = [];
            $result['module'] = null;
            $result['error'] = 'The isolated CORE NEXT registry could not be verified. Check this installation’s backend and protected bridge, then retry. No background operation was started.';
            if (!$result['installation']) { $result['modules'] = []; $result['visible_modules'] = []; }
        }
        return $result;
    }
}
