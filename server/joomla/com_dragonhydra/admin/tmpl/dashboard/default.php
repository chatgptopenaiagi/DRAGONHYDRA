<?php
defined('_JEXEC') or die;
use Joomla\CMS\HTML\HTMLHelper;
use Joomla\CMS\Language\Text;
use Joomla\CMS\Router\Route;

$escape = static fn($value): string => htmlspecialchars((string) $value, ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8');
$route = static fn(string $query): string => Route::_('index.php?option=com_dragonhydra&' . $query, false);
$sections = ['sources'=>'SOURCES','matches'=>'MATCHES','odds'=>'ODDS','models'=>'MODELS','research'=>'RESEARCH','databases'=>'DATABASES','system'=>'SYSTEM'];
$json = static fn($value): string => htmlspecialchars(json_encode($value, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES), ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8');
?>
<div class="container-fluid dragonhydra-administration">
  <p><?= Text::_('COM_DRAGONHYDRA_INTRO') ?></p>
  <nav class="nav nav-pills gap-2 mb-4" aria-label="DRAGONHYDRA administration sections">
    <?php foreach ($sections as $key => $language): ?>
      <a class="nav-link<?= $this->section === $key ? ' active' : '' ?>" <?= $this->section === $key ? 'aria-current="page"' : '' ?> href="<?= $escape($route('section=' . $key)) ?>"><?= Text::_('COM_DRAGONHYDRA_' . $language) ?></a>
    <?php endforeach; ?>
  </nav>
  <?php if ($this->error): ?>
    <div class="alert alert-warning" role="alert"><strong><?= Text::_('COM_DRAGONHYDRA_REQUEST_FAILED') ?></strong> <?= $escape($this->error) ?>
      <p class="mt-2 mb-0"><?= Text::_('COM_DRAGONHYDRA_RECOVERY') ?></p>
    </div>
    <a class="btn btn-primary" href="<?= $escape($route('section=' . $this->section . ($this->jobId ? '&job_id=' . rawurlencode($this->jobId) : ''))) ?>"><?= Text::_('COM_DRAGONHYDRA_RETRY') ?></a>
  <?php elseif ($this->section === 'sources'): ?>
    <h2><?= Text::_('COM_DRAGONHYDRA_SOURCES') ?></h2>
    <p><?= Text::_('COM_DRAGONHYDRA_SOURCE_FLOW') ?></p>
    <?php if ($this->probe): ?><div class="alert alert-info" role="status"><strong><?= Text::_('COM_DRAGONHYDRA_PROOF') ?></strong><pre><?= $json($this->probe) ?></pre></div><?php endif; ?>
    <div class="table-responsive"><table class="table table-striped">
      <caption><?= Text::_('COM_DRAGONHYDRA_SOURCE_CAPTION') ?></caption>
      <thead><tr><th scope="col">Source</th><th scope="col">Status and coverage</th><th scope="col">Imported records</th><th scope="col">Actions</th></tr></thead>
      <tbody><?php foreach (($this->data['items'] ?? []) as $source): ?>
        <tr><th scope="row"><?= $escape($source['name'] ?? $source['id']) ?></th>
          <td><?= $escape($source['status'] ?? 'Unknown') ?><p class="mb-1"><?= $escape($source['reason'] ?? '') ?></p><small><?= $escape(implode(', ', $source['capabilities'] ?? [])) ?></small></td>
          <td><?= $escape($source['record_count'] ?? 0) ?><br><small><?= $escape($source['last_import'] ?? 'No successful import') ?></small></td>
          <td>
            <?php $registration = parse_url((string) ($source['registration_url'] ?? '')); ?>
            <?php if ($registration && ($registration['scheme'] ?? '') === 'https'): ?><a class="btn btn-outline-secondary btn-sm mb-2" href="<?= $escape($source['registration_url']) ?>" target="_blank" rel="noopener noreferrer">Register with provider</a><?php endif; ?>
            <?php if ($this->canImport && ($source['implemented'] ?? false)): ?>
              <form method="post" action="<?= $escape($route('task=actions.probe')) ?>" class="mb-2">
                <input type="hidden" name="connection_id" value="<?= $escape($source['id']) ?>">
                <button class="btn btn-outline-primary btn-sm" type="submit">Check capabilities</button><?= HTMLHelper::_('form.token') ?>
              </form>
              <?php if ($source['id'] === 'openfootball'): ?><form method="post" action="<?= $escape($route('task=actions.sync')) ?>">
                <button class="btn btn-primary btn-sm" type="submit">Import public results</button><?= HTMLHelper::_('form.token') ?>
              </form><?php endif; ?>
            <?php elseif (!$this->canImport): ?><p>Read access. Ask an administrator with Import permission to synchronize this source.</p><?php endif; ?>
          </td></tr>
      <?php endforeach; ?></tbody>
    </table></div>
    <a class="btn btn-outline-primary" href="<?= $escape($route('section=matches')) ?>">Open imported matches</a>
  <?php elseif ($this->section === 'matches'): ?>
    <h2><?= Text::_('COM_DRAGONHYDRA_MATCHES') ?></h2>
    <?php if (isset($this->data['match'])): $match = $this->data['match']; ?>
      <h3><?= $escape($match['home']['name'] ?? '') ?> — <?= $escape($match['away']['name'] ?? '') ?></h3>
      <dl class="row">
        <dt class="col-sm-3">Competition / season</dt><dd class="col-sm-9"><?= $escape($match['competition'] ?? '') ?> / <?= $escape($match['season'] ?? '') ?></dd>
        <dt class="col-sm-3">Source event date</dt><dd class="col-sm-9"><?= $escape($match['event_date'] ?? '') ?></dd>
        <dt class="col-sm-3">State</dt><dd class="col-sm-9"><?= $escape($match['status'] ?? '') ?> / <?= $escape($match['data_state'] ?? '') ?></dd>
        <dt class="col-sm-3">Full-time score</dt><dd class="col-sm-9"><?= isset($match['score']) ? $escape($match['score']['home'] . ' – ' . $match['score']['away']) : 'Not supplied' ?></dd>
      </dl>
      <?php if ($this->dashboardUrl): ?><a class="btn btn-primary" href="<?= $escape(rtrim($this->dashboardUrl, '/') . '/#match/' . rawurlencode($match['id'])) ?>" target="_blank" rel="noopener">Open dashboard</a><?php endif; ?>
      <a class="btn btn-outline-secondary" href="<?= $escape($route('section=matches')) ?>">Back to matches</a>
      <details class="mt-3"><summary>Technical details and evidence</summary><pre><?= $json($match) ?></pre></details>
    <?php else: ?>
      <p><?= $escape($this->data['total'] ?? 0) ?> retained matches. No data is imported by opening this page.</p>
      <?php if (empty($this->data['items'])): ?><div class="alert alert-info">Import public results from Data sources, then return here.</div><?php endif; ?>
      <div class="table-responsive"><table class="table table-striped">
        <caption>Kernel canonical matches; dates retain source precision.</caption>
        <thead><tr><th scope="col">Date</th><th scope="col">Match</th><th scope="col">Competition</th><th scope="col">State / score</th></tr></thead>
        <tbody><?php foreach (($this->data['items'] ?? []) as $match): ?><tr>
          <td><?= $escape($match['event_date']) ?></td><th scope="row"><a href="<?= $escape($route('section=matches&match_id=' . rawurlencode($match['id']))) ?>"><?= $escape($match['home']['name']) ?> — <?= $escape($match['away']['name']) ?></a></th>
          <td><?= $escape($match['competition']) ?></td><td><?= $escape($match['status']) ?> <?= isset($match['score']) ? $escape($match['score']['home'] . ' – ' . $match['score']['away']) : '' ?></td>
        </tr><?php endforeach; ?></tbody>
      </table></div>
      <?php $offset = (int) ($this->data['offset'] ?? 0); $limit = (int) ($this->data['limit'] ?? 50); ?>
      <?php if ($offset > 0): ?><a class="btn btn-outline-secondary" href="<?= $escape($route('section=matches&offset=' . max(0, $offset - $limit))) ?>">Previous page</a><?php endif; ?>
      <?php if ($offset + $limit < (int) ($this->data['total'] ?? 0)): ?><a class="btn btn-outline-secondary" href="<?= $escape($route('section=matches&offset=' . ($offset + $limit))) ?>">Next page</a><?php endif; ?>
    <?php endif; ?>
  <?php elseif ($this->section === 'jobs'): ?>
    <h2>Import job</h2>
    <p role="status">State: <strong><?= $escape($this->data['status'] ?? 'Unknown') ?></strong></p>
    <progress max="100" value="<?= $escape($this->data['progress'] ?? 0) ?>" aria-label="Job progress"><?= $escape($this->data['progress'] ?? 0) ?>%</progress>
    <?php if (!empty($this->data['error'])): ?><p class="alert alert-danger"><?= $escape(is_array($this->data['error']) ? json_encode($this->data['error']) : $this->data['error']) ?></p><?php endif; ?>
    <div class="my-3"><a class="btn btn-primary" href="<?= $escape($route('section=jobs&job_id=' . rawurlencode($this->jobId))) ?>">Refresh job status</a>
      <?php if (($this->data['status'] ?? '') === 'succeeded'): ?><a class="btn btn-success" href="<?= $escape($route('section=matches')) ?>">View imported matches</a><?php endif; ?></div>
    <?php if ($this->canImport && in_array($this->data['status'] ?? '', ['queued','running'], true)): ?><form method="post" action="<?= $escape($route('task=actions.cancel')) ?>"><input type="hidden" name="job_id" value="<?= $escape($this->jobId) ?>"><button class="btn btn-outline-danger" type="submit">Cancel import</button><?= HTMLHelper::_('form.token') ?></form><?php endif; ?>
    <details><summary>Job result and retained evidence references</summary><pre><?= $json($this->data) ?></pre></details>
  <?php else: ?>
    <h2><?= Text::_('COM_DRAGONHYDRA_' . $sections[$this->section]) ?></h2>
    <?php if ($this->section === 'odds'): ?><p>Provider/feed mappings and market snapshots remain kernel-owned. The public OpenFootball results connector supplies no odds. Open a match in the dashboard to inspect only compatible retained markets and their freshness.</p>
    <?php elseif ($this->section === 'models'): ?><p>The existing kernel provides frequency, Poisson, recency, Elo and ensemble forecasts. Match analysis uses eligible evidence. Local LLM installation, training and inference administration are not enabled in this extension version.</p>
    <?php elseif ($this->section === 'research'): ?><p>Kernel CLI research memory remains available. Editing tasks from Joomla is not enabled in this extension version. Use match analysis to review retained evidence and missing information.</p>
    <?php elseif ($this->section === 'databases'): ?><p>Canonical writes belong to the kernel. This Joomla extension does not edit sports tables or connect Joomla to SQL Server. External SQL Server/PostgreSQL publication is not enabled in this extension version.</p>
    <?php elseif ($this->section === 'system'): ?><p>Current API status and selected storage backend are reported below. Database cutover, backup restoration and service installation require separate verified product tooling.</p><?php endif; ?>
    <dl class="row"><dt class="col-sm-3">Kernel status</dt><dd class="col-sm-9"><?= $escape($this->data['status'] ?? 'Unknown') ?></dd><dt class="col-sm-3">Selected backend</dt><dd class="col-sm-9"><?= $escape($this->data['backend'] ?? 'Not reported') ?></dd></dl>
    <?php if ($this->dashboardUrl): ?><a class="btn btn-primary" href="<?= $escape($this->dashboardUrl) ?>" target="_blank" rel="noopener">Open DRAGONHYDRA dashboard</a><?php endif; ?>
    <details class="mt-3"><summary>System diagnostics</summary><pre><?= $json($this->data) ?></pre></details>
  <?php endif; ?>
</div>
