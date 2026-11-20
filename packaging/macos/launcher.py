"""Start the desktop app from Finder and retain the existing CLI for diagnostics."""

import sys

if __name__ == "__main__":
    arguments = [arg for arg in sys.argv[1:] if not arg.startswith("-psn_")]
    if arguments[:1] == ["--babel-worker"]:
        from orcaview.io.babel_worker import main
        raise SystemExit(main(arguments[1:]))

    from orcaview.cli import main
    raise SystemExit(main(arguments or ["gui"]))
