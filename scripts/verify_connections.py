"""Exercise actual API sync jobs and write sanitized project-local evidence."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import time
import httpx


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--state', required=True, type=Path)
    parser.add_argument('--url', required=True)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--sources', nargs='+', default=['openfootball', 'football-data-couk', 'statsbomb', 'nflverse', 'moneypuck', 'cricsheet', 'football-data-org', 'api-football', 'the-odds-api', 'sportmonks'])
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    token = json.loads((args.state/'local-session.json').read_text())['token']
    started = datetime.now(timezone.utc).isoformat()
    results = []
    with httpx.Client(base_url=args.url+'/dragon/api/v1', headers={'Authorization': 'Bearer '+token}, timeout=30) as client:
        for provider in args.sources:
            response = client.post('/connections/'+provider+'/sync', json={})
            response.raise_for_status()
            job_id = response.json()['id']
            until = time.monotonic()+170
            while True:
                job = client.get('/jobs/'+job_id).json()
                if job['status'] in ('succeeded', 'failed', 'cancelled', 'interrupted') or time.monotonic()>until:
                    break
                # A bounded retry honors provider cooldown; do not bypass quota.
                if job['status']=='queued' and job.get('error', {}).get('retry_after', 0) if job.get('error') else False:
                    break
                time.sleep(.3)
            result = {'provider': provider, 'job': job}
            results.append(result)
            print(json.dumps({'provider': provider, 'status': job['status'], 'result': job.get('result'), 'error': job.get('error')}, ensure_ascii=False), flush=True)
            (args.output/(provider+'.json')).write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding='utf-8')
        cards = client.get('/connections').json()
        (args.output/'connections.json').write_text(json.dumps(cards, indent=2, ensure_ascii=False), encoding='utf-8')
        summary = {'started_at': started, 'finished_at': datetime.now(timezone.utc).isoformat(),
                   'results': results, 'connections': cards}
        (args.output/'summary.json').write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding='utf-8')
        passed = [r for r in results if r['job']['status']=='succeeded' and r['provider']!='openfootball']
        print('PUBLIC SOURCES STORED:', len(passed), flush=True)
        if len(passed)<3:
            raise SystemExit('Fewer than three new public sources ingested successfully.')


if __name__=='__main__':
    main()
