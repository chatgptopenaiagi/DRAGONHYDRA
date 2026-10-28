"""Run the repository-local DRAGONHYDRA CLI without installation."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent / 'src'))
from dragonhydra.cli import main

if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (ValueError, OSError) as exc:
        print('Unavailable:', exc, file=sys.stderr)
        raise SystemExit(2)
