<?php
/** Isolated rendering of real templates; no Joomla configuration, credentials or backend I/O. */
declare(strict_types=1);

namespace Joomla\CMS {
    final class Factory {
        public static function getApplication(): object {
            return new class {
                public object $input;
                public function __construct() { $this->input = new class { public function getInt(string $key, int $default = 0): int { return $default; } }; }
                public function getIdentity(): object { return (object) ['guest'=>empty($GLOBALS['fixture_authenticated']), 'name'=>'Isolated fixture reviewer', 'username'=>'fixture-reviewer']; }
            };
        }
    }
}
namespace Joomla\CMS\HTML {
    final class HTMLHelper { public static function _($name): string { return '<input type="hidden" name="fixture_csrf_only" value="1">'; } }
}
namespace Joomla\CMS\Router {
    final class Route { public static function _(string $url, bool $xhtml = true): string { return $url; } }
}
namespace Joomla\CMS\Uri {
    final class Uri { public static function root(): string { return 'http://127.0.0.1/'; } }
}
namespace {
    define('_JEXEC', 1);
    $scenario = PHP_SAPI === 'cli' ? ($argv[1] ?? 'empty') : ($_GET['scenario'] ?? 'empty');
    if (!in_array($scenario, ['empty', 'backend_unavailable', 'noanalysis', 'anonymous', 'permission_denied'], true)) {
        http_response_code(400); echo 'Unknown isolated fixture scenario'; exit;
    }
    $root = dirname(__DIR__, 2);
    $GLOBALS['fixture_authenticated'] = !in_array($scenario, ['anonymous'], true);
    $workspace = ['section'=>'overview', 'authenticated'=>$GLOBALS['fixture_authenticated'], 'error'=>null,
        'health'=>['status'=>'ready'], 'summary'=>['total_matches'=>0,'total_teams'=>0,'total_competitions'=>0,'recent'=>[],'upcoming'=>[],'last_retrieval'=>null],
        'matches'=>['items'=>[],'total'=>0,'offset'=>0,'limit'=>25], 'teams'=>['items'=>[]], 'competitions'=>['items'=>[]],
        'match'=>null,'filters'=>[],'analysis'=>null,'predictions'=>null,'connections'=>['items'=>[]]];
    if ($scenario === 'backend_unavailable') { $workspace['error'] = 'The local sports server did not respond within the bounded request. Please retry when it is available.'; $workspace['health'] = []; }
    if ($scenario === 'permission_denied') { $workspace['authenticated'] = false; $workspace['permission_denied'] = true; }
    if ($scenario === 'noanalysis') {
        $workspace['section'] = 'analysis';
        $workspace['match'] = ['id'=>str_repeat('a',64),'home'=>['name'=>'SYNTHETIC fixture home'],'away'=>['name'=>'SYNTHETIC fixture away'],
            'event_date'=>'2000-01-01','status'=>'finished','competition'=>'Isolated rendering fixture only','source_id'=>'SYNTHETIC-render-fixture','received_at'=>null,'score'=>['home'=>0,'away'=>0]];
        $workspace['predictions'] = ['available'=>false,'reason'=>'No prospective forecast was retained for this finished match.','models'=>[],'ensemble'=>null];
    }
    $view = new class { public array $workspace; public function render(string $template): void { require $template; } };
    $view->workspace = $workspace;
    header('Content-Type: text/html; charset=utf-8');
    header('Cache-Control: no-store');
    echo '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Isolated DRAGONHYDRA template fixture</title><style>body{margin:16px;background:#e5eaf0}';
    echo file_get_contents($root . '/server/joomla/com_dragonhydra/media/css/workspace.css');
    echo '</style></head><body><p>Isolated template fixture — no production backend or credentials.</p>';
    $view->render($root . '/server/joomla/com_dragonhydra/site/tmpl/dashboard/default.php');
    echo '</body></html>';
}
