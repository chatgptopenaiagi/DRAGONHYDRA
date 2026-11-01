<?php
namespace Dragonhydra\Component\Dragonhydra\Administrator\View\Dashboard;
defined('_JEXEC') or die;

use Joomla\CMS\Component\ComponentHelper;
use Joomla\CMS\Factory;
use Joomla\CMS\Language\Text;
use Joomla\CMS\MVC\View\HtmlView as BaseHtmlView;
use Joomla\CMS\Toolbar\ToolbarHelper;
use Dragonhydra\Component\Dragonhydra\Administrator\Service\Kernel;
use Dragonhydra\Component\Dragonhydra\Administrator\Service\SystemModules;
use Dragonhydra\Component\Dragonhydra\Administrator\Service\SystemWorkflow;

final class HtmlView extends BaseHtmlView
{
    public string $section = 'sources';
    public array $data = [];
    public ?string $error = null;
    public bool $canImport = false;
    public array $probe = [];
    public string $dashboardUrl = '';
    public string $jobId = '';
    public array $control = [];
    public array $workflow = [];
    public ?string $workflowError = null;
    public string $workflowMatchId = '';
    public array $workflowKeys = [];

    public function display($tpl = null): void
    {
        $app = Factory::getApplication();
        $user = $app->getIdentity();
        if (!$user->authorise('core.manage', 'com_dragonhydra')) {
            throw new \RuntimeException('JERROR_ALERTNOAUTHOR', 403);
        }
        ToolbarHelper::title(Text::_('COM_DRAGONHYDRA'), 'chart-line');
        if ($user->authorise('core.options', 'com_dragonhydra')) {
            ToolbarHelper::preferences('com_dragonhydra');
        }
        $section = $app->input->getCmd('section', 'sources');
        $this->section = in_array($section, ['control','sources','matches','odds','models','research','databases','system','jobs'], true) ? $section : 'sources';
        $this->canImport = $user->authorise('dragonhydra.import', 'com_dragonhydra');
        $this->probe = (array) $app->getUserState('com_dragonhydra.last_probe', []);
        $url = (string) ComponentHelper::getParams('com_dragonhydra')->get('dashboard_url', 'http://127.0.0.1:8731/');
        $parts = parse_url($url);
        if ($parts && in_array($parts['scheme'] ?? '', ['http', 'https'], true) && !isset($parts['user']) && !isset($parts['pass'])) {
            $this->dashboardUrl = $url;
        }
        try {
            $api = Kernel::client();
            if ($this->section === 'control') {
                $this->control = SystemModules::load(
                    fn(string $path): array => $api->request('GET', $path),
                    $app->input->getCmd('group', ''),
                    $app->input->getCmd('status', ''),
                    $app->input->getCmd('module_id', '')
                );
                try {
                    $this->control['backend_build'] = SystemModules::buildIdentity($api->request('GET', '/system'));
                } catch (\RuntimeException $error) {
                    $this->control['backend_build'] = SystemModules::buildIdentity([]);
                }
                $this->workflowMatchId = $app->input->getString('match_id', '');
                if ($this->workflowMatchId !== '') {
                    try {
                        $this->workflow = SystemWorkflow::load(fn(string $path): array => $api->request('GET', $path), $this->workflowMatchId);
                        if ($this->canImport) {
                            foreach (['forecasts','evaluations'] as $operation) {
                                $this->workflowKeys[$operation] = SystemWorkflow::formKey($app, $this->workflowMatchId, $operation);
                            }
                        }
                    } catch (\RuntimeException $error) {
                        $this->workflowError = 'Retained workflow history is not available for this match. Choose an existing supported retained match or retry when the backend is available.';
                    }
                }
            } elseif ($this->section === 'sources') {
                $this->data = $api->request('GET', '/connections');
            } elseif ($this->section === 'matches') {
                $id = $app->input->getCmd('match_id', '');
                $offset = max(0, $app->input->getInt('offset', 0));
                $this->data = $id ? ['match' => $api->request('GET', '/matches/' . rawurlencode($id))]
                    : $api->request('GET', '/matches?limit=50&offset=' . $offset);
            } elseif ($this->section === 'jobs') {
                $this->jobId = $app->input->getCmd('job_id', '');
                if (!$this->jobId) {
                    throw new \RuntimeException('Choose an import from Data sources to open its job.');
                }
                $this->data = $api->request('GET', '/jobs/' . rawurlencode($this->jobId));
            } else {
                $this->data = $api->request('GET', '/system');
            }
        } catch (\RuntimeException $error) {
            $this->error = $this->section === 'control'
                ? 'The module registry could not be read through this installation\'s protected bridge. Retry or review the connection in Options. No module state was changed.'
                : $error->getMessage();
        }
        if ($this->section === 'control') {
            $assets = $this->getDocument()->getWebAssetManager();
            $assets->getRegistry()->addExtensionRegistryFile('com_dragonhydra');
            $assets->useStyle('com_dragonhydra.control');
        }
        parent::display($tpl);
    }
}
