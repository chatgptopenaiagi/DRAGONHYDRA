<?php
defined('_JEXEC') or die;

use Joomla\CMS\Factory;
use Joomla\CMS\Version;

final class Com_DragonhydraInstallerScript
{
    public function preflight($type, $parent): bool
    {
        if ($type === 'uninstall') {
            return true;
        }
        if (version_compare(PHP_VERSION, '8.3.0', '<') || version_compare(Version::MAJOR_VERSION . '.0', '6.0', '<')) {
            Factory::getApplication()->enqueueMessage('DRAGONHYDRA requires Joomla 6 and PHP 8.3 or newer; the packaged stack targets PHP 8.4.', 'error');
            return false;
        }
        if (!extension_loaded('curl')) {
            Factory::getApplication()->enqueueMessage('DRAGONHYDRA administration requires PHP cURL.', 'error');
            return false;
        }
        return true;
    }

    public function uninstall($parent): bool
    {
        Factory::getApplication()->enqueueMessage('DRAGONHYDRA kernel databases, raw evidence, models and credentials have been retained.');
        return true;
    }

    public function postflight($type, $parent): bool
    {
        if (!in_array($type, ['install', 'update', 'discover_install'], true)) {
            return true;
        }
        require_once JPATH_ADMINISTRATOR . '/components/com_dragonhydra/src/Service/FrontendSetup.php';
        \Dragonhydra\Component\Dragonhydra\Administrator\Service\FrontendSetup::apply();
        return true;
    }
}
