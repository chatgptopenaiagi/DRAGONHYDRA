"""Entry point for installed or frozen DRAGONHYDRA applications."""
from pathlib import Path
import os
import sys


def workspace():
    """Honor an explicit workspace, otherwise find the enclosing checkout."""
    explicit = os.environ.get('DRAGONHYDRA_HOME')
    if explicit:
        return Path(explicit).expanduser().resolve()
    # An installed wheel must never find an unrelated checkout in an ancestor.
    if 'site-packages' in Path(__file__).resolve().parts:
        return Path.cwd().resolve()
    starts = (Path.cwd().resolve(), Path(sys.argv[0]).resolve().parent)
    visited = set()
    for start in starts:
        for candidate in (start, *start.parents):
            if candidate in visited:
                continue
            visited.add(candidate)
            if (candidate / 'dragon.py').is_file() and (candidate / 'src' / 'dragonhydra').is_dir():
                return candidate
    return Path.cwd().resolve()


def main():
    from . import cli, watch
    from .cognition import runtime
    root = workspace()
    cli.ROOT = root
    cli.DEFAULT_DB = root / 'runtime' / 'dragonhydra.sqlite3'
    watch.ROOT = root
    runtime.ROOT = root
    try:
        return cli.main()
    except (ValueError, OSError) as exc:
        print('Unavailable:', exc, file=sys.stderr)
        return 2
