<?php
namespace Dragonhydra\Component\Dragonhydra\Site\View\Dashboard;
defined('_JEXEC') or die;

use Joomla\CMS\Factory;
use Joomla\CMS\MVC\View\HtmlView as BaseHtmlView;
use Dragonhydra\Component\Dragonhydra\Site\Service\Kernel;

final class HtmlView extends BaseHtmlView
{
    public array $workspace = [];

    public function display($tpl = null): void
    {
        $app = Factory::getApplication();
        $user = $app->getIdentity();
        $input = $app->input;
        $filters = [];
        foreach (['section', 'q', 'competition', 'team', 'team_id', 'match_id', 'job_id', 'status'] as $key) {
            $filters[$key] = $input->getString($key, '');
        }
        $filters['section'] = $filters['section'] ?: 'overview';
        $filters['limit'] = $input->getInt('limit', 25);
        $filters['offset'] = $input->getInt('offset', 0);
        $this->workspace = $this->getModel()->build($filters, Kernel::canRead($user));
        $this->workspace['permission_denied'] = !$user->guest && !Kernel::canRead($user);
        $this->workspace['user_name'] = $user->guest ? '' : (string) $user->username;
        $this->workspace['itemid'] = $input->getInt('Itemid', 0);
        $this->getDocument()->setTitle('DRAGONHYDRA · Sports intelligence');
        $assets = $this->getDocument()->getWebAssetManager();
        $assets->getRegistry()->addExtensionRegistryFile('com_dragonhydra');
        $assets->useStyle('com_dragonhydra.workspace');
        parent::display($tpl);
    }
}
