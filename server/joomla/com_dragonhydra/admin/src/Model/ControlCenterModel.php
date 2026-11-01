<?php
namespace Dragonhydra\Component\Dragonhydra\Administrator\Model;
defined('_JEXEC') or die;

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

    private static function identity(array $value): array
    {
        if (($value['product'] ?? '') !== self::PRODUCT || empty($value['installation_id'])) {
            throw new \RuntimeException('CORE_NEXT_IDENTITY_REQUIRED');
        }
        return array_intersect_key($value, array_flip(['product', 'edition', 'installation_id', 'environment_id', 'build_id', 'source_commit', 'version']));
    }

    private static function module(array $value, int $now): array
    {
        self::identifier((string) ($value['id'] ?? ''));
        $value = array_intersect_key($value, array_flip(['id', 'name', 'version', 'state', 'description', 'category', 'origin', 'observed_at', 'expires_at', 'reason', 'dependencies', 'capabilities', 'capability_status', 'operations', 'observation', 'optional_dependency_status', 'configuration_requirements', 'data_domains', 'verification_references', 'implementation_reference', 'implementation_state', 'configuration_state', 'runtime_state', 'reason_code', 'human_readable_reason', 'last_success_at', 'evidence_expires_at', 'actual_version_or_build', 'display_name', 'responsibility', 'kind']));
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
        return $value;
    }

    public function build(array $input, bool $authorised, callable $read, ?int $now = null): array
    {
        $section = self::section((string) ($input['section'] ?? 'overview'));
        $result = ['section'=>$section, 'installation'=>[], 'modules'=>[], 'module'=>null, 'system'=>[], 'data'=>[], 'job_id'=>'', 'error'=>null];
        if (!$authorised) {
            $result['error'] = 'An authorized Joomla administrator session is required.';
            return $result;
        }
        try {
            if ($this->expectedInstallationId === '') {
                throw new \RuntimeException('CORE_NEXT_INSTALLATION_BINDING_REQUIRED');
            }
            $registry = $read('/modules');
            if (($registry['schema_version'] ?? '') !== 'core-next.modules/1' || !is_array($registry['items'] ?? null)) {
                throw new \RuntimeException('INVALID_MODULE_REGISTRY');
            }
            $result['installation'] = self::identity((array) ($registry['installation'] ?? []));
            if ($result['installation']['installation_id'] !== $this->expectedInstallationId) {
                $result['installation'] = [];
                throw new \RuntimeException('CORE_NEXT_INSTALLATION_MISMATCH');
            }
            foreach ($registry['items'] as $module) {
                $module = self::module((array) $module, $now ?? time());
                if (isset($result['modules'][$module['id']])) {
                    throw new \RuntimeException('DUPLICATE_MODULE_ID');
                }
                $result['modules'][$module['id']] = $module;
            }
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
                $result['module'] = self::module($detail, $now ?? time());
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
        } catch (\Throwable $error) {
            // Transport details, configuration paths and arbitrary backend errors stay server-side.
            $result['data'] = [];
            $result['system'] = [];
            $result['module'] = null;
            $result['error'] = 'The isolated CORE NEXT registry could not be verified. Check this installation’s backend and protected bridge, then retry. No background operation was started.';
            if (!$result['installation']) { $result['modules'] = []; }
        }
        return $result;
    }
}
