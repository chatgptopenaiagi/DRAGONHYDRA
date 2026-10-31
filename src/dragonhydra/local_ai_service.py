"""Explicit optional local inference through the existing durable worker.

Configuration belongs to the server process, never a client-supplied endpoint.
The queued package freezes the selected evidence before a later source revision.
"""
from __future__ import annotations

from . import local_ai
from .local_ai_settings import Settings
from .product import now


def explain(product, package, check=lambda: None):
    check()
    local_ai.validate_grounding(product, package)
    evidence = package['evidence']['E1']
    event = package['event']
    context_package = package['schema_version'] == local_ai.SCHEMA_CONTEXT
    first_observation = (package['allowed_facts'][0]['observation'] if context_package
                         else package['allowed_observations'][0])
    input_manifest = [evidence['id']]
    if context_package:
        context = package['evidence']['C1']
        input_manifest.extend([context['id'], context['documents']['events']['id'],
                               context['documents']['lineups']['id']])
    result = {
        'kind': 'deterministic', 'summary': event['home']['name'] + ' vs ' + event['away']['name'],
        'match_id': event['id'], 'observations': [first_observation],
        'evidence': [{'id': evidence['id'], 'url': '/dragon/api/v1/evidence/' + evidence['id'],
                      'label': 'Retained source record'}],
        'input_manifest': input_manifest, 'package_sha256': package['package_sha256'],
        'cutoff': now(), 'version': 'local-source-fact/1', 'unknowns': []}
    try:
        endpoint, key = Settings(product.state).effective()
        if not endpoint or not key:
            raise local_ai.LocalAIError('AI_NOT_CONFIGURED', 'Local model endpoint and protected server key are not configured.')
        accepted = local_ai.infer(package, endpoint, key, timeout=25, check=check)
    except local_ai.LocalAIError as error:
        result['local_ai'] = {'requested': True, 'accepted': False, 'code': error.code, 'message': error.message}
        result['unknowns'] = ['Local inference was unavailable or rejected; this summary is deterministic.']
        return result
    result.update(kind=accepted['kind'], mode=accepted['mode'], observations=[accepted['observation']],
                  runtime=accepted['runtime'], unknowns=[accepted['limitation']],
                  local_ai={'requested': True, 'accepted': True})
    if context_package:
        result.update(fact_id=accepted['fact_id'], evidence_aliases=accepted['evidence_aliases'],
                      evidence=accepted['evidence'], input_manifest=accepted['input_manifest'])
    return result
