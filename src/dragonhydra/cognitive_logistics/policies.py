"""Bounded inventory decisions over public forecasts, without side effects."""
import math

from .forecast import integer, number, protection_distribution, safety_stock

POLICIES = ('reorder_point', 'order_up_to', 'base_stock', 's_S', 'probabilistic_cost')
COSTS = ('holding', 'ordering', 'shortage', 'transport', 'spoilage', 'acquisition', 'computation')
DEFAULT_COSTS = {'holding': .1, 'ordering': 1., 'shortage': 3., 'transport': .05,
                 'spoilage': 0., 'acquisition': 0., 'computation': 0.}
DEFAULTS = {'service_level': .95, 'objective': 'cycle_service_level', 'review_period': 1,
            'min_order': 1, 'order_multiple': 1, 'max_order': 500}
OPTIONAL = {'reorder_point', 'order_up_to', 's', 'S', 'base_stock', 'fixed_quantity'}


def _inventory(raw):
    required = {'on_hand', 'on_order', 'backorder', 'inventory_position', 'capacity', 'reserved', 'atp'}
    if not isinstance(raw, dict) or not required <= set(raw) or set(raw)-required-{'in_transit'}:
        raise ValueError('LOGISTICS_INVENTORY_SCHEMA')
    result = {key: integer(raw[key], 0, 1000000) for key in required-{'inventory_position'}}
    result['inventory_position'] = integer(raw['inventory_position'], -1000000, 2000000)
    if (result['on_hand'] > result['capacity'] or result['reserved'] > result['on_hand'] or result['atp'] != result['on_hand']-result['reserved']
            or result['inventory_position'] != result['on_hand']+result['on_order']-result['backorder']):
        raise ValueError('LOGISTICS_INVENTORY_IDENTITY_MISMATCH')
    if 'in_transit' in raw and integer(raw['in_transit'], 0, 1000000) > result['on_order']:
        raise ValueError('LOGISTICS_TRANSIT_NOT_SUBSET_OF_ON_ORDER')
    return result


def _parameters(params):
    if params is not None and (not isinstance(params, dict) or set(params)-set(DEFAULTS)-OPTIONAL-{'costs'}):
        raise ValueError('LOGISTICS_POLICY_PARAMETERS')
    result = {**DEFAULTS, **(params or {})}
    result['service_level'] = number(result['service_level'], .001, .999)
    integer(result['review_period'], 0, 30)
    for key in ('min_order', 'order_multiple', 'max_order'):
        integer(result[key], 1, 1000)
    for key in OPTIONAL & result.keys():
        integer(result[key], 0, 1000000)
    if result['min_order'] > result['max_order']:
        raise ValueError('LOGISTICS_ORDER_MINIMUM_EXCEEDS_MAXIMUM')
    costs = result.get('costs', DEFAULT_COSTS)
    if not isinstance(costs, dict) or set(costs) != set(COSTS):
        raise ValueError('LOGISTICS_SEVEN_COST_COMPONENTS_REQUIRED')
    result['costs'] = {key: number(costs[key], 0, 1000000) for key in COSTS}
    return result


def _cost(quantity, position, support, probabilities, costs):
    expected_excess = math.fsum(max(0, position+quantity-demand)*p for demand, p in zip(support, probabilities))
    expected_shortage = math.fsum(max(0, demand-position-quantity)*p for demand, p in zip(support, probabilities))
    parts = {'holding': costs['holding']*expected_excess, 'ordering': costs['ordering']*int(quantity > 0),
             'shortage': costs['shortage']*expected_shortage, 'transport': costs['transport']*quantity,
             'spoilage': costs['spoilage']*expected_excess, 'acquisition': 0., 'computation': 0.}
    return {'total': math.fsum(parts.values()), 'components': parts,
            'expected_excess': expected_excess, 'expected_shortage': expected_shortage}


def _service(quantity, position, support, probabilities, cfg, mean):
    # Existing backlog consumes arriving units; a negative usable balance does
    # not create a negative fill fraction for the new protection-window demand.
    available = max(0, position+quantity)
    csl = min(1., max(0., math.fsum(p for demand, p in zip(support, probabilities) if demand <= available)))
    shortage = math.fsum(max(0, demand-available)*p for demand, p in zip(support, probabilities))
    fill = min(1., max(0., 1-shortage/mean)) if mean else None
    value = csl if cfg['objective'] == 'cycle_service_level' else fill
    return {'achieved_CSL': csl, 'expected_fill_rate': fill,
            'objective_service_value': value,
            'service_target_met': value + 1e-12 >= cfg['service_level'] if value is not None else None}


def recommend(inventory, demand_forecast, lead_forecast, policy='order_up_to', params=None):
    if policy not in POLICIES:
        raise ValueError('LOGISTICS_POLICY_UNSUPPORTED')
    stock, cfg = _inventory(inventory), _parameters(params)
    position = stock['inventory_position']
    physical_remaining = max(0, stock['capacity']-stock['on_hand']-stock['on_order'])
    maximum = min(cfg['max_order'], physical_remaining)
    feasible = [0] + [q for q in range(cfg['min_order'], maximum+1) if q % cfg['order_multiple'] == 0]
    lead = safety_stock(demand_forecast, lead_forecast, cfg['service_level'], cfg['objective'], 0)
    protection = safety_stock(demand_forecast, lead_forecast, cfg['service_level'], cfg['objective'], cfg['review_period'])
    reorder = cfg.get('reorder_point', lead['target_level'])
    target = cfg.get('order_up_to', protection['target_level'])
    support, probabilities = protection_distribution(demand_forecast, lead_forecast, cfg['review_period'])
    mean = protection['protection_mean']
    best_service = _service(max(feasible), position, support, probabilities, cfg, mean)
    target_feasible = best_service['service_target_met']
    selection_rule = 'HEURISTIC_WITH_SERVICE_DISCLOSURE'
    candidates = []
    raw = 0
    if policy == 'probabilistic_cost':
        for quantity in feasible:
            candidates.append({'quantity': quantity, 'total_cost': _cost(quantity, position, support, probabilities, cfg['costs'])['total'],
                               **_service(quantity, position, support, probabilities, cfg, mean)})
        satisfying = [item for item in candidates if item['service_target_met'] is True]
        if satisfying:
            selected = min(satisfying, key=lambda item: (item['total_cost'], item['quantity']))
            selection_rule = 'MINIMUM_COST_AMONG_SERVICE_FEASIBLE'
        elif target_feasible is None:
            selected = min(candidates, key=lambda item: (item['total_cost'], item['quantity']))
            selection_rule = 'MINIMUM_COST_SERVICE_NOT_APPLICABLE'
        else:
            selected = min(candidates, key=lambda item: (-item['objective_service_value'], item['total_cost'], item['quantity']))
            selection_rule = 'HIGHEST_ACHIEVABLE_SERVICE_THEN_MINIMUM_COST'
        quantity = selected['quantity']
        raw = quantity
    else:
        if policy == 'reorder_point':
            fixed = cfg.get('fixed_quantity', max(1, math.ceil(demand_forecast['daily_mean']*max(1, cfg['review_period']))))
            raw = fixed if position <= reorder else 0
        elif policy == 'order_up_to':
            raw = max(0, target-position)
        elif policy == 'base_stock':
            target = cfg.get('base_stock', lead['target_level'])
            raw = max(0, target-position)
        elif policy == 's_S':
            reorder = cfg.get('s', lead['target_level'])
            target = cfg.get('S', protection['target_level'])
            if target < reorder:
                raise ValueError('LOGISTICS_SMALL_S_EXCEEDS_BIG_S')
            raw = max(0, target-position) if position <= reorder else 0
        requested = max(cfg['min_order'], math.ceil(raw/cfg['order_multiple'])*cfg['order_multiple']) if raw > 0 else 0
        quantity = min((q for q in feasible if q >= requested), default=max(feasible)) if requested else 0
        candidates = [{'quantity': quantity, 'total_cost': _cost(quantity, position, support, probabilities, cfg['costs'])['total'],
                       **_service(quantity, position, support, probabilities, cfg, mean)}]
    expected = _cost(quantity, position, support, probabilities, cfg['costs'])
    achieved = _service(quantity, position, support, probabilities, cfg, mean)
    return {'schema_version': 'dragonhydra.logistics-policy/1', 'policy': policy, 'quantity': quantity,
            'inventory_position': position, 'reorder_point': reorder, 'target_level': target,
            'requested_service_objective': cfg['objective'], 'requested_service_level': cfg['service_level'],
            'service_target_feasible': target_feasible, 'service_objective_applicable': target_feasible is not None,
            **achieved,
            'expected_cost': expected, 'candidates': candidates,
            'evidence': {'cutoff': demand_forecast['cutoff'], 'demand_model_id': demand_forecast['model_id'],
                         'lead_model_id': lead_forecast['model_id'], 'protection': protection,
                         'raw_requested_quantity': raw, 'capacity_order_limit': physical_remaining,
                         'feasible_maximum': max(feasible), 'capacity_or_parameter_limited': quantity < raw or target_feasible is False,
                         'feasible_candidate_count': len(feasible), 'costs': dict(cfg['costs']),
                         'best_achievable_forecast_service': best_service, 'selection_rule': selection_rule,
                         'service_scope': 'FORECAST_LEAD_PLUS_REVIEW_PROTECTION_IF_RECOMMENDED_QUANTITY_IS_AVAILABLE',
                         'assumptions': [
                             'Inventory position = on_hand + on_order - backorder; reserved affects ATP only.',
                             'In-transit quantity is already part of on_order, never counted twice.',
                             'Conservative committed capacity: on_hand + on_order + new quantity <= capacity.',
                             'Probabilistic cost minimizes the surrogate among forecast-service-feasible quantities; if none meet target it prioritizes highest achievable service, then cost.',
                             'This is an uncalibrated one-protection-period surrogate, not dynamic optimality or realized service; later routing/supply clipping can reduce actual quantity.',
                             'Zero-demand expected unit fill rate is undefined; no fill-target success or feasibility is manufactured.',
                             'Holding/spoilage charge expected excess; no shelf-age model is inferred.',
                             'Acquisition/computation are measured externally; no fictitious paid AI or hardware cost is inserted here.']}}
