<?php
namespace Dragonhydra\Component\Dragonhydra\Administrator\Controller;
defined('_JEXEC') or die;

use Joomla\CMS\MVC\Controller\BaseController;
use Joomla\CMS\Router\Route;
use Joomla\CMS\Session\Session;
use Dragonhydra\Component\Dragonhydra\Administrator\Service\Kernel;

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
}
