<?php
defined('_JEXEC') or die;
$center = $this->center;
$modules = $center['modules'] ?? [];
$selected = $center['module'] ?? null;
$installation = $center['installation'] ?? [];
$system = $center['system'] ?? [];
$stateClass = static fn($state): string => in_array($state, \Dragonhydra\Component\Dragonhydra\Administrator\Model\ControlCenterModel::STATES, true) ? strtolower($state) : 'unknown';
$label = static fn($key): string => ucfirst(str_replace('_', ' ', (string) $key));
$reason = static fn($text): string => preg_match('/^[A-Z0-9_]+$/D', (string) $text) ? ucfirst(strtolower(str_replace('_', ' ', (string) $text))) : (string) $text;
$value = static fn($v): string => is_bool($v) ? ($v ? 'Yes' : 'No') : (is_scalar($v) && $v !== '' ? (string) $v : 'Not reported');
$counts = array_count_values(array_map(static fn($m) => $m['state'], $modules));
$detailsUrl = static fn($id): string => $route('section=modules&module=' . rawurlencode((string) $id));
?>
<?php if ($this->section === 'overview'): ?>
  <section class="dhcn-introduction"><div><p class="dhcn-eyebrow">SYSTEM OVERVIEW</p><h2>One registry. A clear operating picture.</h2><p>Inspect the modules serving this installation, their retained evidence and the work they can currently support.</p></div><a class="btn btn-outline-primary" href="<?= $escape($route('section=modules')) ?>">Browse all modules</a></section>
  <div class="dhcn-summary" aria-label="Module state summary">
    <article><span>Registered modules</span><strong><?= count($modules) ?></strong><small>Definitions from this kernel</small></article>
    <article><span>Ready</span><strong><?= (int) ($counts['READY'] ?? 0) ?></strong><small>Within their reported proof scope</small></article>
    <article><span>Unavailable or limited</span><strong><?= (int) ($counts['DEGRADED'] ?? 0) + (int) ($counts['UNAVAILABLE'] ?? 0) + (int) ($counts['STOPPED'] ?? 0) + (int) ($counts['NOT_CONFIGURED'] ?? 0) + (int) ($counts['NOT_IMPLEMENTED'] ?? 0) + (int) ($counts['NOT_APPLICABLE'] ?? 0) ?></strong><small>Read each module’s reason</small></article>
    <article><span>Unknown or expired</span><strong><?= (int) ($counts['UNKNOWN'] ?? 0) + (int) ($counts['EXPIRED'] ?? 0) + (int) ($counts['UNVERIFIED'] ?? 0) ?></strong><small>Current readiness is unproven</small></article>
  </div>
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

<?php if ($selected): $state = $selected['state'] ?? 'UNKNOWN'; ?>
  <section class="dhcn-panel dhcn-module-detail" aria-labelledby="dhcn-module-title" data-module-id="<?= $escape($selected['id']) ?>">
    <div class="dhcn-module-heading"><div><p class="dhcn-eyebrow"><?= $escape($selected['category'] ?? 'MODULE DETAIL') ?></p><h2 id="dhcn-module-title"><?= $escape($selected['name'] ?? $selected['id']) ?></h2></div><span class="dhcn-state is-<?= $stateClass($state) ?>"><?= $escape($state) ?></span></div>
    <p class="dhcn-description"><?= $escape($selected['description'] ?? 'This module is defined by the associated kernel registry.') ?></p>
    <div class="dhcn-reason"><strong>Current assessment</strong><p><?= $escape($reason($selected['reason'] ?? 'No reason was supplied. Readiness must not be inferred from a module’s presence.')) ?></p></div>
    <dl class="dhcn-facts"><div><dt>Module version</dt><dd><?= $escape($value($selected['version'] ?? null)) ?></dd></div><div><dt>Origin</dt><dd><?= $escape($value($selected['origin'] ?? null)) ?></dd></div><div><dt>Last observation (UTC)</dt><dd><?= $escape($value($selected['observed_at'] ?? null)) ?></dd></div><div><dt>Expires (UTC)</dt><dd><?= $escape($value($selected['expires_at'] ?? null)) ?></dd></div></dl>
    <div class="dhcn-detail-grid"><div><h3>Capabilities</h3><ul><?php foreach (($selected['capabilities'] ?? []) as $capability): if (!is_scalar($capability)) { continue; } ?><li><?= $escape($capability) ?></li><?php endforeach; ?></ul><?php if (empty($selected['capabilities'])): ?><p class="dhcn-muted">No capabilities were reported.</p><?php endif; ?></div><div><h3>Dependencies</h3><?php if (empty($selected['dependencies'])): ?><p class="dhcn-muted">No module dependencies were reported.</p><?php else: ?><ul><?php foreach ($selected['dependencies'] as $dependency): if (!is_string($dependency)) { continue; } ?><li><?php if (isset($modules[$dependency])): ?><a href="<?= $escape($detailsUrl($dependency)) ?>"><?= $escape($modules[$dependency]['name'] ?? $dependency) ?></a> <span class="dhcn-state is-<?= $stateClass($modules[$dependency]['state']) ?>"><?= $escape($modules[$dependency]['state']) ?></span><?php else: ?><?= $escape($dependency) ?> · Not registered<?php endif; ?></li><?php endforeach; ?></ul><?php endif; ?></div></div>
    <h3>Retained observations</h3>
    <?php if (!empty($selected['capability_status'])): ?><div class="table-responsive"><table class="table"><caption>Capability availability is assessed separately from the module definition.</caption><thead><tr><th scope="col">Capability</th><th scope="col">Availability</th><th scope="col">Reason</th></tr></thead><tbody><?php foreach ($selected['capability_status'] as $capability): ?><tr><th scope="row"><?= $escape($label($capability['id'] ?? 'Capability')) ?></th><td><?= !empty($capability['available']) && $state === 'READY' ? 'Available within reported scope' : 'Not currently verified' ?></td><td><?= $escape($reason($capability['reason'] ?? $selected['reason'] ?? 'No current proof reported.')) ?></td></tr><?php endforeach; ?></tbody></table></div><?php endif; ?>
    <?php $metrics = (array) ($selected['observation']['metrics'] ?? []); ?>
    <dl class="dhcn-facts"><div><dt>Implementation</dt><dd><?= $escape($selected['implementation_state'] ?? 'UNVERIFIED') ?></dd></div><div><dt>Configuration</dt><dd><?= $escape($selected['configuration_state'] ?? 'UNVERIFIED') ?></dd></div><div><dt>Runtime operation</dt><dd><?= $escape($selected['runtime_state'] ?? 'UNVERIFIED') ?></dd></div></dl>
    <p class="dhcn-muted">BOUND means the implementation and its contract were constructed. It does not verify configuration or a runtime operation.</p>
    <p class="dhcn-muted">Counter evidence: <?= $escape($selected['observation']['metrics_state'] ?? 'UNVERIFIED') ?>. Sampled <?= $escape($value($selected['observation']['metrics_sampled_at'] ?? null)) ?>; expires <?= $escape($value($selected['observation']['metrics_expires_at'] ?? null)) ?>. An ordinary read does not renew these measurements.</p>
    <?php if ($metrics): ?><dl class="dhcn-metrics"><?php foreach ($metrics as $key=>$metric): if (!is_scalar($metric) && $metric !== null) { continue; } ?><div><dt><?= $escape($label($key)) ?></dt><dd><?= $escape($value($metric)) ?></dd></div><?php endforeach; ?></dl><?php else: ?><p class="dhcn-muted">No retained measurements were reported. This page does not create measurements.</p><?php endif; ?>
    <?php $evidence = $selected['observation']['evidence'] ?? []; if (is_string($evidence)) { $evidence = [$evidence]; } ?>
    <?php if ($evidence): ?><h3>Evidence scope</h3><ul class="dhcn-muted"><?php foreach ((array) $evidence as $entry): if (is_scalar($entry)): ?><li><?= $escape($entry) ?></li><?php endif; endforeach; ?></ul><?php endif; ?>
    <?php if (!empty($selected['configuration_requirements']) || !empty($selected['optional_dependency_status'])): ?><div class="dhcn-detail-grid"><div><h3>Configuration requirements</h3><ul><?php foreach (($selected['configuration_requirements'] ?? []) as $requirement): if (is_scalar($requirement)): ?><li><?= $escape($label($requirement)) ?></li><?php endif; endforeach; ?></ul></div><div><h3>Optional dependencies</h3><ul><?php foreach (($selected['optional_dependency_status'] ?? []) as $dependency): ?><li><?= $escape($dependency['id'] ?? 'Dependency') ?> · <?= $escape($dependency['state'] ?? 'UNKNOWN') ?><br><span class="dhcn-muted"><?= $escape($dependency['reason'] ?? 'No current proof reported.') ?></span></li><?php endforeach; ?></ul></div></div><?php endif; ?>
    <h3>Operations</h3><div class="table-responsive"><table class="table"><caption>Only implemented, explicitly authorized actions can change state. Module status is a retained read.</caption><thead><tr><th scope="col">Operation</th><th scope="col">Availability</th><th scope="col">Reason and next step</th></tr></thead><tbody>
    <?php foreach (($selected['operations'] ?? []) as $operation): $readOnly = ($operation['enabled'] ?? false) && ($operation['method'] ?? 'GET') === 'GET'; ?><tr><th scope="row"><?= $escape($operation['label'] ?? $operation['id'] ?? 'Operation') ?></th><td><?= $readOnly ? 'Read only' : 'Disabled here' ?></td><td><?= $escape($operation['reason'] ?? ($readOnly ? 'Available through this module’s retained status.' : 'No supported Control Center action is registered.')) ?></td></tr><?php endforeach; ?>
    <?php if (empty($selected['operations'])): ?><tr><td colspan="3">No operations were reported for this module.</td></tr><?php endif; ?>
    </tbody></table></div>
    <?php if ($selected['id'] === 'data'): ?><a class="btn btn-outline-primary" href="<?= $escape($route('section=sources')) ?>">Open existing Data sources actions</a><?php endif; ?>
    <a class="btn btn-outline-secondary" href="<?= $escape($route('section=modules')) ?>">All modules</a>
    <?php if (!empty($selected['verification_references']) || !empty($selected['implementation_reference'])): ?><details class="mt-4"><summary>Implementation and verification references</summary><p class="dhcn-muted"><?= $escape($selected['implementation_reference'] ?? 'Not reported') ?></p><ul class="dhcn-muted"><?php foreach (($selected['verification_references'] ?? []) as $reference): if (is_scalar($reference)): ?><li><?= $escape($reference) ?></li><?php endif; endforeach; ?></ul></details><?php endif; ?>
  </section>
<?php elseif (in_array($this->section, ['odds','prediction','ai','memory','evaluation'], true)): ?>
  <section class="dhcn-panel"><h2>Module not reported</h2><p>The registry has no verifiable module detail for this selection. No capability is assumed ready.</p></section>
<?php endif; ?>

<?php if (in_array($this->section, ['overview','modules'], true) && !$selected): ?>
  <section aria-labelledby="dhcn-directory-title"><div class="dhcn-section-heading"><div><p class="dhcn-eyebrow">MODULE REGISTRY</p><h2 id="dhcn-directory-title">Available building blocks</h2></div><span class="dhcn-muted">State and scope from the associated kernel</span></div>
    <div class="dhcn-module-grid"><?php foreach ($modules as $module): ?><article class="dhcn-module-card" data-module-id="<?= $escape($module['id']) ?>"><div class="dhcn-module-heading"><span class="dhcn-eyebrow"><?= $escape($module['category'] ?? 'MODULE') ?></span><span class="dhcn-state is-<?= $stateClass($module['state']) ?>"><?= $escape($module['state']) ?></span></div><h3><a href="<?= $escape($detailsUrl($module['id'])) ?>"><?= $escape($module['name'] ?? $module['id']) ?></a></h3><p><?= $escape($module['description'] ?? '') ?></p><p class="dhcn-card-reason"><?= $escape($reason($module['reason'] ?? 'No assessment reason reported.')) ?></p><div class="dhcn-card-footer"><span>v<?= $escape($module['version'] ?? '?') ?></span><a href="<?= $escape($detailsUrl($module['id'])) ?>">Details <span aria-hidden="true">→</span></a></div></article><?php endforeach; ?></div>
    <?php if (!$modules): ?><div class="dhcn-panel"><p>No module definitions were returned. An empty registry does not establish readiness.</p></div><?php endif; ?>
  </section>
<?php endif; ?>
<p class="dhcn-footnote">Observations retain their reported timestamps. Refreshing this page reads existing status; it never starts an acquisition, calculation, model, installation or service.</p>
