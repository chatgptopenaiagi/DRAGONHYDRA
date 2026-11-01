<?php
namespace Dragonhydra\Component\Dragonhydra\Site\Service;
defined('_JEXEC') or die;

use Joomla\CMS\Component\ComponentHelper;
use Joomla\CMS\Factory;
use Dragonhydra\Component\Dragonhydra\Administrator\Service\ApiClient;

/** The site uses its own Joomla identity, never an administrator-session shortcut. */
final class Kernel
{
    public static function canRead(?object $user = null): bool
    {
        $user ??= Factory::getApplication()->getIdentity();
        return !(bool) $user->guest && (int) $user->id > 0
            && $user->authorise('core.manage', 'com_dragonhydra');
    }

    public static function client(): ApiClient
    {
        $user = Factory::getApplication()->getIdentity();
        if (!self::canRead($user)) {
            throw new \RuntimeException('JERROR_ALERTNOAUTHOR', 403);
        }
        // Both clients are installed by this component. Older Joomla namespace
        // caches can resolve Site before Administrator has been booted this request.
        if (!class_exists(ApiClient::class)) {
            require_once JPATH_ADMINISTRATOR . '/components/com_dragonhydra/src/Service/ApiClient.php';
        }
        $params = ComponentHelper::getParams('com_dragonhydra');
        $path = (string) $params->get('bridge_secret_path', '');
        if (!$path || !is_file($path) || !is_readable($path) || filesize($path) > 4096) {
            throw new \RuntimeException('BRIDGE_NOT_CONFIGURED');
        }
        $secret = trim((string) file_get_contents($path));
        if (str_starts_with($secret, '{')) {
            $record = json_decode($secret, true);
            $secret = is_array($record) && is_string($record['secret'] ?? null) ? $record['secret'] : '';
        }
        // Site reads/exports always retain the backend's owner-specific reader role.
        return new ApiClient((string) $params->get('api_base', ''), $secret, 'joomla:' . (int) $user->id, 'reader');
    }
}
