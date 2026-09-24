"""Validate a local Desktop draft and atomically publish its final envelope."""
import argparse,json
from ..config import PROJECT_ROOT
from ..web.provenance import bounded_file
from ..web.json_api import parse_json
from ..web.contracts import PipelineError
from .contracts import MAX_MANIFEST_BYTES
from .receipts import atomic_publish


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--draft',required=True)
    args=p.parse_args()
    try:
        draft=PROJECT_ROOT/args.draft
        raw=bounded_file(draft,PROJECT_ROOT/'runtime/handoff/browser_notes',MAX_MANIFEST_BYTES)
        result=atomic_publish(parse_json(raw),PROJECT_ROOT)
        print(json.dumps({'status':'PUBLISHED','path':str(result)}));return 0
    except Exception as error:
        print(json.dumps({'status':'REJECTED','reason':str(error) if isinstance(error,PipelineError) else type(error).__name__}));return 1


if __name__=='__main__':raise SystemExit(main())
