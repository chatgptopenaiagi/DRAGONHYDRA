<?php
defined('_JEXEC') or die;

use Dragonhydra\Component\Dragonhydra\Administrator\Service\SystemModules;
use Joomla\CMS\Uri\Uri;

$control = $this->control;
$groups = SystemModules::GROUPS;
$states = SystemModules::STATES;
$stamp = static fn(?string $date): string => $date ? gmdate('d M Y, H:i:s', strtotime($date)) . ' UTC' : 'Not recorded';
$tone = static fn(string $state): string => match ($state) { 'ready' => 'good', 'degraded','configured_unverified','installed_not_configured' => 'warning', 'unavailable' => 'danger', default => 'neutral' };
$controlRoute = static fn(array $query = []): string => $route(http_build_query(['section'=>'control'] + $query, '', '&', PHP_QUERY_RFC3986));
$selected = $control['selected'] ?? null;
// Only these existing product pages can be reached from module operations. Backend
// references are evidence text, never browser-selected URLs, commands or tasks.
$operationRoutes = [
    'read_modules' => $controlRoute(), 'read_system' => $route('section=system'),
    'read_matches' => $route('section=matches'), 'read_connections' => $route('section=sources'),
    'read_teams' => Uri::root() . 'index.php?option=com_dragonhydra&section=teams',
    'read_competitions' => Uri::root() . 'index.php?option=com_dragonhydra&section=competitions',
    'read_predictions' => Uri::root() . 'index.php?option=com_dragonhydra&section=analysis',
    'read_analysis_package' => Uri::root() . 'index.php?option=com_dragonhydra&section=analysis',
    'read_cognition_history' => $controlRoute() . '#dc-workflow',
];
?>
<section class="dh-control" aria-labelledby="dc-title">
  <header class="dc-hero">
    <div><div class="dc-eyebrow">DRAGONHYDRA / Workstation administration</div>
      <h2 id="dc-title">System Control Center</h2>
      <p>One evidence-based view of this installation’s infrastructure, retained data and intelligence modules.</p>
      <p class="dc-meta">Read-only registry snapshot<?php if (!empty($control['as_of'])): ?> · <time datetime="<?= $escape($control['as_of']) ?>"><?= $escape($stamp($control['as_of'])) ?></time><?php endif; ?></p>
    </div>
    <a class="btn" href="<?= $escape($controlRoute(array_filter(['group'=>$control['group'] ?? '', 'status'=>$control['status'] ?? '', 'module_id'=>$control['requested_id'] ?? '', 'match_id'=>$this->workflowMatchId]))) ?>">Refresh status</a>
  </header>
  <div class="dc-notice"><p>Refresh reads local module evidence and selected retained workflow history. It does not synchronize providers, install software or submit model jobs. Optional modules can remain unavailable while the core workspace operates normally.</p></div>

  <?php if ($this->error): ?>
    <div class="dc-notice dc-warning" role="alert"><h3>Module status is unavailable</h3><p><?= $escape($this->error) ?></p><p>Readiness has not been verified by this page. Existing records and settings remain unchanged.</p></div>
    <a class="btn btn-outline-primary" href="<?= $escape($route('section=sources')) ?>">Open existing data sources</a>
  <?php else: ?>
    <?php $backendBuild = $control['backend_build'] ?? SystemModules::buildIdentity([]); ?>
    <section class="dc-notice" aria-labelledby="dc-build-title"><h3 id="dc-build-title">Associated backend build</h3><dl>
      <dt>API version</dt><dd><?= $escape($backendBuild['version'] ?? 'Not reported') ?></dd>
      <dt>Build kind</dt><dd><?= $escape($backendBuild['build_kind'] ?? 'Not reported') ?></dd>
      <dt>Source commit</dt><dd class="dc-code" data-backend-build="source_sha"><?= $escape($backendBuild['source_sha'] ?? 'Not reported') ?></dd>
      <dt>Source content SHA-256</dt><dd class="dc-code" data-backend-build="source_content_sha256"><?= $escape($backendBuild['source_content_sha256'] ?? 'Not reported') ?></dd>
    </dl><p class="dc-muted">Build identity describes the running backend payload. An unavailable commit or content hash is not inferred from the API version.</p></section>
    <div class="dc-stats" aria-label="Module registry overview">
      <div class="dc-stat"><strong data-module-total="<?= $escape($control['total']) ?>"><?= $escape($control['total']) ?></strong><span>Defined modules</span></div>
      <div class="dc-stat"><strong><?= $escape($control['core_ready']) ?> / <?= $escape($control['core_required']) ?></strong><span>Required modules ready</span></div>
      <div class="dc-stat"><strong><?= $escape($control['counts']['ready']) ?></strong><span>Ready with current evidence</span></div>
      <div class="dc-stat"><strong><?= $escape($control['counts']['degraded'] + $control['counts']['unavailable']) ?></strong><span>Degraded or unavailable</span></div>
      <div class="dc-stat"><strong><?= $escape($control['counts']['configured_unverified']) ?></strong><span>Configured, unverified</span></div>
    </div>
    <nav class="dc-groups" aria-label="Control Center module groups">
      <a href="<?= $escape($controlRoute()) ?>" <?= !$control['group'] ? 'aria-current="page"' : '' ?>>Overview</a>
      <?php foreach ($groups as $key => $label): ?><a href="<?= $escape($controlRoute(['group'=>$key])) ?>" <?= $control['group'] === $key ? 'aria-current="page"' : '' ?>><?= $escape($label) ?> <span>(<?= $escape($control['group_counts'][$key]) ?>)</span></a><?php endforeach; ?>
    </nav>
    <form class="dc-filters" method="get" action="index.php">
      <input type="hidden" name="option" value="com_dragonhydra"><input type="hidden" name="section" value="control">
      <div><label for="dc-group">Module group</label><select id="dc-group" name="group"><option value="">All groups</option><?php foreach ($groups as $key=>$label): ?><option value="<?= $escape($key) ?>" <?= $control['group'] === $key ? 'selected' : '' ?>><?= $escape($label) ?></option><?php endforeach; ?></select></div>
      <div><label for="dc-status">Runtime status</label><select id="dc-status" name="status"><option value="">All statuses</option><?php foreach ($states as $key=>$label): ?><option value="<?= $escape($key) ?>" <?= $control['status'] === $key ? 'selected' : '' ?>><?= $escape($label) ?></option><?php endforeach; ?></select></div>
      <button class="btn btn-primary" type="submit">Apply filters</button><a href="<?= $escape($controlRoute()) ?>">Clear filters</a>
    </form>
    <?php if (empty($control['modules'])): ?>
      <div class="dc-empty" role="status"><h3>No module definitions were reported</h3><p>The registry returned an empty snapshot. This page cannot establish module readiness from that response.</p></div>
    <?php elseif (empty($control['visible'])): ?>
      <div class="dc-empty" role="status"><h3>No modules match these filters</h3><p>Choose another group or runtime status, or clear the filters to see the full registry.</p></div>
    <?php else: ?>
      <div class="dc-table-wrap" tabindex="0" role="region" aria-label="Scrollable module status table">
        <table class="dc-table"><caption><?= $escape(count($control['visible'])) ?> of <?= $escape($control['total']) ?> modules. Runtime states describe this installation; implemented code alone does not establish readiness.</caption>
          <thead><tr><th scope="col">Module</th><th scope="col">Runtime status and reason</th><th scope="col">Evidence</th><th scope="col">Role</th></tr></thead>
          <tbody><?php foreach ($control['visible'] as $module): ?><tr>
            <th scope="row"><a href="<?= $escape($controlRoute(array_filter(['group'=>$control['group'],'status'=>$control['status'],'module_id'=>$module['id']]))) ?>#dc-detail"><?= $escape($module['name']) ?></a><small><?= $escape($groups[$module['category']]) ?></small><small class="dc-code"><?= $escape($module['id']) ?></small></th>
            <td><span class="dc-badge" data-tone="<?= $escape($tone($module['state'])) ?>"><?= $escape($states[$module['state']]) ?></span><p><?= $escape($module['reason'] ?: 'No supporting reason was reported.') ?></p></td>
            <td><time datetime="<?= $escape($module['observed_at'] ?? '') ?>"><?= $escape($stamp($module['observed_at'])) ?></time><small><?= $module['fresh'] ? 'Evidence current until ' : 'Evidence missing or expired · expiry ' ?><?= $escape($stamp($module['expires_at'])) ?></small></td>
            <td><?= $module['required_for_core'] ? 'Required for core' : 'Optional / supporting' ?><small>Implementation: <?= $escape(str_replace('_',' ',$module['implementation_state'])) ?></small><small>Configuration: <?= $escape(str_replace('_',' ',$module['configuration_state'])) ?></small></td>
          </tr><?php endforeach; ?></tbody>
        </table>
      </div>
    <?php endif; ?>

    <?php if (!empty($control['requested_id']) && !$selected): ?><div class="dc-notice dc-warning" role="status">The requested module is not present in this registry snapshot. Select a module from the table.</div><?php endif; ?>
    <?php if ($selected): $module = $selected; ?>
      <article class="dc-detail" id="dc-detail" aria-labelledby="dc-detail-title">
        <header class="dc-detail-head"><div><div class="dc-eyebrow dc-muted">Module details / <?= $escape($groups[$module['category']]) ?></div><h3 id="dc-detail-title"><?= $escape($module['name']) ?></h3></div><span class="dc-badge" data-tone="<?= $escape($tone($module['state'])) ?>"><?= $escape($states[$module['state']]) ?></span></header>
        <p><?= $escape($module['description']) ?></p><p><strong>Current reason:</strong> <?= $escape($module['reason'] ?: 'Not reported') ?></p>
        <div class="dc-grid"><section aria-labelledby="dc-observation"><h4 id="dc-observation">Installation observation</h4><dl>
          <dt>Module identifier</dt><dd class="dc-code"><?= $escape($module['id']) ?></dd>
          <dt>Implementation</dt><dd><?= $escape(str_replace('_',' ',$module['implementation_state'])) ?></dd>
          <dt>Version</dt><dd><?= $escape($module['version']) ?></dd>
          <dt>Configuration</dt><dd><?= $escape(str_replace('_',' ',$module['configuration_state'])) ?></dd>
          <dt>Observed</dt><dd><?= $escape($stamp($module['observed_at'])) ?></dd>
          <dt>Evidence expires</dt><dd><?= $escape($stamp($module['expires_at'])) ?></dd>
          <dt>Last success</dt><dd><?= $escape($stamp($module['last_success_at'])) ?></dd>
          <dt>Reason code</dt><dd class="dc-code"><?= $escape($module['reason_code'] ?: 'Not reported') ?></dd>
          <?php if ($module['state'] !== $module['reported_state']): ?><dt>Expired reported state</dt><dd><?= $escape($states[$module['reported_state']]) ?> — current readiness is unverified.</dd><?php endif; ?>
        </dl></section>
        <section aria-labelledby="dc-dependencies"><h4 id="dc-dependencies">Dependencies</h4>
          <?php if (!$module['dependencies']): ?><p class="dc-muted">No module dependencies were reported.</p><?php else: ?><ul class="dc-list"><?php foreach ($module['dependencies'] as $dependency): ?><li>
            <?php if (isset($control['modules'][$dependency['module_id']])): ?><a href="<?= $escape($controlRoute(['module_id'=>$dependency['module_id']])) ?>#dc-detail"><?= $escape($control['modules'][$dependency['module_id']]['name']) ?></a><?php else: ?><span class="dc-code"><?= $escape($dependency['module_id']) ?></span><?php endif; ?>
            <span class="dc-badge" data-tone="<?= $escape($tone($dependency['runtime_state'])) ?>"><?= $escape($states[$dependency['runtime_state']]) ?></span><p class="dc-muted"><?= $dependency['required'] ? 'Required dependency' : 'Optional dependency' ?> · reported runtime state</p>
          </li><?php endforeach; ?></ul><?php endif; ?>
        </section></div>
        <div class="dc-grid"><section><h4>Implemented capabilities</h4><?php if ($module['capabilities']): ?><ul><?php foreach ($module['capabilities'] as $capability): ?><li><?= $escape($capability) ?></li><?php endforeach; ?></ul><?php else: ?><p class="dc-muted">No implemented capabilities were declared.</p><?php endif; ?>
          <p><strong>Data domains:</strong> <?= $escape(implode(', ', $module['data_domains']) ?: 'Not reported') ?></p>
        </section><section><h4>Configuration requirements</h4><?php if ($module['requirements']): ?><ul class="dc-list"><?php foreach ($module['requirements'] as $requirement): ?><li><strong><?= $escape($requirement['reference']) ?></strong> <small><?= $requirement['required'] ? 'Required' : 'Optional' ?></small><p><?= $escape($requirement['description']) ?></p></li><?php endforeach; ?></ul><?php else: ?><p class="dc-muted">No configuration requirements were declared.</p><?php endif; ?><p class="dc-muted">Configuration values and credentials are not displayed here. Existing Joomla Options retain their permission checks.</p></section></div>
        <section><h4>Available operations</h4><?php if (!$module['operations']): ?><p class="dc-unavailable">No supported operations were reported for this module.</p><?php else: ?><ul class="dc-list"><?php foreach ($module['operations'] as $operation): ?><li>
          <?php if ($operation['available'] && $operation['read_only'] && isset($operationRoutes[$operation['operation_id']])): ?><a class="btn btn-outline-primary" href="<?= $escape($operationRoutes[$operation['operation_id']]) ?>"><?= $escape($operation['label']) ?></a>
          <?php else: ?><strong><?= $escape($operation['label']) ?></strong><p class="dc-unavailable"><?= $escape(!$operation['available'] && $operation['reason'] ? $operation['reason'] : 'This operation has no enabled execution control in Joomla. Use its existing supported product tooling; the registry does not execute it.') ?></p><?php endif; ?>
        </li><?php endforeach; ?></ul><?php endif; ?></section>
        <?php if ($module['metrics']): ?><section><h4>Sanitized retained metrics</h4><dl><?php foreach ($module['metrics'] as $key=>$value): ?><dt><?= $escape(ucfirst(str_replace('_',' ',$key))) ?></dt><dd><?= $escape($value) ?></dd><?php endforeach; ?></dl></section><?php endif; ?>
        <details><summary>Implementation and evidence references</summary><p class="dc-muted">References describe the declared implementation and retained verification scope. A build reference does not establish a running service or connected device.</p>
          <?php foreach (['implementation_refs'=>'Implementation','verification_refs'=>'Verification','evidence_refs'=>'Observation evidence'] as $field=>$label): ?><h4><?= $escape($label) ?></h4><?php if ($module[$field]): ?><ul><?php foreach ($module[$field] as $reference): ?><li class="dc-code"><?= $escape($reference) ?></li><?php endforeach; ?></ul><?php else: ?><p class="dc-muted">No references reported.</p><?php endif; ?><?php endforeach; ?>
        </details>
      </article>
    <?php endif; ?>
    <?php require __DIR__ . '/workflow.php'; ?>
    <details class="dc-guide"><summary>How to read module status</summary><p>Ready requires current runtime evidence for this installation. Configured, unverified means configuration or a build may exist, while successful operation is not established. Degraded and unavailable include the observed reason. Not implemented and not applicable are explicit states, including optional integrations.</p><p>Joomla does not maintain a second status database. Every refresh reads the associated server’s registry. Evidence dates use UTC.</p></details>
  <?php endif; ?>
</section>
