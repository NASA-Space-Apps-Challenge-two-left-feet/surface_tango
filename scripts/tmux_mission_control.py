#!/usr/bin/env python3
"""Four-pane tmux telemetry HUD for the demo (MCP logs, Zarr latency, web/SSE logs, control deck).

python3 scripts/tmux_mission_control.py
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

SESSION = "sars-hud"
WINDOW = f"{SESSION}:mission-control"
PROJECT_ROOT = Path(__file__).resolve().parents[1]

PANES = {
    0: (
        "FASTMCP SERVERS (8001: NISAR ASF | 8002: GEE FUSION)",
        "docker compose logs -f --tail=40 mcp-nisar-asf mcp-gee-fusion 2>/dev/null"
        " || echo 'Run [make up] or [make pitch] in pane 3 to stream MCP tool calls...'",
    ),
    2: (
        "ZARR v3 TENSOR LATENCY & CIRCUIT-BREAKER TELEMETRY",
        "uv run python scripts/watch_zarr_telemetry.py",
    ),
    1: (
        "XYZ RASTER TILE STREAM & FASTAPI SSE EVENTS (PORT 8000)",
        "docker compose logs -f --tail=40 sars-web-orchestrator | grep --line-buffered -E"
        " 'local-tiles|stream-hazards|agent_update|CIRCUIT-BREAKER|GET|POST'",
    ),
    3: (
        "LANGGRAPH MULTI-AGENT DAG & INTERACTIVE COMMAND CONSOLE",
        "clear && printf '\\033[1;36m=== LANGGRAPH MULTI-AGENT CONTROL DECK ===\\033[0m\\n'"
        " && printf '  make pitch     -> offline cached mode\\n'"
        " && printf '  make up        -> live GEE + ASF mode\\n'"
        " && printf '  make test-dag  -> run the agent graph from the CLI\\n\\n'",
    ),
}

STYLE = {
    "pane-border-status": "top",
    "pane-border-format": " #[fg=#89dceb,bold]#[bg=#181825] #{pane_index}: #{pane_title} #[default] ",
    "pane-border-style": "fg=#313244",
    "pane-active-border-style": "fg=#89b4fa,bold",
    "status-style": "bg=#11111b,fg=#cdd6f4",
    "status-left": "#[bg=#89b4fa,fg=#11111b,bold] SPACE APPS 2026 #[bg=#181825,fg=#89dceb] DANCING WITH THE SARS ",
    "status-right": "#[fg=#a6e3a1]Valle de Aburrá / Medellín #[fg=#fab387]| %H:%M:%S ",
}


def tmux(*args: str, check: bool = True) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(["tmux", *args], check=check)


def attach() -> None:
    os.execvp("tmux", ["tmux", "attach-session", "-t", SESSION])


def main() -> int:
    if shutil.which("tmux") is None:
        print("tmux is not installed", file=sys.stderr)
        return 1
    os.chdir(PROJECT_ROOT)
    if tmux("has-session", "-t", SESSION, check=False).returncode == 0:
        print(f"Attaching to existing Mission Control session: {SESSION}")
        attach()

    root = str(PROJECT_ROOT)
    tmux("new-session", "-d", "-s", SESSION, "-n", "mission-control", "-c", root)
    for option, value in STYLE.items():
        tmux("set-option", "-t", SESSION, option, value)
    # Four quadrants; afterwards 0 = top-left, 1 = bottom-left, 2 = top-right, 3 = bottom-right.
    tmux("split-window", "-h", "-p", "50", "-t", f"{WINDOW}.0", "-c", root)
    tmux("split-window", "-v", "-p", "50", "-t", f"{WINDOW}.0", "-c", root)
    tmux("split-window", "-v", "-p", "50", "-t", f"{WINDOW}.1", "-c", root)
    for pane, (title, command) in PANES.items():
        tmux("select-pane", "-t", f"{WINDOW}.{pane}", "-T", title)
        tmux("send-keys", "-t", f"{WINDOW}.{pane}", command, "C-m")
    tmux("select-pane", "-t", f"{WINDOW}.3")

    if shutil.which("open"):  # open the mission-control UI on macOS
        threading.Timer(
            1.0, lambda: subprocess.run(["open", "http://localhost:8000"], check=False)
        ).start()
        time.sleep(1.2)
    attach()
    return 0


if __name__ == "__main__":
    sys.exit(main())
