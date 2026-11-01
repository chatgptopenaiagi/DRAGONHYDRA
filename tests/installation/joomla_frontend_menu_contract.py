"""Narrow semantic comparison for Joomla's managed Home parameter serialization.

Native menu forms add these documented defaults and discard an undeclared internal
marker. Preserve every other value; a real title/visibility/custom-field change is
still a mismatch. Do not treat all parameter-hash changes as harmless.
"""
NATIVE_DEFAULTS = {
    'menu-anchor_title': '', 'menu-anchor_css': '', 'menu_icon_css': '',
    'menu_image': '', 'menu_image_css': '', 'menu_text': '1', 'menu_show': '1',
    'page_heading': '', 'menu-meta_description': '', 'robots': '',
}


def normalize_home_params(params):
    normalized = dict(params)
    if 'dragonhydra_workspace_home' in normalized:
        if normalized.pop('dragonhydra_workspace_home') != 1:
            raise ValueError('Unexpected internal marker value')
    for key, value in NATIVE_DEFAULTS.items():
        normalized.setdefault(key, value)
    for key in ('menu_text', 'menu_show'):
        if normalized[key] in (0, 1, '0', '1'):
            normalized[key] = str(int(normalized[key]))
    return normalized


def site_menus_equivalent(before, after, managed_home_id, before_params, after_params):
    old = {row['id']: dict(row) for row in before if row['client_id'] == 0}
    new = {row['id']: dict(row) for row in after if row['client_id'] == 0}
    if set(old) != set(new) or managed_home_id not in old:
        return False
    old[managed_home_id].pop('params_sha256', None)
    new[managed_home_id].pop('params_sha256', None)
    return old == new and normalize_home_params(before_params) == normalize_home_params(after_params)
