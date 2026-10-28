"""Explain model disagreement and turn measured gaps into bounded research tasks."""
from datetime import date, datetime, timezone

VERSION = 'cognitive-research/1'
OUTCOMES = ('home','draw','away')


def assess(forecast, market_rows, *, evaluated_predictions=0, disagreement_threshold=0.10,
           assessment_cutoff=None):
    if not isinstance(forecast, dict) or not isinstance(market_rows, list):
        raise ValueError('INVALID_RESEARCH_INPUT')
    if isinstance(evaluated_predictions, bool) or not isinstance(evaluated_predictions, int) or evaluated_predictions < 0:
        raise ValueError('INVALID_EVALUATION_COUNT')
    if isinstance(disagreement_threshold, bool) or not 0 <= float(disagreement_threshold) <= 1:
        raise ValueError('INVALID_DISAGREEMENT_THRESHOLD')
    ids = sorted({r['evidence_id'] for r in forecast.get('training_manifest', [])} |
                 {forecast['target']['evidence_id'], forecast['configuration']['evidence_id']})
    available = {name: model for name,model in forecast.get('models',{}).items() if model.get('available')}
    hypotheses=[]
    if 'frequency' in available and 'poisson_goals' in available:
        target_key=forecast['target'].get('fixture_key',forecast['target']['evidence_id'])
        hypotheses=[
            {'hypothesis_id':'model-assumptions:'+target_key,
             'claim':'The model differences may reflect their distinct goal and outcome assumptions.',
             'supporting_evidence_ids':ids,'contradicting_evidence_ids':[],
             'assumptions':['Both models use the retained eligible source observations.'],
             'missing_information':['Out-of-sample ablation separating model assumptions.'],
             'next_question':'Does a common-cohort ablation retain the difference?'},
            {'hypothesis_id':'sampling-variation:'+target_key,
             'claim':'The model differences may reflect limited-sample variation.',
             'supporting_evidence_ids':ids,'contradicting_evidence_ids':[],
             'assumptions':['The historical sample is not necessarily representative of the next match.'],
             'missing_information':['Uncertainty intervals and genuinely later forecast outcomes.'],
             'next_question':'How stable are the estimates across eligible data windows?'}]
    disagreement = {}
    for outcome in OUTCOMES:
        values = [float(m['probabilities'][outcome]['value']) for m in available.values()]
        disagreement[outcome] = {'value':max(values)-min(values) if len(values)>=2 else None,
            'units':'probability fraction','evidence_ids':ids,
            'reason':None if len(values)>=2 else 'INSUFFICIENT_MODELS',
            'transformation':{'version':VERSION,'formula':'maximum model probability minus minimum model probability'}}
    tasks = list(forecast.get('research_tasks', []))
    target_id = forecast['target']['evidence_id']
    training=forecast.get('training_manifest', [])
    freshness={'value':None,'reason':'NO_DATED_TRAINING_RESULTS' if training else 'NO_TRAINING_RESULTS','evidence_ids':[],
               'transformation':{'version':VERSION,'formula':'cutoff UTC date minus latest eligible source event date'}}
    dated=[]
    missing_dates=[]
    for row in training:
        try:
            dated.append((date.fromisoformat(row.get('event_date')),row['evidence_id']))
        except (TypeError,ValueError,KeyError):
            missing_dates.append(row.get('evidence_id'))
    if missing_dates:
        tasks.append({'gap':'RESULT_DATE_UNAVAILABLE',
            'question':'Can the missing source event dates be validated?',
            'permitted_source':'documented or user-supplied source',
            'priority_rationale':'Undated results cannot establish coverage freshness.',
            'expected_evidence':'dated source fixture and result records',
            'budget':'one bounded source check','stopping_condition':'dates verified or source unavailable',
            'evidence_ids':[eid for eid in missing_dates if eid]})
    if dated:
        latest_day=max(day for day,_ in dated)
        cutoff_day=datetime.fromisoformat(forecast['decision_cutoff'].replace('Z','+00:00')).date()
        latest_ids=[eid for day,eid in dated if day==latest_day]
        age=(cutoff_day-latest_day).days
        freshness={'value':age,'units':'calendar days','latest_event_date':latest_day.isoformat(),
                   'evidence_ids':latest_ids,'threshold_days':14,
                   'transformation':{'version':VERSION,'formula':'cutoff UTC date minus latest eligible source event date'}}
        if age>14:
            tasks.append({'gap':'STALE_RESULTS_COVERAGE',
                'question':'Can more recent verified results from the same competition be captured?',
                'permitted_source':'same documented source or independently verified equivalent',
                'priority_rationale':'The most recent eligible match is older than the configured coverage threshold.',
                'expected_evidence':'more recent source fixture and result records with actual acquisition times',
                'budget':'one bounded source update','stopping_condition':'new eligible results imported or source unavailable',
                'evidence_ids':latest_ids})
    # Fixture IDs belong to different source namespaces. A boolean supplied by
    # an observation is not proof of a temporal identity mapping; this layer
    # deliberately abstains until a persisted mapping resolver is available.
    matched = []
    if not matched:
        tasks.append({'gap':'MATCHING_MARKET_QUOTES_UNAVAILABLE',
            'question':'Can time-stamped quotes for the same verified fixture and settlement rules be obtained?',
            'permitted_source':'documented public or user-supplied provider',
            'priority_rationale':'A model-versus-market comparison requires a verified common fixture and market.',
            'expected_evidence':'source price snapshots, provider identity, settlement rules and acquisition clocks',
            'budget':'one bounded source investigation',
            'stopping_condition':'compatible quotes are validated or the source is unavailable',
            'evidence_ids':[target_id]})
    if evaluated_predictions == 0:
        tasks.append({'gap':'NO_SCORED_OPERATIONAL_PREDICTIONS',
            'question':'Can future persisted predictions be matched to later available outcomes?',
            'permitted_source':'persisted forecasts and validated result evidence',
            'priority_rationale':'Operational model performance and calibration need genuine later outcomes.',
            'expected_evidence':'prediction and subsequent outcome records with availability proof',
            'budget':'one evaluation after outcomes arrive',
            'stopping_condition':'eligible predictions are scored or no outcomes are available',
            'evidence_ids':[target_id]})
    if any(item['value'] is not None and item['value'] > float(disagreement_threshold) for item in disagreement.values()):
        tasks.append({'gap':'HIGH_MODEL_DISAGREEMENT',
            'question':'Which assumptions explain the disagreement between model estimates?',
            'permitted_source':'retained model inputs and independent context',
            'priority_rationale':'Divergent estimates increase forecast uncertainty.',
            'expected_evidence':'model ablation and independent, time-eligible context',
            'budget':'one bounded ablation','stopping_condition':'driver identified or evidence exhausted',
            'evidence_ids':ids})
    computed_at=datetime.now(timezone.utc).isoformat()
    if assessment_cutoff is None:
        assessment_cutoff=computed_at
    assessed=datetime.fromisoformat(assessment_cutoff.replace('Z','+00:00'))
    decision=datetime.fromisoformat(forecast['decision_cutoff'].replace('Z','+00:00'))
    if assessed.tzinfo is None or decision.tzinfo is None or assessed < decision or assessed > datetime.fromisoformat(computed_at):
        raise ValueError('INVALID_ASSESSMENT_CUTOFF')
    return {'computed_at':computed_at, 'decision_cutoff':forecast['decision_cutoff'],
            'assessment_cutoff':assessment_cutoff,
            'transformation_version':VERSION,'model_disagreement':disagreement,'latest_result_age':freshness,
            'uncertainty_summary':{'abstained':forecast.get('abstained', True),
                'unknowns':['Probability calibration and predictive improvement are not established.',
                            'No provider mapping is inferred across unrelated fixture namespaces.' if not matched else 'Quote timing and settlement must remain compatible.'],
                'model_count':len(available),'matched_quote_count':len(matched)},
            'matched_quote_evidence_ids':[row['evidence_id'] for row in matched], 'hypotheses':hypotheses,
            'research_tasks':tasks}
