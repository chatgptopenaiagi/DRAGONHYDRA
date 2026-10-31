<?php
namespace Dragonhydra\Component\Dragonhydra\Administrator\Service;
defined('_JEXEC') or die;

use Joomla\CMS\Component\ComponentHelper;
use Joomla\CMS\Factory;

final class Kernel
{
    public static function client(): ApiClient
    {
        $user = Factory::getApplication()->getIdentity();
        if (!$user->authorise('core.manage', 'com_dragonhydra')) {
            throw new \RuntimeException('JERROR_ALERTNOAUTHOR', 403);
        }
        $params = ComponentHelper::getParams('com_dragonhydra');
        $path = (string) $params->get('bridge_secret_path', '');
        if (!$path || !is_file($path) || !is_readable($path) || filesize($path) > 4096) {
            throw new \RuntimeException('BRIDGE_NOT_CONFIGURED: Set a readable protected bridge-secret file in component options.');
        }
        $secret = trim((string) file_get_contents($path));
        if (str_starts_with($secret, '{')) {
            $record = json_decode($secret, true);
            $secret = is_array($record) && is_string($record['secret'] ?? null) ? $record['secret'] : '';
        }
        $roles = $user->authorise('dragonhydra.import', 'com_dragonhydra') ? 'admin' : 'reader';
        return new ApiClient((string) $params->get('api_base', 'http://127.0.0.1:8731/dragon/api/v1'), $secret, 'joomla:' . (int) $user->id, $roles);
    }
}
