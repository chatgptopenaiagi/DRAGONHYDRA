<?php
namespace Dragonhydra\Component\Dragonhydra\Administrator\Service;
defined('_JEXEC') or die;

/** Typed retained-workflow reads and explicit commands; never a generic API proxy. */
final class ControlWorkflow
{
    public static function matchId(string $id): string
    {
        if (!preg_match('/^[a-f0-9]{64}$/D', $id)) { throw new \RuntimeException('INVALID_MATCH_ID', 400); }
        return $id;
    }

    public static function load(callable $read, string $id, string $installationId): array
    {
        $id = self::matchId($id);
        $match = $read('/matches/' . $id);
        $history = $read('/matches/' . $id . '/cognition-history');
        if (($history['schema_version'] ?? '') !== 'core-next.workflow/1' || $installationId === ''
            || ($history['installation']['product'] ?? '') !== 'DRAGONHYDRA CORE NEXT'
            || ($history['installation']['installation_id'] ?? '') !== $installationId
            || ($history['match_id'] ?? '') !== $id || !is_array($history['records'] ?? null)) {
            throw new \RuntimeException('INVALID_WORKFLOW_HISTORY');
        }
        return self::project($match, $history);
    }

    public static function project(array $match, array $history): array
    {
        $id = self::matchId(self::text($history['match_id'] ?? ''));
        if (($match['id'] ?? '') !== $id) { throw new \RuntimeException('INVALID_WORKFLOW_HISTORY'); }
        $records = $history['records'] ?? [];
        $models = [];
        foreach (self::rows($records['models'] ?? []) as $row) {
            $workflow = is_array($row['parameters']['workflow'] ?? null) ? $row['parameters']['workflow'] : [];
            $models[] = self::fields($row, ['record_id','run_id','model_name','model_version','data_cutoff','received_at','usable_at'])
                + ['generated_at'=>self::text($workflow['generated_at'] ?? ''),
                    'build'=>self::fields((array)($workflow['build'] ?? []), ['product','installation_id','build_id','source_commit','version']),
                    'input_evidence_ids'=>self::strings($row['input_evidence_ids'] ?? []),
                    'input_evidence_count'=>is_array($row['input_evidence_ids'] ?? null) ? count($row['input_evidence_ids']) : 0,
                    'uncertainty'=>self::strings($workflow['uncertainty']['items'] ?? []),
                    'adaptation_reason'=>self::text($workflow['adaptation']['reason'] ?? ''),
                    'adaptation_minimum_cases'=>self::integer($workflow['adaptation']['minimum_cases'] ?? null),
                    'adaptation_evidence_ids'=>self::strings($workflow['adaptation']['evidence_ids'] ?? [])];
        }
        $predictions = [];
        foreach (self::rows($records['predictions'] ?? []) as $row) {
            $probabilities = [];
            foreach (['home','draw','away'] as $outcome) {
                $value = $row['probabilities'][$outcome] ?? null;
                $numeric = is_int($value) || is_float($value)
                    || (is_string($value) && strlen($value) <= 100 && preg_match('/^\d+(?:\.\d+)?(?:[eE][+-]?\d+)?$/D', $value));
                $probabilities[$outcome] = $numeric && is_finite((float) $value) && (float) $value >= 0 && (float) $value <= 1 ? $value : null;
            }
            $predictions[] = self::fields($row, ['record_id','run_id','model_run_id','target_evidence_id','predicted_at','received_at','usable_at']) + ['probabilities'=>$probabilities];
        }
        $outcomes = [];
        foreach (self::rows($records['outcomes'] ?? []) as $row) {
            $outcomes[] = self::fields($row, ['record_id','source_evidence_id','source_id','fixture_key','outcome','received_at','usable_at']);
        }
        $evaluations = [];
        foreach (self::rows($records['evaluations'] ?? []) as $row) {
            $loss = $row['loss'] ?? null;
            $evaluations[] = self::fields($row, ['record_id','run_id','model','model_version','metric','evaluation_cutoff','received_at','usable_at'])
                + ['sample_size'=>self::integer($row['sample_size'] ?? null),
                    'loss'=>(is_float($loss) || is_int($loss)) && is_finite((float) $loss) ? $loss : null,
                    'scope'=>self::fields((array) ($row['evaluation_scope'] ?? []), ['source_id','competition','period','settlement'])];
        }
        return ['match'=>['id'=>$id,'home'=>self::text($match['home']['name'] ?? ''),'away'=>self::text($match['away']['name'] ?? ''),
                'status'=>self::text($match['status'] ?? ''),'event_date'=>self::text($match['event_date'] ?? ''),
                'competition'=>self::text($match['competition'] ?? ''),'source_id'=>self::text($history['source_id'] ?? '')],
            'workflow_version'=>self::text($history['workflow_version'] ?? ''),'cutoff'=>self::text($history['cutoff'] ?? ''),
            'target_evidence_id'=>self::text($history['target_evidence_id'] ?? ''),'fixture_key'=>self::text($history['fixture_key'] ?? ''),
            'models'=>$models,'predictions'=>$predictions,'outcomes'=>$outcomes,'evaluations'=>$evaluations,
            'counts'=>array_combine(['models','predictions','outcomes','evaluations'], array_map(static fn($kind): int => is_array($records[$kind] ?? null) ? count($records[$kind]) : 0, ['models','predictions','outcomes','evaluations'])),
            'forecast_available'=>($match['status'] ?? '') === 'scheduled' && empty($match['score']),
            'limitations'=>self::strings($history['limitations'] ?? []),
            'holdout_mode'=>self::text($history['present_knowledge_holdout']['mode'] ?? ''),
            'holdout_available'=>($history['present_knowledge_holdout']['available'] ?? false) === true,
            'holdout_reason'=>self::text($history['present_knowledge_holdout']['reason'] ?? '')];
    }

    public static function formKey(object $app, string $id, string $operation): string
    {
        $slot = self::slot($id, $operation);
        $key = $app->getUserState($slot, '');
        if (!is_string($key) || !preg_match('/^[a-f0-9]{32}$/D', $key)) {
            $key = bin2hex(random_bytes(16));
            $app->setUserState($slot, $key);
        }
        return $key;
    }

    public static function slot(string $id, string $operation): string
    {
        self::matchId($id);
        if (!in_array($operation, ['forecasts','evaluations'], true)) { throw new \RuntimeException('INVALID_WORKFLOW_OPERATION'); }
        return 'com_dragonhydra.workflow.' . $operation . '.' . $id;
    }

    public static function submit(callable $request, string $id, string $operation, string $key, string $expected): array
    {
        self::slot($id, $operation);
        if (!preg_match('/^[a-f0-9]{32}$/D', $key) || !$expected || !hash_equals($expected, $key)) {
            throw new \RuntimeException('INVALID_WORKFLOW_COMMAND', 403);
        }
        $job = $request('POST', '/matches/' . $id . '/' . $operation, [], $key);
        if (!preg_match('/^[a-f0-9]{32}$/D', self::text($job['id'] ?? ''))) { throw new \RuntimeException('INVALID_WORKFLOW_JOB'); }
        return ['id'=>$job['id']];
    }

    private static function text(mixed $value): string { return is_scalar($value) ? substr((string) $value, 0, 1500) : ''; }
    private static function integer(mixed $value): ?int { return is_int($value) && $value >= 0 ? $value : null; }
    private static function rows(mixed $rows): array { return is_array($rows) ? array_values(array_filter(array_slice($rows, 0, 100), 'is_array')) : []; }
    private static function strings(mixed $rows): array { return is_array($rows) ? array_values(array_filter(array_map([self::class,'text'], array_slice($rows,0,100)))) : []; }
    private static function fields(array $row, array $fields): array
    {
        $result = []; foreach ($fields as $field) { $result[$field] = self::text($row[$field] ?? ''); } return $result;
    }
}
