<?php
namespace Dragonhydra\Component\Dragonhydra\Site\Model;
defined('_JEXEC') or die;

use Joomla\CMS\MVC\Model\BaseDatabaseModel;
use Dragonhydra\Component\Dragonhydra\Site\Service\Kernel;

/** Presentation adapter over the existing API. It owns no sports-data store. */
final class WorkspaceModel extends BaseDatabaseModel
{
    private const SECTIONS = ['overview', 'matches', 'teams', 'competitions', 'analysis', 'reports', 'connections'];
    private const STATUSES = ['', 'finished', 'scheduled', 'live'];

    public static function identifier(mixed $value, int $length = 64): string
    {
        $value = (string) $value;
        if ($value !== '' && !preg_match('/^[a-f0-9]{' . $length . '}$/D', $value)) {
            throw new \InvalidArgumentException('INVALID_RESOURCE_IDENTIFIER', 400);
        }
        return $value;
    }

    public static function filters(array $input): array
    {
        $section = (string) ($input['section'] ?? 'overview');
        $search = trim((string) ($input['q'] ?? ''));
        if (strlen($search) > 480 || preg_match('/[\x00-\x1f\x7f]/', $search)) {
            throw new \InvalidArgumentException('INVALID_SEARCH', 400);
        }
        $search = function_exists('mb_substr') ? mb_substr($search, 0, 120, 'UTF-8') : substr($search, 0, 120);
        $status = (string) ($input['status'] ?? '');
        $limit = (int) ($input['limit'] ?? 25);
        return [
            'section' => in_array($section, self::SECTIONS, true) ? $section : 'overview',
            'q' => $search,
            'competition' => self::identifier($input['competition'] ?? ''),
            'team' => self::identifier($input['team'] ?? ''),
            'team_id' => self::identifier($input['team_id'] ?? ''),
            'match_id' => self::identifier($input['match_id'] ?? ''),
            'job_id' => self::identifier($input['job_id'] ?? '', 32),
            'status' => in_array($status, self::STATUSES, true) ? $status : '',
            'limit' => in_array($limit, [10, 25, 50, 100], true) ? $limit : 25,
            'offset' => max(0, min(20000, (int) ($input['offset'] ?? 0))),
        ];
    }

    private static function query(array $values): string
    {
        return http_build_query(array_filter($values, static fn($value): bool => $value !== '' && $value !== null), '', '&', PHP_QUERY_RFC3986);
    }

    public static function filterTeamMatches(array $rows, array $filters): array
    {
        $q = $filters['q'];
        $found = array_values(array_filter($rows, static function (array $row) use ($filters, $q): bool {
            $names = (string) ($row['home']['name'] ?? '') . ' ' . (string) ($row['away']['name'] ?? '');
            $searchMatches = $q === '' || (function_exists('mb_stripos') ? mb_stripos($names, $q, 0, 'UTF-8') !== false : stripos($names, $q) !== false);
            return $searchMatches
                && (!$filters['competition'] || ($row['competition_id'] ?? '') === $filters['competition'])
                && (!$filters['status'] || ($row['status'] ?? '') === $filters['status']);
        }));
        usort($found, static fn($a, $b): int => strcmp(($b['event_date'] ?? '') . ($b['id'] ?? ''), ($a['event_date'] ?? '') . ($a['id'] ?? '')));
        return ['items' => array_slice($found, $filters['offset'], $filters['limit']),
            'total' => count($found), 'limit' => $filters['limit'], 'offset' => $filters['offset'],
            'as_of' => null, 'timestamp_semantics' => 'Retained source event dates; UTC receipt timestamps.'];
    }

    private static function matchPage(callable $read, array $filters): array
    {
        if ($filters['team']) {
            $team = $read('/teams/' . $filters['team']);
            return self::filterTeamMatches((array) ($team['matches'] ?? []), $filters);
        }
        return $read('/matches?' . self::query([
            'search' => $filters['q'], 'competition' => $filters['competition'], 'status' => $filters['status'],
            'limit' => $filters['limit'], 'offset' => $filters['offset'],
        ]));
    }

    private static function upcoming(callable $read): array
    {
        $rows = [];
        $offset = 0;
        do {
            $page = $read('/matches?status=scheduled&limit=200&offset=' . $offset);
            $batch = (array) ($page['items'] ?? []);
            $rows = array_merge($rows, $batch);
            $offset += count($batch);
            if ($offset >= (int) ($page['total'] ?? 0)) {
                break;
            }
            if (!$batch || $offset >= 10000) {
                throw new \RuntimeException('RETAINED_SUMMARY_LIMIT');
            }
        } while (true);
        $today = gmdate('Y-m-d');
        $rows = array_values(array_filter($rows, static fn($row): bool => ($row['event_date'] ?? '') >= $today));
        usort($rows, static fn($a, $b): int => strcmp(($a['event_date'] ?? '') . ($a['id'] ?? ''), ($b['event_date'] ?? '') . ($b['id'] ?? '')));
        return array_slice($rows, 0, 8);
    }

    /** The injected reader is for isolated tests; HTTP input cannot supply one. */
    public function build(array $input, bool $authenticated, ?callable $read = null): array
    {
        $filters = self::filters($input);
        $workspace = [
            'section' => $filters['section'], 'authenticated' => $authenticated,
            'error' => null, 'analysis_error' => null, 'health' => null, 'filters' => $filters,
            'matches' => ['items' => [], 'total' => 0, 'limit' => $filters['limit'], 'offset' => $filters['offset']],
            'match' => null, 'teams' => ['items' => []], 'competitions' => ['items' => []],
            'selectedTeam' => null, 'standings' => null, 'predictions' => null, 'analysis' => null,
            'connections' => ['items' => []], 'job' => null,
            'summary' => ['total_matches' => null, 'total_teams' => null, 'total_competitions' => null,
                'recent' => [], 'upcoming' => [], 'last_retrieval' => null],
            'pagination' => ['has_previous' => false, 'has_next' => false, 'previous_offset' => 0, 'next_offset' => 0],
            'export_formats' => ['json', 'csv', 'xlsx'],
        ];
        if (!$authenticated) {
            return $workspace;
        }
        try {
            if ($read === null) {
                $client = Kernel::client();
                $read = static fn(string $path): array => $client->request('GET', $path);
            }
            $workspace['health'] = $read('/health/ready');
            $section = $filters['section'];
            if (in_array($section, ['overview', 'matches', 'teams', 'competitions', 'analysis', 'reports'], true)) {
                $workspace['teams'] = $read('/teams');
                $workspace['competitions'] = $read('/competitions');
                $workspace['summary']['total_teams'] = count($workspace['teams']['items'] ?? []);
                $workspace['summary']['total_competitions'] = count($workspace['competitions']['items'] ?? []);
            }
            if (in_array($section, ['overview', 'connections'], true)) {
                $workspace['connections'] = $read('/connections');
                $retrievals = array_filter(array_column($workspace['connections']['items'] ?? [], 'last_import'), 'is_string');
                if ($retrievals) {
                    rsort($retrievals);
                    $workspace['summary']['last_retrieval'] = $retrievals[0];
                }
            }
            if ($section === 'overview') {
                $page = $read('/matches?limit=1&offset=0');
                $workspace['summary']['total_matches'] = (int) ($page['total'] ?? 0);
                $workspace['summary']['recent'] = $read('/matches?status=finished&limit=8&offset=0')['items'] ?? [];
                $workspace['summary']['upcoming'] = self::upcoming($read);
            }
            if (in_array($section, ['matches', 'analysis', 'reports'], true)) {
                if ($filters['match_id']) {
                    $workspace['match'] = $read('/matches/' . $filters['match_id']);
                } else {
                    $workspace['matches'] = self::matchPage($read, $filters);
                }
            }
            if ($section === 'teams' && $filters['team_id']) {
                $workspace['selectedTeam'] = $read('/teams/' . $filters['team_id']);
            }
            if ($section === 'competitions' && $filters['competition']) {
                $workspace['standings'] = $read('/competitions/' . $filters['competition'] . '/standings');
            }
            if ($section === 'analysis' && $filters['match_id']) {
                $workspace['predictions'] = $read('/matches/' . $filters['match_id'] . '/predictions');
                try {
                    $workspace['analysis'] = $read('/matches/' . $filters['match_id'] . '/analysis-package');
                } catch (\Throwable $error) {
                    $workspace['analysis_error'] = 'The retained analysis package is not available for this match.';
                }
            }
            if ($section === 'reports' && $filters['job_id']) {
                $job = $read('/jobs/' . $filters['job_id']);
                if (($job['kind'] ?? '') !== 'export') {
                    throw new \RuntimeException('EXPORT_JOB_REQUIRED');
                }
                $workspace['job'] = $job;
            }
            $page = $workspace['matches'];
            $workspace['pagination'] = [
                'has_previous' => $filters['offset'] > 0,
                'has_next' => $filters['offset'] + $filters['limit'] < (int) ($page['total'] ?? 0),
                'previous_offset' => max(0, $filters['offset'] - $filters['limit']),
                'next_offset' => $filters['offset'] + $filters['limit'],
            ];
        } catch (\Throwable $error) {
            $workspace['error'] = $workspace['health'] === null
                ? 'The retained-data service is temporarily unavailable. Saved data and settings are unchanged. Try again or open Administration.'
                : 'The requested retained information is not available. Try another match or filter. Saved data and settings are unchanged.';
        }
        return $workspace;
    }
}
