<?php
declare(strict_types=1);
ini_set('display_errors', '0');
header('Cache-Control: no-store');
header('X-Content-Type-Options: nosniff');
header("Content-Security-Policy: default-src 'none'; style-src 'self'; frame-ancestors 'self'; base-uri 'none'; form-action 'none'");
if (!in_array($_SERVER['REMOTE_ADDR'] ?? '', ['127.0.0.1','::1'], true)) { http_response_code(403); exit('Localhost only'); }
if (($_SERVER['REQUEST_METHOD'] ?? '') !== 'GET') { http_response_code(405); exit('Read-only'); }
$host = strtolower(parse_url('http://'.($_SERVER['HTTP_HOST'] ?? ''), PHP_URL_HOST) ?: '');
if (!in_array($host, ['localhost','127.0.0.1','[::1]'], true)) { http_response_code(403); exit('Localhost host required'); }
function esc(mixed $v): string { return htmlspecialchars((string)$v, ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8'); }
try {
    // Runtime configuration and its single-table SELECT credential stay outside htdocs.
    $config = json_decode(file_get_contents(dirname(__DIR__,3).'/DRAGONHYDRA/config/dashboard.local.json'), true, 512, JSON_THROW_ON_ERROR);
    $secret = json_decode(file_get_contents($config['credential_file']), true, 512, JSON_THROW_ON_ERROR);
    if ($secret['username'] !== 'dragonhydra_web') { throw new RuntimeException('Identity mismatch'); }
    mysqli_report(MYSQLI_REPORT_ERROR | MYSQLI_REPORT_STRICT);
    $db = mysqli_init(); $db->options(MYSQLI_OPT_CONNECT_TIMEOUT, 5);
    $db->real_connect('127.0.0.1', $secret['username'], $secret['password'], 'dragonhydra_web', 3306);
    $db->set_charset('utf8mb4');
    $row = $db->query("SELECT payload FROM presentation_cache WHERE cache_key='intelligence'")->fetch_row();
    if (!$row) { throw new RuntimeException('Summary missing'); }
    $dto = json_decode($row[0], true, 512, JSON_THROW_ON_ERROR);
    $bridgeRow = $db->query("SELECT payload FROM presentation_cache WHERE cache_key='desktop_cli_bridge'")->fetch_row();
    $dto['desktop_cli_bridge'] = $bridgeRow ? json_decode($bridgeRow[0], true, 512, JSON_THROW_ON_ERROR) : null;
    if (isset($_GET['format']) && $_GET['format'] === 'json') {
        header('Content-Type: application/json; charset=utf-8');
        echo json_encode($dto, JSON_THROW_ON_ERROR | JSON_HEX_TAG | JSON_HEX_AMP); exit;
    }
} catch (Throwable $e) { http_response_code(503); exit('Intelligence summary unavailable. Run the local summary builder.'); }
?><!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>DRAGONHYDRA Web Intelligence Lab</title><link rel="stylesheet" href="dashboard.css"></head><body>
<header><span class="eyebrow">LOCAL RESEARCH / EVIDENCE FIRST</span><h1>DRAGONHYDRA<br>Web Intelligence Lab</h1><p>Public sports information, traceable observations, and controlled local analysis.</p></header>
<main><section class="cards">
<?php foreach ($dto['counts'] as $label=>$count): ?><article><strong><?=esc($count)?></strong><span><?=esc(str_replace('_',' ',$label))?></span></article><?php endforeach; ?>
</section><section><h2>Pipeline health</h2><dl><dt>MariaDB</dt><dd>Connected · presentation cache</dd><dt>SQL Server at summary time</dt><dd><?=esc($dto['sqlserver'])?></dd><dt>Browser handoff</dt><dd><?=esc($dto['browser_handoff'])?></dd><dt>CLI processor</dt><dd><?=esc($dto['cli_processor'])?> · <?=esc($dto['processing']['status'] ?? 'No run')?></dd><dt>SQL ingestion</dt><dd><?=esc($dto['processing']['items_accepted'] ?? 0)?> accepted in last run</dd><dt>Summary built (UTC)</dt><dd><?=esc($dto['built_at'])?></dd><dt>Last successful fetch</dt><dd><?=esc($dto['last_fetch']['finished_at'] ?? 'None')?> · <?=esc($dto['last_fetch']['source_id'] ?? '')?></dd></dl>
<p>Snapshot freshness: <?=esc(max(0,time()-strtotime($dto['built_at'])))?> seconds. Refresh is explicit; this page does not fetch external data.</p></section>
<p>Latest bridge origin: <?=esc($dto['bridge']['origin'])?> · Desktop browser result: <?=esc($dto['bridge']['desktop_result'])?>. Processing success does not imply browser confirmation.</p>
<?php if ($dto['desktop_cli_bridge']): $b=$dto['desktop_cli_bridge']; ?>
<section><h2>Desktop / CLI data bridge v1</h2><dl>
<dt>Desktop Handoff status</dt><dd><?=esc($b['desktop_handoff_status'])?></dd>
<dt>CLI Consumer status</dt><dd><?=esc($b['consumer_status'])?></dd>
<dt>Capture provenance</dt><dd><?=esc($b['last_attempt_provenance'] ?? $b['provenance'])?></dd>
<dt>SQL Server status at summary time</dt><dd><?=esc($b['sqlserver_status'])?></dd>
<dt>MariaDB status</dt><dd>HEALTHY · read-only cache</dd>
<dt>Last handoff ID</dt><dd><?=esc($b['last_handoff_id'])?></dd>
<dt>Last attempted handoff</dt><dd><?=esc($b['last_attempt_handoff_id'] ?? '')?></dd>
<dt>Last processed source</dt><dd><?=esc($b['last_source'])?></dd>
<dt>Observation count</dt><dd><?=esc($b['observation_count'])?></dd>
<dt>Last processing time</dt><dd><?=esc($b['last_processing_time'])?></dd>
<dt>Rejected handoffs</dt><dd><?=esc($b['rejected_handoffs_count'])?></dd></dl>
<p>Generated <?=esc($b['generated_at'])?>. SYNTHETIC and MANUAL records do not confirm Codex Desktop browsing.</p></section>
<?php endif; ?>
<section><h2>Sports evidence</h2><p>Historical fixtures from OpenFootball (CC0). Source dates are preserved; UTC kickoff is unknown.</p><div class="scroll"><table><thead><tr><th>Fixture</th><th>Result</th><th>Source date</th><th>Observed (UTC)</th><th>Evidence</th></tr></thead><tbody>
<?php foreach ($dto['fixtures'] as $f): ?><tr><td><?=esc($f['home_team'].' — '.$f['away_team'])?></td><td><?=esc(isset($f['home_score']) ? $f['home_score'].' : '.$f['away_score'] : 'Synthetic fixture')?></td><td><?=esc($f['match_date'] ?? 'Not applicable')?></td><td><?=esc($f['observed_at'])?></td><td><?=esc($f['source_id'])?><?php if (!empty($f['source_url'])): ?> · <a href="<?=esc($f['source_url'])?>" rel="noreferrer">Source</a><?php endif; ?></td></tr><?php endforeach; ?>
</tbody></table></div></section>
<section><h2>Synthetic odds demonstration</h2><p class="notice">SYNTHETIC DATA — generated locally. These are not live prices or bookmaker quotes. Confidence describes generator provenance, not outcome probability.</p><div class="scroll"><table><thead><tr><th>Fixture</th><th>Market</th><th>Selection</th><th>Decimal odds</th><th>Implied probability</th><th>Observed (UTC)</th><th>Confidence</th></tr></thead><tbody>
<?php foreach ($dto['odds'] as $o): ?><tr><td><?=esc($o['fixture_id'])?></td><td><?=esc($o['market_key'])?></td><td><?=esc($o['selection'])?></td><td><?=esc($o['decimal_odds'])?></td><td><?=esc(round($o['implied_probability']*100,2))?>%</td><td><?=esc($o['observed_at'])?></td><td><?=esc($o['confidence'])?> · <?=esc($o['verification_state'])?></td></tr><?php endforeach; ?>
</tbody></table></div></section><footer><?=esc($dto['attribution'])?><p>No wagering functionality. <a href="../">Joomla home</a> · <a href="?format=json">Read-only summary JSON</a></p></footer></main></body></html>
