<?php
/** Isolated actual-administrator-template rendering; no installed configuration or network I/O. */
declare(strict_types=1);
namespace Joomla\CMS\HTML { final class HTMLHelper { public static function _($name): string { return '<input type="hidden" name="fixture_csrf_only" value="1">'; } } }
namespace Joomla\CMS\Router { final class Route { public static function _(string $url, bool $xhtml = true): string { return $url; } } }
namespace Joomla\CMS\Uri { final class Uri { public static function root(): string { return 'http://127.0.0.1/'; } } }
namespace Joomla\CMS\Language { final class Text {
    public static function _(string $key): string { return $GLOBALS['fixture_language'][$key] ?? $key; }
} }
namespace {
    define('_JEXEC', 1);
    $root = dirname(__DIR__, 2);
    require $root . '/server/joomla/com_dragonhydra/admin/src/Service/SystemModules.php';
    require $root . '/server/joomla/com_dragonhydra/admin/src/Service/SystemWorkflow.php';
    use Dragonhydra\Component\Dragonhydra\Administrator\Service\SystemModules;
    use Dragonhydra\Component\Dragonhydra\Administrator\Service\SystemWorkflow;
    $scenario = PHP_SAPI === 'cli' ? ($argv[1] ?? 'normal') : ($_GET['scenario'] ?? 'normal');
    if (!in_array($scenario, ['normal','empty','unavailable','expired','escaped','filtered','missing','workflow','finished','reader','workflow_error','pending_job','failed_job'], true)) {
        http_response_code(400); echo 'Unknown isolated fixture scenario'; exit;
    }
    $now = time();
    $registry = ['schema_version'=>1,'registry_version'=>'module-registry/1','as_of'=>gmdate('c',$now),
        'read_only'=>true,'core_state'=>'ready','modules'=>[],'password'=>'PRIVATE_FIXTURE_SECRET'];
    $definition = ['schema_version'=>1,'module_id'=>'data_engine','display_name'=>'Synthetic fixture data engine',
        'category'=>'data','kind'=>'service','description'=>'Isolated rendering example; no production state.',
        'actual_build_or_module_version'=>'fixture-only','required_for_core'=>true,
        'implemented_capabilities'=>['Retained fixture reads'], 'data_domains'=>['Synthetic fixtures'],
        'implementation_reference'=>['fixture/module.py'], 'verification_refs'=>['fixture/test.py'],
        'configuration_requirements'=>[['reference'=>'owned_store','description'=>'Existing local store','required'=>true]],
        'private_config'=>'PRIVATE_FIXTURE_SECRET'];
    $observation = ['module_id'=>'data_engine','observed_at'=>gmdate('c',$now),'evidence_expires_at'=>gmdate('c',$now+300),
        'last_success_at'=>null,'runtime_state'=>'ready','implementation_state'=>'implemented','configuration_state'=>'configured',
        'reason_code'=>'FIXTURE_ONLY','reason'=>'Synthetic fixture storage is available.',
        'sanitized_metrics'=>['table_count'=>3,'configured'=>true,'password'=>'PRIVATE_FIXTURE_SECRET'],
        'evidence_reference'=>['fixture/isolated-receipt.json']];
    $module = ['definition'=>$definition,'observation'=>$observation,'dependencies'=>[],
        'operations'=>[['operation_id'=>'read_matches','label'=>'Browse retained matches','kind'=>'http','available'=>true,'read_only'=>true],
            ['operation_id'=>'create_export','label'=>'Create export','kind'=>'http','available'=>true,'read_only'=>false],
            ['operation_id'=>'cli_memory_history','label'=>'Memory history CLI','kind'=>'cli','available'=>false,'read_only'=>true,'reason'=>'This CLI operation is not exposed through Joomla.'],
            ['operation_id'=>'unknown_operation','label'=>'Unmapped operation','kind'=>'http','available'=>true,'read_only'=>true,'reference'=>'https://untrusted.invalid/PRIVATE_FIXTURE_SECRET']]];
    if ($scenario === 'expired') { $module['observation']['evidence_expires_at'] = gmdate('c',$now-10); }
    if ($scenario === 'escaped') {
        $module['definition']['display_name'] = '<script>fixture_attack()</script>';
        $module['observation']['reason'] = 'Fixture <img src=x onerror=fixture_attack()> & "quoted"';
    }
    if ($scenario !== 'empty') { $registry['modules'][] = $module; }
    $control = SystemModules::project($registry, $scenario === 'filtered' ? 'optional_ai' : '', '', $scenario === 'missing' ? 'unknown_module' : 'data_engine');
    $GLOBALS['fixture_language'] = parse_ini_file($root . '/server/joomla/com_dragonhydra/admin/language/en-GB/com_dragonhydra.ini');
    $view = new class {
        public string $section = 'control'; public array $control; public ?string $error = null;
        public array $data = []; public string $jobId = ''; public bool $canImport = false; public array $probe = []; public string $dashboardUrl = '';
        public array $workflow = []; public ?string $workflowError = null; public string $workflowMatchId = ''; public array $workflowKeys = [];
        public function render(string $path): void { require $path; }
    };
    $view->control = $control;
    if ($scenario === 'unavailable') { $view->control = []; $view->error = 'The module registry could not be read through this installation’s protected bridge. No module state was changed.'; }
    if (in_array($scenario, ['workflow','finished','reader','workflow_error'], true)) {
        $id = str_repeat('a',64); $view->workflowMatchId = $id;
        $match = ['id'=>$id,'status'=>$scenario === 'finished' ? 'finished' : 'scheduled',
            'home'=>['name'=>'Synthetic fixture home'],'away'=>['name'=>'Synthetic fixture away'],
            'competition'=>'Synthetic fixture league','event_date'=>'2099-01-01'];
        $history = ['workflow_version'=>'system-workflow/1','match_id'=>$id,'cutoff'=>gmdate('c',$now),
            'target_evidence_id'=>'synthetic-target-evidence','source_id'=>'synthetic-source','fixture_key'=>'synthetic-fixture-key',
            'records'=>['models'=>[['record_id'=>'synthetic-model-record','run_id'=>'synthetic-command','model_name'=>'frequency',
                'model_version'=>'fixture-only','data_cutoff'=>gmdate('c',$now-60),'received_at'=>gmdate('c',$now),'usable_at'=>gmdate('c',$now),
                'input_evidence_ids'=>['synthetic-training-evidence'], 'password'=>'PRIVATE_FIXTURE_SECRET',
                'parameters'=>['workflow'=>['generated_at'=>gmdate('c',$now),'uncertainty'=>['items'=>['Synthetic fixture uncertainty only.']],
                    'adaptation'=>['reason'=>'INSUFFICIENT_COMPARABLE_OPERATIONAL_EVALUATIONS','minimum_cases'=>20,'evidence_ids'=>[]]]]]],
                'predictions'=>[['record_id'=>'synthetic-prediction-record','model_run_id'=>'synthetic-model-record','target_evidence_id'=>'synthetic-target-evidence',
                    'probabilities'=>['home'=>'0.4','draw'=>'0.3','away'=>'0.3'],'predicted_at'=>gmdate('c',$now)]],
                'outcomes'=>[],'evaluations'=>[]],
            'present_knowledge_holdout'=>['mode'=>'PRESENT_KNOWLEDGE_CHRONOLOGICAL_HOLDOUT','available'=>false,'reason'=>'EXPLICIT_DIAGNOSTIC_NOT_REQUESTED'],
            'limitations'=>['Synthetic fixture only: a stored forecast is not proof of skill.']];
        $view->workflow = SystemWorkflow::project($match,$history);
        $view->canImport = $scenario !== 'reader';
        $view->workflowKeys = ['forecasts'=>str_repeat('f',32),'evaluations'=>str_repeat('e',32)];
        if ($scenario === 'workflow_error') { $view->workflow = []; $view->workflowError = 'Retained workflow history is not available for this match.'; }
    }
    if (in_array($scenario, ['pending_job','failed_job'], true)) {
        $view->section = 'jobs'; $view->jobId = str_repeat('b',32);
        $view->data = ['kind'=>'evaluation','id'=>$view->jobId,'status'=>'succeeded','progress'=>100,
            'payload'=>['match_id'=>str_repeat('a',64)],'result'=>['status'=>'pending','reason'=>'LATER_RETAINED_OUTCOME_UNAVAILABLE']];
        if ($scenario === 'failed_job') {
            $view->data['status'] = 'failed'; $view->data['result'] = null;
            $view->data['error'] = ['code'=>'FIXTURE_WORKFLOW_FAILED','message'=>'PRIVATE_FIXTURE_SECRET'];
        }
    }
    header('Content-Type: text/html; charset=utf-8'); header('Cache-Control: no-store');
    echo '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Isolated System Control Center fixture</title><style>body{font-family:system-ui;margin:1rem;background:#e9eef3}a{color:#075a83}.btn{display:inline-block;text-decoration:none;padding:.6rem .8rem;border:1px solid #9aacbc;border-radius:.3rem}.nav{display:flex;gap:1rem;flex-wrap:wrap}.nav-link{padding:.5rem}';
    echo file_get_contents($root . '/server/joomla/com_dragonhydra/media/css/control.css');
    echo '</style></head><body><p>Isolated template fixture — no installed configuration, credentials or backend requests.</p>';
    $view->render($root . '/server/joomla/com_dragonhydra/admin/tmpl/dashboard/default.php');
    echo '</body></html>';
}
