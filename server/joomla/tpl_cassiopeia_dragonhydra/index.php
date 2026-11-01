<?php
defined('_JEXEC') or die;
use Joomla\CMS\Factory;
use Joomla\CMS\Uri\Uri;
$app = Factory::getApplication();
$wa = $this->getWebAssetManager();
$wa->getRegistry()->addTemplateRegistryFile('cassiopeia', 0);
$wa->usePreset('template.cassiopeia.' . ($this->direction === 'rtl' ? 'rtl' : 'ltr'));
$wa->registerStyle('template.active', '', [], [], ['template.cassiopeia.' . ($this->direction === 'rtl' ? 'rtl' : 'ltr')]);
$wa->addInlineStyle('body.dh-site{margin:0;background:#f2f5f8;font-family:system-ui,-apple-system,"Segoe UI",sans-serif;color:#102c3f}.dh-site>.dh-site-main{max-width:none;margin:0}.dh-site-brand{display:flex;align-items:center;justify-content:space-between;gap:1rem;padding:1.1rem clamp(1rem,4vw,3rem);background:#0d2738;color:#fff}.dh-site-brand a{color:#fff}.dh-site-brand strong{letter-spacing:.08em}.dh-site>.dh-site-main>.com-users-login,.dh-site>.dh-site-main>.com-users-logout,.dh-site>.dh-site-main>.com-users-profile,.dh-site>.dh-site-main>.com-users-reset,.dh-site>.dh-site-main>.com-users-remind{max-width:40rem;margin:2rem auto;padding:1.5rem;background:white;border-radius:.75rem}.dh-site a:focus-visible,.dh-site button:focus-visible,.dh-site input:focus-visible{outline:3px solid #bd6b00;outline-offset:3px}.dh-skip{position:fixed;left:1rem;top:-6rem;padding:.75rem;background:#fff;color:#102c3f;z-index:9999}.dh-skip:focus{top:1rem}');
$escape = static fn(string $value): string => htmlspecialchars($value, ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8');
$isWorkspace = $app->getInput()->getCmd('option') === 'com_dragonhydra';
?>
<!DOCTYPE html>
<html lang="<?= $escape($this->language) ?>" dir="<?= $escape($this->direction) ?>">
<head>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <jdoc:include type="metas" />
  <jdoc:include type="styles" />
  <jdoc:include type="scripts" />
</head>
<body class="dh-site">
  <a class="dh-skip" href="#dh-site-main">Skip to workspace</a>
  <?php if (!$isWorkspace): ?>
  <header class="dh-site-brand"><a href="<?= $escape(Uri::root(true) . '/') ?>"><strong>DRAGONHYDRA</strong></a><a href="<?= $escape(Uri::root(true) . '/administrator/') ?>">Administration</a></header>
  <?php endif; ?>
  <jdoc:include type="message" />
  <main id="dh-site-main" class="dh-site-main"><jdoc:include type="component" /></main>
</body>
</html>
