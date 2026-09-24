from urllib.robotparser import RobotFileParser
from urllib.parse import urlsplit
from .contracts import utcnow, PipelineError


def evaluate_robots(text, url, user_agent, status=200):
    p = urlsplit(url)
    evidence = {'robots_url': f'{p.scheme}://{p.netloc}/robots.txt',
                'robots_checked_at': utcnow(), 'allowed_path': None, 'disallowed_path': None,
                'crawl_delay_if_any': None, 'http_status': status}
    if status == 404:
        evidence.update(robots_status='ABSENT', allowed_path=p.path)
        return evidence
    if status != 200:
        raise PipelineError('ROBOTS_BLOCKED')
    parser = RobotFileParser()
    parser.parse(text.splitlines())
    allowed = parser.can_fetch(user_agent, url)
    evidence.update(robots_status='ALLOWED' if allowed else 'DISALLOWED',
                    allowed_path=p.path if allowed else None, disallowed_path=None if allowed else p.path,
                    crawl_delay_if_any=parser.crawl_delay(user_agent))
    return evidence
