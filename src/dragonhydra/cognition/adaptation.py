"""Select only comparable, eligible operational performance for model adaptation."""
from .. import public_results, research
from . import evaluation, models

VERSION='operational-adaptation/1'


def select(memory_view, source_rows, target, cutoff, *, minimum_cases=20, raw_resolver=None):
    if not isinstance(memory_view,dict) or not isinstance(source_rows,list) or not isinstance(target,dict):
        raise ValueError('INVALID_ADAPTATION_INPUT')
    records=memory_view.get('evaluations')
    outcomes=memory_view.get('outcomes')
    if not isinstance(records,list) or not isinstance(outcomes,list):
        raise ValueError('INVALID_ADAPTATION_INPUT')
    if type(minimum_cases) is not int or minimum_cases < 1:
        raise ValueError('INVALID_MINIMUM_CASES')
    decision=research._time(cutoff)
    if not callable(raw_resolver):
        return {'records':[],'reason':'EVALUATION_SOURCE_VERIFICATION_UNAVAILABLE',
                'minimum_cases':minimum_cases,'evidence_ids':[],
                'transformation':{'version':VERSION,'formula':'require retained source bytes for adaptive evidence'}}
    ambiguous=public_results.find_ambiguous_fixtures(source_rows,decision.isoformat())
    cache={}
    def verified_conflict(flag):
        ids=set(flag['evidence_ids'])
        for row in source_rows:
            if isinstance(row,dict) and row.get('evidence_id') in ids and research._fully_known_before(row,decision):
                evaluation._verify_public(row,decision,raw_resolver,cache)
    for flag in ambiguous:
        if flag['source_id']==target.get('source_id') and target.get('fixture_key') in flag['fixture_keys']:
            verified_conflict(flag)
            return {'records':[],'reason':'AMBIGUOUS_TARGET_FIXTURE','minimum_cases':minimum_cases,
                    'evidence_ids':flag['evidence_ids'],
                    'transformation':{'version':VERSION,'formula':'reject unresolved cutoff-eligible fixture-date conflicts'}}
    latest={}
    for item in records:
        if not isinstance(item,dict) or not research._fully_known_before(item,decision):
            continue
        scope=item.get('evaluation_scope')
        if not isinstance(scope,dict) or any(scope.get(k)!=target.get(k) for k in ('source_id','competition','period','settlement')):
            continue
        name=item.get('model')
        if name not in models.NAMES or item.get('model_version')!=models.VERSION or item.get('metric')!='brier':
            continue
        if type(item.get('sample_size')) is not int or item['sample_size'] < minimum_cases:
            continue
        keys=item.get('fixture_keys')
        if not isinstance(keys,list) or len(keys)!=item['sample_size'] or len(set(keys))!=len(keys):
            continue
        cases=item.get('cases')
        if (not isinstance(cases,list) or len(cases)!=len(keys) or
            not all(isinstance(case,dict) and isinstance(case.get('fixture_key'),str) for case in cases) or
            sorted(case['fixture_key'] for case in cases)!=sorted(keys)):
            continue
        # Older evaluations remain auditable but cannot steer a new forecast
        # after an outcome correction or a newly imported source revision.
        valid=True
        for case in cases:
            fixture=case.get('fixture_key')
            conflicts=[flag for flag in ambiguous if flag['source_id']==scope['source_id'] and fixture in flag['fixture_keys']]
            if conflicts:
                for flag in conflicts:
                    verified_conflict(flag)
                valid=False
                break
            candidates=[o for o in outcomes if o.get('fixture_key')==fixture and
                        o.get('source_id')==scope['source_id'] and research._fully_known_before(o,decision)]
            latest_outcome=evaluation._latest_outcome(candidates) if candidates else None
            latest_sources=[r for r in source_rows if r.get('fixture_key')==fixture and
                            r.get('source_id')==scope['source_id'] and research._fully_known_before(r,decision)]
            if (not latest_outcome or latest_outcome.get('record_id')!=case.get('outcome_record_id') or
                len(latest_sources)!=1 or latest_sources[0].get('evidence_id')!=latest_outcome.get('source_evidence_id')):
                valid=False
                break
            evaluation._verify_public(latest_sources[0],decision,raw_resolver,cache)
        if not valid:
            continue
        order=(research._time(item['usable_at']),item.get('record_id',''))
        if name not in latest or order>latest[name][0]:
            latest[name]=(order,item)
    if set(latest)!=set(models.NAMES):
        return {'records':[],'reason':'INSUFFICIENT_COMPARABLE_OPERATIONAL_EVALUATIONS',
                'minimum_cases':minimum_cases,'evidence_ids':[],
                'transformation':{'version':VERSION,'formula':'require eligible scoped Brier evidence for every model'}}
    selected=[latest[name][1] for name in models.NAMES]
    cohorts={tuple(sorted(item['fixture_keys'])) for item in selected}
    if len(cohorts)!=1:
        return {'records':[],'reason':'EVALUATION_COHORTS_DIFFER','minimum_cases':minimum_cases,
                'evidence_ids':[item['record_id'] for item in selected],
                'transformation':{'version':VERSION,'formula':'all model evaluations must score the same fixture cohort'}}
    return {'records':[{'evidence_id':item['record_id'],'usable_at':item['usable_at']} for item in selected],
            'reason':None,'minimum_cases':minimum_cases,'evidence_ids':[item['record_id'] for item in selected],
            'transformation':{'version':VERSION,'formula':'latest cutoff-eligible same-scope same-cohort operational Brier evidence'}}
