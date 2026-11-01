<?php
namespace Dragonhydra\Component\Dragonhydra\Administrator\Service;
defined('_JEXEC') or die;

use Joomla\CMS\Factory;
use Joomla\CMS\Table\Menu;
use Joomla\Database\DatabaseInterface;

/** Idempotent presentation migration. Never reads or writes kernel/provider data. */
final class FrontendSetup
{
    public const TEMPLATE = 'cassiopeia_dragonhydra';
    public const HOME_LINK = 'index.php?option=com_dragonhydra&view=dashboard';

    /** Retain the module's behavior everywhere except one managed Home item. */
    public static function excludeMenu(array $assignments, int $menuId): array
    {
        if ($menuId <= 1) {
            throw new \InvalidArgumentException('INVALID_WORKSPACE_HOME');
        }
        $assignments = array_values(array_unique(array_map('intval', $assignments)));
        $hasAllOrExclusions = count(array_filter($assignments, static fn(int $value): bool => $value <= 0)) > 0;
        $assignments = array_values(array_filter($assignments, static fn(int $value): bool => $value !== $menuId));
        if ($hasAllOrExclusions && !in_array(-$menuId, $assignments, true)) {
            $assignments[] = -$menuId;
        }
        sort($assignments, SORT_NUMERIC);
        return $assignments;
    }

    public static function apply(?DatabaseInterface $db = null): array
    {
        $db ??= Factory::getContainer()->get(DatabaseInterface::class);
        $db->setQuery($db->createQuery()->select($db->quoteName('extension_id'))->from($db->quoteName('#__extensions'))
            ->where($db->quoteName('type') . '=' . $db->quote('component'))
            ->where($db->quoteName('element') . '=' . $db->quote('com_dragonhydra')));
        $componentId = (int) $db->loadResult();
        if (!$componentId) {
            throw new \RuntimeException('WORKSPACE_COMPONENT_NOT_REGISTERED');
        }
        $db->setQuery($db->createQuery()->select($db->quoteName('id'))->from($db->quoteName('#__template_styles'))
            ->where($db->quoteName('client_id') . '=0')->where($db->quoteName('template') . '=' . $db->quote(self::TEMPLATE))
            ->order($db->quoteName('id')));
        $styleId = (int) $db->loadResult();
        if (!$styleId) {
            throw new \RuntimeException('WORKSPACE_CHILD_TEMPLATE_NOT_INSTALLED');
        }
        $db->setQuery($db->createQuery()->select('*')->from($db->quoteName('#__menu'))
            ->where($db->quoteName('client_id') . '=0')->where($db->quoteName('home') . '=1')
            ->order($db->quoteName('id')));
        $homeItems = $db->loadObjectList();
        if (!$homeItems) {
            $homeItems = [(object) ['language' => '*', 'menutype' => 'mainmenu']];
        }
        $languages = [];
        foreach ($homeItems as $home) {
            $languages[(string) $home->language] = $home;
        }
        $report = ['configured' => true, 'template' => self::TEMPLATE, 'style_id' => $styleId,
            'home_ids' => [], 'created_home_ids' => [], 'module_assignment_changes' => 0,
            'articles_deleted' => false, 'modules_unpublished' => false, 'kernel_data_changed' => false];
        $db->transactionStart();
        try {
            foreach ($languages as $language => $oldHome) {
                $db->setQuery($db->createQuery()->select($db->quoteName('id'))->from($db->quoteName('#__menu'))
                    ->where($db->quoteName('client_id') . '=0')->where($db->quoteName('component_id') . '=' . $componentId)
                    ->where($db->quoteName('link') . '=' . $db->quote(self::HOME_LINK))
                    ->where($db->quoteName('language') . '=' . $db->quote($language))->order($db->quoteName('id')));
                $id = (int) $db->loadResult();
                $table = new Menu($db);
                if ($id && !$table->load($id)) {
                    throw new \RuntimeException('WORKSPACE_HOME_LOAD_FAILED');
                }
                if (!$id) {
                    $table->setLocation(1, 'last-child');
                    $table->alias = 'dragonhydra-workspace' . ($language === '*' ? '' : '-' . strtolower($language));
                    $table->parent_id = 1;
                    $table->menutype = (string) ($oldHome->menutype ?? 'mainmenu');
                }
                $table->title = 'DRAGONHYDRA';
                $table->link = self::HOME_LINK;
                $table->type = 'component';
                $table->component_id = $componentId;
                $table->published = 1;
                $table->home = 1;
                $table->language = $language;
                $table->access = 1;
                $table->client_id = 0;
                $table->template_style_id = $styleId;
                $params = json_decode((string) ($table->params ?? '{}'), true) ?: [];
                $params['show_page_heading'] = '0';
                $params['page_title'] = 'DRAGONHYDRA | Sports intelligence';
                $params['pageclass_sfx'] = ' dragonhydra-workspace-page';
                $params['dragonhydra_workspace_home'] = 1;
                $table->params = json_encode($params, JSON_THROW_ON_ERROR);
                if (!$table->check() || !$table->store()) {
                    throw new \RuntimeException('WORKSPACE_HOME_SAVE_FAILED');
                }
                $homeId = (int) $table->id;
                $report['home_ids'][] = $homeId;
                if (!$id) {
                    $report['created_home_ids'][] = $homeId;
                }
                $db->setQuery($db->createQuery()->select($db->quoteName('id'))->from($db->quoteName('#__modules'))
                    ->where($db->quoteName('client_id') . '=0')->where($db->quoteName('published') . '=1'));
                foreach ($db->loadColumn() as $moduleId) {
                    $moduleId = (int) $moduleId;
                    $db->setQuery($db->createQuery()->select($db->quoteName('menuid'))->from($db->quoteName('#__modules_menu'))
                        ->where($db->quoteName('moduleid') . '=' . $moduleId));
                    $before = array_values(array_unique(array_map('intval', $db->loadColumn())));
                    sort($before, SORT_NUMERIC);
                    $after = self::excludeMenu($before, $homeId);
                    if ($before === $after) {
                        continue;
                    }
                    $db->setQuery($db->createQuery()->delete($db->quoteName('#__modules_menu'))
                        ->where($db->quoteName('moduleid') . '=' . $moduleId))->execute();
                    foreach ($after as $menuId) {
                        $assignment = (object) ['moduleid' => $moduleId, 'menuid' => $menuId];
                        $db->insertObject('#__modules_menu', $assignment);
                    }
                    $report['module_assignment_changes']++;
                }
            }
            $db->transactionCommit();
        } catch (\Throwable $failure) {
            $db->transactionRollback();
            throw $failure;
        }
        // This is presentation setup only; retain all original menu/article/module records.
        return $report;
    }
}
