<?php
namespace Dragonhydra\Component\Dragonhydra\Site\Controller;
defined('_JEXEC') or die;

use Joomla\CMS\MVC\Controller\BaseController;
use Joomla\CMS\Router\Route;
use Joomla\CMS\Session\Session;
use Dragonhydra\Component\Dragonhydra\Site\Model\WorkspaceModel;
use Dragonhydra\Component\Dragonhydra\Site\Service\Kernel;

final class ActionsController extends BaseController
{
    private function guard(bool $mutation): void
    {
        if (!Kernel::canRead($this->app->getIdentity())) {
            throw new \RuntimeException('JERROR_ALERTNOAUTHOR', 403);
        }
        if ($mutation && !Session::checkToken('post')) {
            throw new \RuntimeException('JINVALID_TOKEN', 403);
        }
        $this->app->setHeader('Cache-Control', 'private, no-store, max-age=0', true);
    }

    public function export(): void
    {
        $this->guard(true);
        $id = WorkspaceModel::identifier($this->input->post->getString('match_id', ''));
        $format = $this->input->post->getCmd('format', '');
        if (!$id || !in_array($format, ['json', 'csv', 'xlsx'], true)) {
            throw new \RuntimeException('INVALID_EXPORT_REQUEST', 400);
        }
        try {
            $job = Kernel::client()->request('POST', '/exports', ['match_id' => $id, 'format' => $format]);
            $jobId = WorkspaceModel::identifier($job['id'] ?? '', 32);
            if (!$jobId || ($job['kind'] ?? '') !== 'export') {
                throw new \RuntimeException('INVALID_EXPORT_RESPONSE');
            }
            $this->setRedirect(Route::_('index.php?option=com_dragonhydra&section=reports&match_id=' . $id . '&job_id=' . $jobId, false));
        } catch (\Throwable $error) {
            $this->setRedirect(Route::_('index.php?option=com_dragonhydra&section=reports&match_id=' . $id, false), 'The export could not be started. Existing records and settings are unchanged.', 'warning');
        }
    }

    public function download(): void
    {
        $this->guard(false);
        $id = WorkspaceModel::identifier($this->input->getString('job_id', ''), 32);
        if (!$id) {
            throw new \RuntimeException('INVALID_EXPORT_REQUEST', 400);
        }
        $client = Kernel::client();
        // The reader-signed backend request checks the exact Joomla job owner.
        $job = $client->request('GET', '/jobs/' . $id);
        if (($job['kind'] ?? '') !== 'export' || ($job['status'] ?? '') !== 'succeeded') {
            throw new \RuntimeException('EXPORT_NOT_READY', 409);
        }
        $file = $client->download('/exports/' . $id . '/download');
        $extension = strtolower(pathinfo((string) ($job['result']['filename'] ?? ''), PATHINFO_EXTENSION));
        $types = ['json' => 'application/json', 'csv' => 'text/csv; charset=utf-8', 'xlsx' => 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'];
        if (!isset($types[$extension]) || !is_string($file['body'] ?? null)) {
            throw new \RuntimeException('INVALID_EXPORT_RESPONSE', 502);
        }
        $this->app->setHeader('Content-Type', $types[$extension], true);
        $this->app->setHeader('Content-Disposition', 'attachment; filename="DRAGONHYDRA-' . $id . '.' . $extension . '"', true);
        $this->app->setHeader('X-Content-Type-Options', 'nosniff', true);
        $this->app->setHeader('Content-Length', (string) strlen($file['body']), true);
        $this->app->sendHeaders();
        echo $file['body'];
        $this->app->close();
    }
}
