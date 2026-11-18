"""Compatibility entry point; use production_cli.py for the interactive console."""
import sys
from production_cli import main
if __name__ == '__main__':
    if len(sys.argv) > 1 and not sys.argv[1].startswith('--'):
        sys.argv.insert(1, '--port')
    main()
