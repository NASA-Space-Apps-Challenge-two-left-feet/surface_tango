"""Make repository modules importable for the scoped MCP suite via pytest CLI."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
