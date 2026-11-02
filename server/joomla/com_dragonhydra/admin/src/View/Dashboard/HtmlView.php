<?php
namespace Dragonhydra\Component\Dragonhydra\Administrator\View\Dashboard;
defined('_JEXEC') or die;

use Joomla\CMS\Component\ComponentHelper;
use Joomla\CMS\Factory;
use Joomla\CMS\Language\Text;
use Joomla\CMS\MVC\View\HtmlView as BaseHtmlView;
use Joomla\CMS\Toolbar\ToolbarHelper;
use Dragonhydra\Component\Dragonhydra\Administrator\Service\Kernel;
use Dragonhydra\Component\Dragonhydra\Administrator\Model\ControlCenterModel;
use Dragonhydra\Component\Dragonhydra\Administrator\Service\ControlWorkflow;

final class HtmlView extends BaseHtmlView
{
    public string $section = 'overview';
    public array $center = [];
    public array $data = [];
    public ?string $error = null;
    public bool $canImport = false;
    public array $probe = [];
    public string $dashboardUrl = '';
    public string $jobId = '';
    public string $workflowMatchId = '';
    public array $workflowKeys = [];

    public function display($tpl = null): void
    {
        $app = Factory::getApplication();
        $user = $app->getIdentity();
        if (!$user->authorise('core.manage', 'com_dragonhydra')) {
            throw new \RuntimeException('JERROR_ALERTNOAUTHOR', 403);
        }
        ToolbarHelper::title('DRAGONHYDRA CORE NEXT · System Control Center', 'chart-line');
        if ($user->authorise('core.options', 'com_dragonhydra')) {
            ToolbarHelper::preferences('com_dragonhydra');
        }
        $this->section = ControlCenterModel::section($app->input->getCmd('section', 'overview'));
        $this->canImport = $user->authorise('dragonhydra.import', 'com_dragonhydra');
        $this->probe = (array) $app->getUserState('com_dragonhydra.last_probe', []);
        $url = (string) ComponentHelper::getParams('com_dragonhydra')->get('dashboard_url', '');
        $parts = parse_url($url);
        if ($parts && in_array($parts['scheme'] ?? '', ['http', 'https'], true)
            && in_array($parts['host'] ?? '', ['127.0.0.1', '[::1]'], true)
            && !in_array((int) ($parts['port'] ?? 0), range(18740, 18751), true)
            && !isset($parts['user']) && !isset($parts['pass'])) {
            $this->dashboardUrl = $url;
        }
        try {
            $api = Kernel::client();
            $expectedId = (string) ComponentHelper::getParams('com_dragonhydra')->get('core_next_installation_id', '');
            $this->center = (new ControlCenterModel($expectedId))->build([
                'section'=>$this->section, 'module'=>$app->input->getString('module', ''),
                'match_id'=>$app->input->getString('match_id', ''), 'job_id'=>$app->input->getString('job_id', ''),
                'offset'=>$app->input->getInt('offset', 0),
                'layer'=>$app->input->getString('layer',''), 'category'=>$app->input->getString('category',''),
                'status'=>$app->input->getString('status',''),
            ], true, static fn(string $path): array => $api->request('GET', $path));
            $this->data = $this->center['data'];
            $this->jobId = $this->center['job_id'];
            $this->error = $this->center['error'];
            $this->workflowMatchId = $app->input->getString('match_id','');
            if ($this->canImport && !empty($this->center['workflow'])) {
                foreach (['forecasts','evaluations'] as $operation) {
                    $this->workflowKeys[$operation] = ControlWorkflow::formKey($app,$this->workflowMatchId,$operation);
                }
            }
        } catch (\RuntimeException $error) {
            $this->error = 'The CORE NEXT backend is unavailable. Check this installation’s protected bridge and retry.';
        }
        $this->getDocument()->setTitle('CORE NEXT · System Control Center');
        $assets = $this->getDocument()->getWebAssetManager();
        $assets->getRegistry()->addExtensionRegistryFile('com_dragonhydra');
        $assets->useStyle('com_dragonhydra.control-center');
        parent::display($tpl);
    }
}
