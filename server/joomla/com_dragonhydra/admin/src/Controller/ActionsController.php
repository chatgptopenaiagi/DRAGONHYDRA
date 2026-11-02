<?php
namespace Dragonhydra\Component\Dragonhydra\Administrator\Controller;
defined('_JEXEC') or die;

use Joomla\CMS\MVC\Controller\BaseController;
use Joomla\CMS\Router\Route;
use Joomla\CMS\Session\Session;
use Joomla\CMS\Component\ComponentHelper;
use Dragonhydra\Component\Dragonhydra\Administrator\Service\Kernel;
use Dragonhydra\Component\Dragonhydra\Administrator\Service\ControlWorkflow;

final class ActionsController extends BaseController
{
    private function guard(): void
    {
        if (!Session::checkToken('post')) {
            throw new \RuntimeException('JINVALID_TOKEN', 403);
        }
        $user = $this->app->getIdentity();
        if (!$user->authorise('core.manage', 'com_dragonhydra') || !$user->authorise('dragonhydra.import', 'com_dragonhydra')) {
            throw new \RuntimeException('JERROR_ALERTNOAUTHOR', 403);
        }
        $expected = (string) ComponentHelper::getParams('com_dragonhydra')->get('core_next_installation_id', '');
        $registry = Kernel::client()->request('GET', '/modules');
        if ($expected === '' || ($registry['installation']['product'] ?? '') !== 'DRAGONHYDRA CORE NEXT'
            || ($registry['installation']['installation_id'] ?? '') !== $expected) {
            throw new \RuntimeException('CORE_NEXT_INSTALLATION_MISMATCH', 403);
        }
    }

    public function sync(): void
    {
        $this->guard();
        try {
            // The browser selects no executable, URL, adapter path or arbitrary operation.
            $job = Kernel::client()->request('POST', '/connections/openfootball/sync', []);
            $this->setRedirect(Route::_('index.php?option=com_dragonhydra&section=jobs&job_id=' . rawurlencode((string) $job['id']), false), 'Import queued. Follow the job to open its imported matches.');
        } catch (\RuntimeException $error) {
            $this->setRedirect(Route::_('index.php?option=com_dragonhydra&section=sources', false), $error->getMessage(), 'error');
        }
    }

    public function probe(): void
    {
        $this->guard();
        $id = $this->input->post->getCmd('connection_id', '');
        if (!preg_match('/^[a-z0-9_-]{1,80}$/D', $id)) {
            throw new \RuntimeException('INVALID_CONNECTION_ID', 400);
        }
        try {
            $proof = Kernel::client()->request('POST', '/connections/' . $id . '/test', []);
            $this->app->setUserState('com_dragonhydra.last_probe', $proof);
            $this->setRedirect(Route::_('index.php?option=com_dragonhydra&section=sources', false), 'Capability check completed. Review the returned proof below.');
        } catch (\RuntimeException $error) {
            $this->setRedirect(Route::_('index.php?option=com_dragonhydra&section=sources', false), $error->getMessage(), 'error');
        }
    }

    public function cancel(): void
    {
        $this->guard();
        $id = $this->input->post->getCmd('job_id', '');
        if (!preg_match('/^[a-zA-Z0-9_-]{1,80}$/D', $id)) {
            throw new \RuntimeException('INVALID_JOB_ID', 400);
        }
        try {
            Kernel::client()->request('POST', '/jobs/' . $id . '/cancel', []);
            $this->setRedirect(Route::_('index.php?option=com_dragonhydra&section=jobs&job_id=' . rawurlencode($id), false), 'Cancellation requested.');
        } catch (\RuntimeException $error) {
            $this->setRedirect(Route::_('index.php?option=com_dragonhydra&section=jobs&job_id=' . rawurlencode($id), false), $error->getMessage(), 'error');
        }
    }

    public function observe(): void
    {
        $this->guard();
        try {
            $expected=(string)ComponentHelper::getParams('com_dragonhydra')->get('core_next_installation_id','');
            $result=Kernel::client()->request('POST','/modules/observe',[]);
            if (($result['schema_version'] ?? '') !== 'core-next.local-observation/1'
                || ($result['installation']['product'] ?? '') !== 'DRAGONHYDRA CORE NEXT'
                || ($result['installation']['installation_id'] ?? '') !== $expected) { throw new \RuntimeException('INVALID_LOCAL_OBSERVATION'); }
            $message=match($result['status'] ?? '') {
                'completed'=>'Local checks completed. Read each module’s evidence and reason; completion does not mean every module is ready.',
                'busy'=>'Another local check is already running. No second check was started.',
                'disabled'=>'Local checks are disabled. No new check was completed.',
                default=>throw new \RuntimeException('INVALID_LOCAL_OBSERVATION'),
            };
            $this->setRedirect(Route::_('index.php?option=com_dragonhydra&section=overview',false),$message);
        } catch (\RuntimeException $error) {
            $this->setRedirect(Route::_('index.php?option=com_dragonhydra&section=overview',false),'The local check could not be confirmed for this installation. Existing observations remain visible with their original clocks.','error');
        }
    }

    public function forecast(): void { $this->workflow('forecasts'); }
    public function evaluate(): void { $this->workflow('evaluations'); }

    private function workflow(string $operation): void
    {
        $this->guard();
        $id=ControlWorkflow::matchId($this->input->post->getString('match_id',''));
        $key=$this->input->post->getString('command_key','');
        $expected=(string)$this->app->getUserState(ControlWorkflow::slot($id,$operation),'');
        try {
            $api=Kernel::client();
            $job=ControlWorkflow::submit(fn($method,$path,$payload,$command)=>$api->request($method,$path,$payload,$command),$id,$operation,$key,$expected);
            $this->setRedirect(Route::_('index.php?option=com_dragonhydra&section=jobs&job_id='.$job['id'],false),
                'Explicit workflow command submitted. Job completion and retained result availability are reported separately.');
        } catch (\RuntimeException $error) {
            $this->setRedirect(Route::_('index.php?option=com_dragonhydra&section=prediction&match_id='.$id,false),
                'Workflow command submission could not be confirmed. Retry with the same command key to reuse its job.','error');
        }
    }
}
