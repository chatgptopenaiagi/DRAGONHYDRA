<?php
defined('_JEXEC') or die;
$center = $this->center;
$modules = $center['modules'] ?? [];
$visibleModules = $center['visible_modules'] ?? $modules;
$inventory = $center['inventory'] ?? ['engines'=>0,'supporting'=>0,'total'=>count($modules),'unclassified'=>count($modules)];
$selected = $center['module'] ?? null;
$installation = $center['installation'] ?? [];
$system = $center['system'] ?? [];
$stateClass = static fn($state): string => in_array($state, \Dragonhydra\Component\Dragonhydra\Administrator\Model\ControlCenterModel::STATES, true) ? strtolower($state) : 'unknown';
$stateTone = static fn($state): string => \Dragonhydra\Component\Dragonhydra\Administrator\Model\ControlCenterModel::tone((string)$state);
$stateLabel = static fn($state): string => \Dragonhydra\Component\Dragonhydra\Administrator\Model\ControlCenterModel::stateLabel((string)$state);
$age = static fn($seconds): string => is_int($seconds) ? ($seconds < 60 ? $seconds . ' seconds' : ($seconds < 3600 ? (int)floor($seconds/60) . ' minutes' : (int)floor($seconds/3600) . ' hours')) : 'Not reported';
$label = static fn($key): string => ucfirst(str_replace('_', ' ', (string) $key));
$reason = static fn($text): string => preg_match('/^[A-Z0-9_]+$/D', (string) $text) ? ucfirst(strtolower(str_replace('_', ' ', (string) $text))) : (string) $text;
$value = static fn($v): string => is_bool($v) ? ($v ? 'Yes' : 'No') : (is_scalar($v) && $v !== '' ? (string) $v : 'Not reported');
$counts = array_count_values(array_map(static fn($m) => $m['state'], $modules));
$activeFilters = array_filter(array_intersect_key((array)($center['filters'] ?? []), array_flip(['layer','category','status'])), static fn($entry): bool => is_string($entry) && $entry !== '');
$detailsUrl = static fn($id): string => $route(http_build_query(['section'=>'modules','module'=>(string)$id] + $activeFilters, '', '&', PHP_QUERY_RFC3986));
?>
<?php if ($this->section === 'overview'): ?>
  <section class="dhcn-introduction"><div><p class="dhcn-eyebrow">SYSTEM OVERVIEW</p><h2>One registry. A clear operating picture.</h2><p>Inspect the modules serving this installation, their retained evidence and the work they can currently support.</p></div><a class="btn btn-outline-primary" href="<?= $escape($route('section=modules')) ?>">Browse all modules</a></section>
  <div class="dhcn-summary" aria-label="Module state summary">
    <article><span>Engines</span><strong data-inventory="engines"><?= (int)$inventory['engines'] ?></strong><small>Distinct existing engine responsibilities</small></article>
    <article><span>Supporting modules</span><strong data-inventory="supporting"><?= (int)$inventory['supporting'] ?></strong><small>Infrastructure, clients and recovery</small></article>
    <article><span>Total registry entries</span><strong data-inventory="total"><?= (int)$inventory['total'] ?></strong><small>One registry; no duplicated engines</small></article>
    <article><span>Ready within scope</span><strong><?= (int) ($counts['READY'] ?? 0) ?></strong><small>Engine and supporting observations</small></article>
  </div>
  <?php if (!empty($inventory['unclassified'])): ?><p class="dhcn-muted"><?= (int)$inventory['unclassified'] ?> entries have no verified layer classification. Their presence is not counted as an engine.</p><?php endif; ?>
  <p class="dhcn-state-legend"><span class="dhcn-state" data-tone="green">Ready</span> Current scoped proof <span class="dhcn-state" data-tone="amber">Degraded</span> Limited capability <span class="dhcn-state" data-tone="red">Unavailable / stopped</span> Observed failure or absence <span class="dhcn-state" data-tone="neutral">Not configured / unverified / expired / unknown / not applicable</span> No current readiness proof</p>
<?php endif; ?>

<?php if (in_array($this->section, ['overview','infrastructure'], true)): ?>
  <section class="dhcn-panel" aria-labelledby="dhcn-infrastructure-title"><p class="dhcn-eyebrow">INFRASTRUCTURE</p><h2 id="dhcn-infrastructure-title">This installation’s backend</h2>
    <dl class="dhcn-facts">
      <div><dt>API state</dt><dd><?= $escape($value($system['status'] ?? null)) ?></dd></div>
      <div><dt>Sports storage</dt><dd><?= $escape($value($system['backend'] ?? null)) ?></dd></div>
      <div><dt>Kernel version</dt><dd><?= $escape($value($installation['version'] ?? $system['version'] ?? null)) ?></dd></div>
      <div><dt>Environment</dt><dd><?= $escape($value($installation['environment_id'] ?? null)) ?></dd></div>
    </dl>
    <p class="dhcn-muted">Joomla owns accounts and presentation. The associated Python kernel owns sports records, calculations, module observations and durable jobs.</p>
    <div class="dhcn-limit"><strong>Infrastructure changes are disabled here.</strong><p>Service restart, installation, database cutover and restoration require the installation’s scoped management tooling. Opening this page performs no probe, import, inference or restart.</p></div>
  </section>
<?php endif; ?>

<?php if (in_array($this->section, ['overview','infrastructure'], true) || ($selected['id'] ?? '') === 'runtime_supervisor'):
    $serviceModule = ($selected['id'] ?? '') === 'runtime_supervisor' ? $selected : ($modules['runtime_supervisor'] ?? []);
    $serviceIdentity = $serviceModule['service_identity'] ?? null; ?>
  <section class="dhcn-panel" aria-labelledby="dhcn-service-identity-title">
    <h2 id="dhcn-service-identity-title">Bound Windows service identity</h2>
    <?php if ($serviceIdentity): ?>
      <dl class="dhcn-facts" data-service-identity>
        <div><dt>Running service</dt><dd><code><?= $escape($serviceIdentity['service_name']) ?></code></dd></div>
        <div><dt>Installation</dt><dd><code><?= $escape($serviceIdentity['installation_id']) ?></code></dd></div>
        <div><dt>Source commit</dt><dd><code><?= $escape($serviceIdentity['source_commit']) ?></code></dd></div>
        <div><dt>Build identity</dt><dd><?= $escape($serviceIdentity['build_id']) ?></dd></div>
        <div><dt>Observed (UTC)</dt><dd><?= $escape($serviceIdentity['observed_at']) ?></dd></div>
        <div><dt>Evidence expires (UTC)</dt><dd><?= $escape($serviceIdentity['evidence_expires_at']) ?></dd></div>
      </dl>
      <p class="dhcn-muted">Verification scope: <?= $escape($serviceIdentity['verification_scope']) ?>.</p>
      <p class="dhcn-muted">This limited evidence identifies the running service and its supervisor parent. It does not report a service account, its privileges or interactive application acceptance.</p>
    <?php else: ?>
      <p class="dhcn-muted" data-service-identity-unverified>No current bound service identity was supplied. A configured service name or runtime-owner label does not establish service ownership.</p>
    <?php endif; ?>
  </section>
<?php endif; ?>

<?php if ($selected): $state = $selected['state'] ?? 'UNKNOWN'; ?>
  <section class="dhcn-panel dhcn-module-detail" aria-labelledby="dhcn-module-title" data-module-id="<?= $escape($selected['id']) ?>">
    <div class="dhcn-module-heading"><div><p class="dhcn-eyebrow"><?= $escape($selected['category'] ?? 'MODULE DETAIL') ?></p><h2 id="dhcn-module-title"><?= $escape($selected['name'] ?? $selected['id']) ?></h2></div><span class="dhcn-state is-<?= $stateClass($state) ?>" data-state="<?= $escape($state) ?>" data-tone="<?= $stateTone($state) ?>"><?= $escape($stateLabel($state)) ?></span></div>
    <p class="dhcn-description"><?= $escape($selected['description'] ?? 'This module is defined by the associated kernel registry.') ?></p>
    <div class="dhcn-reason"><strong>Current assessment</strong><p><?= $escape($reason($selected['reason'] ?? 'No reason was supplied. Readiness must not be inferred from a module’s presence.')) ?></p></div>
    <dl class="dhcn-facts"><div><dt>Module version / build</dt><dd><?= $escape($value($selected['actual_version_or_build'] ?? $selected['version'] ?? null)) ?></dd></div><div><dt>Layer</dt><dd><?= $escape($label($selected['layer'] ?? 'Unclassified')) ?></dd></div><div><dt>Origin</dt><dd><?= $escape($value($selected['origin'] ?? null)) ?></dd></div><div><dt>Observation age</dt><dd><?= $escape($age($selected['evidence_age_seconds'] ?? null)) ?></dd></div><div><dt>Last observation (UTC)</dt><dd><?= $escape($value($selected['observed_at'] ?? null)) ?></dd></div><div><dt>Expires (UTC)</dt><dd><?= $escape($value($selected['expires_at'] ?? null)) ?></dd></div><div><dt>Last success (UTC)</dt><dd><?= $escape($value($selected['last_success_at'] ?? $selected['observation']['last_success'] ?? null)) ?></dd></div><div><dt>Reason code</dt><dd><?= $escape($value($selected['reason_code'] ?? null)) ?></dd></div></dl>
    <dl class="dhcn-facts"><div><dt>Runtime owner</dt><dd><?= $escape($value($selected['runtime_owner'] ?? null)) ?></dd></div><div><dt>Observer</dt><dd><?= $escape($value($selected['observation']['observer_identity'] ?? $selected['observer_identity'] ?? null)) ?></dd></div><div><dt>Observation ID</dt><dd><?= $escape($value($selected['observation']['observation_id'] ?? $selected['observation_id'] ?? null)) ?></dd></div><div><dt>Observed build identity</dt><dd><?= $escape($value($selected['observation']['build_identity'] ?? $selected['build_identity'] ?? null)) ?></dd></div></dl>
    <?php $scope=(array)($selected['observation']['verification_scope'] ?? $selected['verification_scope'] ?? []); ?>
    <h3>Verification scope</h3><?php if($scope): ?><ul><?php foreach($scope as $entry): if(is_scalar($entry)): ?><li><?= $escape($entry) ?></li><?php endif; endforeach; ?></ul><?php else: ?><p class="dhcn-muted">No verification scope was reported. Readiness must remain limited to its stated evidence.</p><?php endif; ?>
    <h3>Data domains</h3><?php if(!empty($selected['data_domains'])): ?><ul><?php foreach($selected['data_domains'] as $domain): if(is_scalar($domain)): ?><li><?= $escape($domain) ?></li><?php endif; endforeach; ?></ul><?php else: ?><p class="dhcn-muted">No data domains were declared.</p><?php endif; ?>
    <div class="dhcn-detail-grid"><div><h3>Capabilities</h3><ul><?php foreach (($selected['capabilities'] ?? []) as $capability): if (!is_scalar($capability)) { continue; } ?><li><?= $escape($capability) ?></li><?php endforeach; ?></ul><?php if (empty($selected['capabilities'])): ?><p class="dhcn-muted">No capabilities were reported.</p><?php endif; ?></div><div><h3>Dependencies</h3><?php if (empty($selected['dependencies'])): ?><p class="dhcn-muted">No module dependencies were reported.</p><?php else: ?><ul><?php foreach ($selected['dependencies'] as $dependency): if (!is_string($dependency)) { continue; } ?><li><?php if (isset($modules[$dependency])): ?><a href="<?= $escape($detailsUrl($dependency)) ?>"><?= $escape($modules[$dependency]['name'] ?? $dependency) ?></a> <span class="dhcn-state is-<?= $stateClass($modules[$dependency]['state']) ?>" data-state="<?= $escape($modules[$dependency]['state']) ?>" data-tone="<?= $stateTone($modules[$dependency]['state']) ?>"><?= $escape($stateLabel($modules[$dependency]['state'])) ?></span><?php else: ?><?= $escape($dependency) ?> · Not registered<?php endif; ?></li><?php endforeach; ?></ul><?php endif; ?></div></div>
    <h3>Retained observations</h3>
    <?php if (!empty($selected['capability_status'])): ?><div class="table-responsive"><table class="table"><caption>Capability availability is assessed separately from the module definition.</caption><thead><tr><th scope="col">Capability</th><th scope="col">Availability</th><th scope="col">Reason</th></tr></thead><tbody><?php foreach ($selected['capability_status'] as $capability): ?><tr><th scope="row"><?= $escape($label($capability['id'] ?? 'Capability')) ?></th><td><?= ($capability['available'] ?? false) === true ? 'Available for named verified operations' : 'Not currently verified' ?></td><td><?= $escape($reason($capability['reason'] ?? $selected['reason'] ?? 'No current proof reported.')) ?></td></tr><?php endforeach; ?></tbody></table></div><?php endif; ?>
    <?php foreach(($selected['capability_status'] ?? []) as $capability): ?>
    <details class="dhcn-operation-proof"><summary><?= $escape($label($capability['id'] ?? 'Capability')) ?> — operation evidence</summary>
      <p class="dhcn-muted">Availability applies only to named operations with current proof. It does not verify every operation or an optional model.</p>
      <p><strong>Verified operations:</strong> <?= $escape(implode(', ',array_filter((array)($capability['verified_operations'] ?? []),'is_string')) ?: 'None reported') ?></p>
      <?php foreach(($capability['operation_status'] ?? []) as $proof): if(!is_array($proof)){continue;} ?>
        <h4><?= $escape($label($proof['id'] ?? 'Operation')) ?> <span class="dhcn-state" data-tone="<?= $stateTone($proof['state'] ?? 'UNKNOWN') ?>"><?= $escape($stateLabel($proof['state'] ?? 'UNKNOWN')) ?></span></h4>
        <dl class="dhcn-facts"><div><dt>Observed (UTC)</dt><dd><?= $escape($value($proof['observed_at'] ?? null)) ?></dd></div><div><dt>Expires (UTC)</dt><dd><?= $escape($value($proof['expires_at'] ?? null)) ?></dd></div><div><dt>Observation ID</dt><dd><?= $escape($value($proof['observation_id'] ?? null)) ?></dd></div><div><dt>Reason</dt><dd><?= $escape($reason($proof['reason'] ?? 'No operation evidence reported.')) ?></dd></div></dl>
        <p><strong>Verification scope:</strong> <?= $escape(implode('; ',array_filter((array)($proof['verification_scope'] ?? []),'is_string')) ?: 'Not reported') ?></p>
      <?php endforeach; ?>
    </details>
    <?php endforeach; ?>
    <?php $metrics = (array) ($selected['observation']['metrics'] ?? []); ?>
    <dl class="dhcn-facts"><div><dt>Implementation</dt><dd><?= $escape($selected['implementation_state'] ?? 'UNVERIFIED') ?></dd></div><div><dt>Configuration</dt><dd><?= $escape($selected['configuration_state'] ?? 'UNVERIFIED') ?></dd></div><div><dt>Runtime operation</dt><dd><?= $escape($selected['runtime_state'] ?? 'UNVERIFIED') ?></dd></div></dl>
    <p class="dhcn-muted">BOUND means the implementation and its contract were constructed. It does not verify configuration or a runtime operation.</p>
    <p class="dhcn-muted">Counter evidence: <?= $escape($selected['observation']['metrics_state'] ?? 'UNVERIFIED') ?>. Sampled <?= $escape($value($selected['observation']['metrics_sampled_at'] ?? null)) ?>; expires <?= $escape($value($selected['observation']['metrics_expires_at'] ?? null)) ?>. An ordinary read does not renew these measurements.</p>
    <?php if ($metrics): ?><dl class="dhcn-metrics"><?php foreach ($metrics as $key=>$metric): if (!is_scalar($metric) && $metric !== null) { continue; } ?><div><dt><?= $escape($label($key)) ?></dt><dd><?= $escape($value($metric)) ?></dd></div><?php endforeach; ?></dl><?php else: ?><p class="dhcn-muted">No retained measurements were reported. This page does not create measurements.</p><?php endif; ?>
    <?php $evidence = $selected['observation']['evidence'] ?? []; if (is_string($evidence)) { $evidence = [$evidence]; } ?>
    <?php if ($evidence): ?><h3>Evidence scope</h3><ul class="dhcn-muted"><?php foreach ((array) $evidence as $entry): if (is_scalar($entry)): ?><li><?= $escape($entry) ?></li><?php endif; endforeach; ?></ul><?php endif; ?>
    <?php if (!empty($selected['configuration_requirements']) || !empty($selected['optional_dependency_status'])): ?><div class="dhcn-detail-grid"><div><h3>Configuration requirements</h3><ul><?php foreach (($selected['configuration_requirements'] ?? []) as $requirement): if (is_scalar($requirement)): ?><li><?= $escape($label($requirement)) ?></li><?php endif; endforeach; ?></ul></div><div><h3>Optional dependencies</h3><ul><?php foreach (($selected['optional_dependency_status'] ?? []) as $dependency): ?><li><?= $escape($dependency['id'] ?? 'Dependency') ?> · <?= $escape($dependency['state'] ?? 'UNKNOWN') ?><br><span class="dhcn-muted"><?= $escape($dependency['reason'] ?? 'No current proof reported.') ?></span></li><?php endforeach; ?></ul></div></div><?php endif; ?>
    <h3>Operations</h3><div class="table-responsive"><table class="table"><caption>Only implemented, explicitly authorized actions can change state. Module status is a retained read.</caption><thead><tr><th scope="col">Operation</th><th scope="col">Availability</th><th scope="col">Reason and next step</th></tr></thead><tbody>
    <?php foreach (($selected['operations'] ?? []) as $operation): if (!is_array($operation)) { continue; } $readView = \Dragonhydra\Component\Dragonhydra\Administrator\Model\ControlCenterModel::operationReadView($operation, (string)$selected['id']); ?><tr><th scope="row"><?= $escape($operation['label'] ?? $operation['id'] ?? 'Operation') ?></th><td><?php if ($readView['query'] !== null): ?><a class="btn btn-outline-primary" data-operation-read-view="<?= $escape($operation['id']) ?>" href="<?= $escape($route($readView['query'])) ?>"><?= $escape($readView['label']) ?></a><?php else: ?>Disabled here<?php endif; ?></td><td><?= $escape($readView['reason']) ?></td></tr><?php endforeach; ?>
    <?php if (empty($selected['operations'])): ?><tr><td colspan="3">No operations were reported for this module.</td></tr><?php endif; ?>
    </tbody></table></div>
    <?php if ($selected['id'] === 'data'): ?><a class="btn btn-outline-primary" href="<?= $escape($route('section=sources')) ?>">Open existing Data sources actions</a><?php endif; ?>
    <a class="btn btn-outline-secondary" href="<?= $escape($route(http_build_query(['section'=>'modules'] + $activeFilters, '', '&', PHP_QUERY_RFC3986))) ?>">All modules</a>
    <?php if (!empty($selected['verification_references']) || !empty($selected['implementation_reference'])): ?><details class="mt-4"><summary>Implementation and verification references</summary><p class="dhcn-muted"><?= $escape($selected['implementation_reference'] ?? 'Not reported') ?></p><ul class="dhcn-muted"><?php foreach (($selected['verification_references'] ?? []) as $reference): if (is_scalar($reference)): ?><li><?= $escape($reference) ?></li><?php endif; endforeach; ?></ul></details><?php endif; ?>
  </section>
<?php elseif (in_array($this->section, ['odds','prediction','ai','memory','evaluation'], true)): ?>
  <section class="dhcn-panel"><h2>Module not reported</h2><p>The registry has no verifiable module detail for this selection. No capability is assumed ready.</p></section>
<?php endif; ?>

<?php if (in_array($this->section, ['overview','modules'], true) && !$selected): ?>
  <section aria-labelledby="dhcn-directory-title"><div class="dhcn-section-heading"><div><p class="dhcn-eyebrow">MODULE REGISTRY</p><h2 id="dhcn-directory-title">Available building blocks</h2></div><span class="dhcn-muted">State and scope from the associated kernel</span></div>
    <form class="dhcn-filter" action="index.php" method="get">
      <input type="hidden" name="option" value="com_dragonhydra"><input type="hidden" name="section" value="<?= $escape($this->section) ?>">
      <div><label for="dhcn-layer">Registry layer</label><select id="dhcn-layer" name="layer"><option value="">All layers</option><?php foreach(['engine'=>'Engines','supporting'=>'Supporting modules'] as $key=>$text): ?><option value="<?= $key ?>" <?= ($center['filters']['layer'] ?? '') === $key ? 'selected' : '' ?>><?= $text ?></option><?php endforeach; ?></select></div>
      <div><label for="dhcn-category">Category</label><select id="dhcn-category" name="category"><option value="">All categories</option><?php foreach(($center['categories'] ?? []) as $category): ?><option value="<?= $escape($category) ?>" <?= ($center['filters']['category'] ?? '') === $category ? 'selected' : '' ?>><?= $escape($category) ?></option><?php endforeach; ?></select></div>
      <div><label for="dhcn-status">Runtime status</label><select id="dhcn-status" name="status"><option value="">All statuses</option><?php foreach(\Dragonhydra\Component\Dragonhydra\Administrator\Model\ControlCenterModel::STATES as $status): ?><option value="<?= $escape($status) ?>" <?= ($center['filters']['status'] ?? '') === $status ? 'selected' : '' ?>><?= $escape($stateLabel($status)) ?></option><?php endforeach; ?></select></div>
      <button class="btn btn-outline-primary" type="submit">Apply display filters</button><a href="<?= $escape($route('section=' . $this->section)) ?>">Clear filters</a>
    </form>
    <div class="dhcn-module-grid"><?php foreach ($visibleModules as $module): ?><article class="dhcn-module-card" data-module-id="<?= $escape($module['id']) ?>" data-module-layer="<?= $escape($module['layer'] ?? 'unclassified') ?>"><div class="dhcn-module-heading"><span class="dhcn-eyebrow"><?= $escape($label($module['layer'] ?? 'unclassified')) ?> / <?= $escape($module['category'] ?? 'MODULE') ?></span><span class="dhcn-state is-<?= $stateClass($module['state']) ?>" data-state="<?= $escape($module['state']) ?>" data-tone="<?= $stateTone($module['state']) ?>"><?= $escape($stateLabel($module['state'])) ?></span></div><h3><a href="<?= $escape($detailsUrl($module['id'])) ?>"><?= $escape($module['name'] ?? $module['id']) ?></a></h3><p><?= $escape($module['description'] ?? '') ?></p><p class="dhcn-card-reason"><?= $escape($reason($module['reason'] ?? 'No assessment reason reported.')) ?></p><p class="dhcn-muted">Evidence age: <?= $escape($age($module['evidence_age_seconds'] ?? null)) ?></p><div class="dhcn-card-footer"><span>v<?= $escape($module['version'] ?? '?') ?></span><a href="<?= $escape($detailsUrl($module['id'])) ?>">Details <span aria-hidden="true">→</span></a></div></article><?php endforeach; ?></div>
    <?php if ($modules && !$visibleModules): ?><div class="dhcn-panel"><p>No modules match these display filters. Clear the filters to read the complete registry.</p></div><?php endif; ?>
    <?php if (!$modules): ?><div class="dhcn-panel"><p>No module definitions were returned. An empty registry does not establish readiness.</p></div><?php endif; ?>
  </section>
<?php endif; ?>
<?php if (in_array($this->section,['prediction','memory','evaluation'],true) || !empty($center['workflow']) || !empty($center['workflow_error'])) { require __DIR__ . '/workflow.php'; } ?>
<p class="dhcn-footnote">Observations retain their reported timestamps. Refreshing this page reads existing status; it never starts an acquisition, calculation, model, installation or service.</p>
