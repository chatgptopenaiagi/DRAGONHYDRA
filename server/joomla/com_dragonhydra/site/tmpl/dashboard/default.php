<?php
defined('_JEXEC') or die;

use Joomla\CMS\Factory;
use Joomla\CMS\HTML\HTMLHelper;
use Joomla\CMS\Router\Route;
use Joomla\CMS\Uri\Uri;

$workspace = is_array($this->workspace ?? null) ? $this->workspace : [];
$sections = ['overview'=>'Overview', 'matches'=>'Matches', 'teams'=>'Teams', 'competitions'=>'Competitions', 'analysis'=>'Analysis', 'reports'=>'Reports', 'connections'=>'Connections'];
$section = array_key_exists($workspace['section'] ?? '', $sections) ? $workspace['section'] : 'overview';
$authenticated = !empty($workspace['authenticated']);
$app = Factory::getApplication();
$identity = $app->getIdentity();
$signedIn = !$identity->guest;
$denied = !empty($workspace['permission_denied']);
$itemid = (int) ($workspace['itemid'] ?? $app->input->getInt('Itemid', 0));
$escape = static fn($value): string => htmlspecialchars((string) $value, ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8');
$route = static function (array $params = []) use ($itemid): string {
    $params = ['option'=>'com_dragonhydra'] + $params;
    if ($itemid > 0) { $params['Itemid'] = $itemid; }
    return Route::_('index.php?' . http_build_query($params, '', '&', PHP_QUERY_RFC3986), false);
};
$home = $route(['section'=>'overview']);
$returnUrl = Uri::root() . ltrim($home, '/');
if (str_starts_with($home, Uri::root())) { $returnUrl = $home; }
$login = Route::_('index.php?option=com_users&view=login&return=' . rawurlencode(base64_encode($returnUrl)) . ($itemid ? '&Itemid=' . $itemid : ''), false);
$admin = Uri::root() . 'administrator/index.php?option=com_dragonhydra';
$filters = (array) ($workspace['filters'] ?? []);
$summary = (array) ($workspace['summary'] ?? []);
$match = is_array($workspace['match'] ?? null) ? $workspace['match'] : null;
$items = static fn($value): array => is_array($value) ? (array) ($value['items'] ?? []) : [];
$date = static function ($value, bool $clock = false): string {
    if (!is_string($value) || $value === '') { return 'Not recorded'; }
    try {
        $parsed = new DateTimeImmutable($value, new DateTimeZone('UTC'));
        return $clock ? $parsed->setTimezone(new DateTimeZone('UTC'))->format('d M Y, H:i \U\T\C') : $parsed->format('d M Y');
    } catch (Throwable $error) { return 'Date unavailable'; }
};
$score = static fn(array $row): string => isset($row['score']['home'], $row['score']['away']) ? (string) $row['score']['home'] . ' – ' . (string) $row['score']['away'] : '—';
$status = static fn(array $row): string => ucfirst((string) ($row['status'] ?? 'Unknown'));
$number = static fn($value): string => is_numeric($value) ? number_format((float) $value, 0, '.', ',') : '—';
$external = static function ($value): ?string {
    if (!is_string($value)) { return null; }
    $parts = parse_url($value);
    if (!$parts || ($parts['scheme'] ?? '') !== 'https' || empty($parts['host']) || isset($parts['user']) || isset($parts['pass']) || isset($parts['query'])) { return null; }
    return $value;
};
$matchList = static function (array $rows, string $label) use ($escape, $route, $date, $score, $status): void {
    if (!$rows) { echo '<p class="dh-empty">No retained matches are available for this selection.</p>'; return; }
    echo '<div class="dh-match-list" aria-label="' . $escape($label) . '">';
    foreach ($rows as $row) {
        echo '<a class="dh-fixture" href="' . $escape($route(['section'=>'matches', 'match_id'=>(string) ($row['id'] ?? '')])) . '">';
        echo '<span class="dh-fixture-date">' . $escape($date($row['event_date'] ?? null)) . '<small>' . $escape($status($row)) . '</small></span>';
        echo '<span class="dh-fixture-teams"><strong>' . $escape($row['home']['name'] ?? 'Unknown home team') . '</strong><span>' . $escape($row['away']['name'] ?? 'Unknown away team') . '</span><small>' . $escape($row['competition'] ?? 'Competition not recorded') . '</small></span>';
        echo '<span class="dh-fixture-score">' . $escape($score($row)) . '<small>' . (isset($row['score']) ? 'Source score' : 'No score supplied') . '</small></span><span class="dh-arrow" aria-hidden="true">↗</span></a>';
    }
    echo '</div>';
};
$exportForm = static function (array $row) use ($escape, $route): void {
    if (empty($row['id'])) { return; }
    echo '<div class="dh-actions" aria-label="Export formats">';
    foreach (['json'=>'JSON', 'csv'=>'CSV', 'xlsx'=>'Excel (.xlsx)'] as $format=>$label) {
        echo '<form method="post" action="' . $escape($route(['task'=>'actions.export'])) . '"><input type="hidden" name="match_id" value="' . $escape($row['id']) . '"><input type="hidden" name="format" value="' . $format . '"><button class="dh-button" type="submit">Export ' . $label . '</button>' . HTMLHelper::_('form.token') . '</form>';
    }
    echo '</div>';
};
$health = (array) ($workspace['health'] ?? []);
$ready = $authenticated && ($health['status'] ?? '') === 'ready';
?>
<div class="dh-workspace" data-dragonhydra-workspace>
  <a class="dh-skip" href="#dh-main">Skip to sports workspace</a>
  <header class="dh-header">
    <a class="dh-brand" href="<?= $escape($home) ?>" aria-label="DRAGONHYDRA CORE NEXT overview"><span class="dh-brand-mark" aria-hidden="true">D</span><span>DRAGONHYDRA<small>CORE NEXT · SPORTS INTELLIGENCE</small></span></a>
    <div class="dh-header-tools">
      <span class="dh-service <?= $ready ? 'is-ready' : '' ?>"><span aria-hidden="true"></span><?= $authenticated ? ($ready ? 'Backend available' : 'Backend unavailable') : 'Private local workspace' ?></span>
      <?php if ($signedIn): ?>
        <span class="dh-user"><?= $escape($identity->name ?: $identity->username) ?></span>
        <form method="post" action="<?= $escape(Route::_('index.php?option=com_users&task=user.logout' . ($itemid ? '&Itemid=' . $itemid : ''), false)) ?>"><input type="hidden" name="return" value="<?= $escape(base64_encode($home)) ?>"><button type="submit" class="dh-link-button">Sign out</button><?= HTMLHelper::_('form.token') ?></form>
      <?php else: ?><a class="dh-button dh-button-small" href="<?= $escape($login) ?>">Sign in</a><?php endif; ?>
    </div>
  </header>
  <?php if ($authenticated): ?>
    <nav class="dh-navigation" aria-label="Sports workspace">
      <?php foreach ($sections as $key=>$label): ?><a href="<?= $escape($route(['section'=>$key])) ?>" <?= $key === $section ? 'aria-current="page"' : '' ?>><?= $escape($label) ?></a><?php endforeach; ?>
      <a class="dh-admin-link" href="<?= $escape($admin) ?>" target="_blank" rel="noopener noreferrer">Administration <span aria-hidden="true">↗</span></a>
    </nav>
  <?php endif; ?>
  <main id="dh-main" class="dh-main" tabindex="-1">
  <?php if ($denied): ?>
    <section class="dh-panel" role="alert"><p class="dh-eyebrow">PERMISSION REQUIRED</p><h1>This account cannot open the sports workspace</h1><p class="dh-lead">You are signed in, but this account does not have permission to read DRAGONHYDRA data. Ask the workstation owner to review its component permissions, or sign out before using an authorized account.</p></section>
  <?php elseif (!$authenticated): ?>
    <section class="dh-welcome" aria-labelledby="dh-welcome-title"><p class="dh-eyebrow">EVIDENCE BEFORE OPINION</p><h1 id="dh-welcome-title">Your sports.<br><span>A clearer view.</span></h1><p class="dh-lead">One place to explore retained matches, compare teams and follow the evidence behind every analysis.</p><div class="dh-actions"><a class="dh-button dh-button-primary" href="<?= $escape($login) ?>">Sign in to your workspace <span aria-hidden="true">→</span></a><a class="dh-button" href="<?= $escape(Uri::root() . 'administrator/') ?>">Administrator access</a></div><p class="dh-privacy-note">This is your local Joomla workspace. Sign in with an authorized Joomla account to view private sports records.</p></section>
    <div class="dh-feature-grid"><article class="dh-feature"><span class="dh-feature-number">01</span><h2>Explore the record</h2><p>Find matches, teams and competitions in your retained source data.</p></article><article class="dh-feature"><span class="dh-feature-number">02</span><h2>Understand the evidence</h2><p>Read existing analysis with source identity, timing and clear limits.</p></article><article class="dh-feature"><span class="dh-feature-number">03</span><h2>Take your findings further</h2><p>Download supported reports and manage providers through protected administration.</p></article></div>
  <?php elseif (!empty($workspace['error'])): ?>
    <section class="dh-panel dh-error" role="alert"><p class="dh-eyebrow"><?= $ready ? 'REQUEST STATUS' : 'CONNECTION STATUS' ?></p><h1><?= $ready ? 'The requested information is unavailable' : 'The workspace is temporarily unavailable' ?></h1><p><?= $escape($workspace['error']) ?></p><p><?= $ready ? 'Your local backend is available. This requested record or operation could not be completed. Choose another retained match or return to the overview.' : 'Your retained data has not been replaced. Check the local server or try this page again.' ?></p><div class="dh-actions"><a class="dh-button dh-button-primary" href="<?= $escape($route(['section'=>$ready ? 'matches' : $section])) ?>"><?= $ready ? 'Browse retained matches' : 'Try again' ?></a><a class="dh-button" href="<?= $escape($admin) ?>">Open administration</a></div></section>
  <?php else: ?>
    <?php require __DIR__ . '/section-' . $section . '.php'; ?>
  <?php endif; ?>
  </main>
  <footer class="dh-footer"><span>Evidence before opinion.</span><span><?= $authenticated ? 'Retained source data · Receipt timestamps shown in UTC' : 'Joomla-native · Local access only' ?></span></footer>
</div>
