<?php
namespace Dragonhydra\Component\Dragonhydra\Site\Controller;
defined('_JEXEC') or die;

use Joomla\CMS\MVC\Controller\BaseController;

final class DisplayController extends BaseController
{
    protected $default_view = 'dashboard';

    public function display($cachable = false, $urlparams = [])
    {
        // Anonymous requests may render the branded shell; the model never calls
        // the bridge without a real, authorised site identity.
        $this->app->setHeader('Cache-Control', 'private, no-store, max-age=0', true);
        $this->app->setHeader('Referrer-Policy', 'same-origin', true);
        $this->input->set('view', 'dashboard');
        $view = $this->getView('Dashboard', 'html', 'Site');
        $view->setModel($this->getModel('Workspace', 'Site', ['ignore_request' => true]), true);
        $view->setDocument($this->app->getDocument());
        $view->display();
        return $this;
    }
}
