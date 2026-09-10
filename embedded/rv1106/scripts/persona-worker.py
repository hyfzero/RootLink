"""Entry point for the shared core in a checkout or deployment bundle."""
try:
    # The deployment bundle installs agent_core in site-packages.  Import it
    # before looking for a checkout: /opt/rootlink is intentionally shallow.
    from agent_core.headless import main
except ModuleNotFoundError:
    from pathlib import Path
    import sys

    source = Path(__file__).resolve().parents[3] / "src"
    if not source.is_dir():
        raise
    sys.path.insert(0, str(source))
    from agent_core.headless import main

raise SystemExit(main())
