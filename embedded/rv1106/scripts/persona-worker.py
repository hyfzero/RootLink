"""Source checkout / deployment bundle entry point for the shared core."""
from pathlib import Path
import sys

source = Path(__file__).resolve().parents[3] / "src"
if source.is_dir():
    sys.path.insert(0, str(source))
from agent_core.headless import main

raise SystemExit(main())
