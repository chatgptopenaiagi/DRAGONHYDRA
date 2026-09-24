"""Immutable bridge events preserve capture origin separately from processing state."""
from uuid import uuid4
from .contracts import utcnow, timestamp
from .provenance import exclusive_json, bounded_file
from .json_api import parse_json

STATES = {'NO_HANDOFF','DESKTOP_CONFIRMED','CLI_FETCHED','BLOCKED_BROWSER_UNAVAILABLE','BLOCKED','PROCESSING','PROCESSED','FAILED'}
ORIGINS = {'DESKTOP_BROWSER','CLI_FETCH','NONE','SYNTHETIC','MANUAL'}


def bridge_event(root, state, origin, handoff_id=None, receipt_path=None, desktop_evidence=None):
    if state not in STATES or origin not in ORIGINS:
        raise ValueError('Unknown bridge state/origin')
    if state == 'DESKTOP_CONFIRMED' and (origin != 'DESKTOP_BROWSER' or not desktop_evidence):
        raise ValueError('Desktop evidence required')
    event = {'state':state,'origin':origin,'handoff_id':handoff_id,'receipt_path':receipt_path,
             'desktop_evidence':desktop_evidence,'recorded_at':utcnow(),'event_id':uuid4().hex}
    exclusive_json(root/'runtime/handoff/manifests/bridge_events'/f'{event["event_id"]}.json',event)
    return event


def bridge_status(root):
    directory = root/'runtime/handoff/manifests/bridge_events'
    events = []
    for path in directory.glob('*.json'):
        event = parse_json(bounded_file(path,directory,32000))
        if event.get('state') not in STATES or event.get('origin') not in ORIGINS:
            continue
        timestamp(event['recorded_at'])
        events.append(event)
    if not events:
        return {'state':'NO_HANDOFF','origin':'NONE','desktop_result':'NOT_CONFIRMED','recorded_at':None}
    result = dict(max(events,key=lambda e:(timestamp(e['recorded_at']),e['event_id'])))
    confirmed = [e for e in events if e['state']=='DESKTOP_CONFIRMED' and e['origin']=='DESKTOP_BROWSER' and e.get('desktop_evidence')]
    result['desktop_result'] = 'CONFIRMED' if confirmed else 'NOT_CONFIRMED'
    result['last_desktop_handoff_id'] = max(confirmed,key=lambda e:timestamp(e['recorded_at']))['handoff_id'] if confirmed else None
    return result


def manifest_origin(manifest):
    # Generic Desktop labels and CLI notes do not establish rendered browser research.
    return 'DESKTOP_BROWSER' if manifest.capture_method == 'DESKTOP_BROWSER_RENDERED' else 'CLI_FETCH'
