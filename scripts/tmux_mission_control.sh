#!/usr/bin/env bash
# scripts/tmux_mission_control.sh
set -euo pipefail

SESSION="sars-hud"
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

# If session already exists, attach immediately
if tmux has-session -t "$SESSION" 2>/dev/null; then
  echo "⚡ Attaching to existing Mission Control session: $SESSION"
  exec tmux attach-session -t "$SESSION"
fi

echo "🚀 Launching NISAR 'Dancing with the SARs' 4-Pane Telemetry HUD..."

# 1. Create detached session with Pane 0 (Top-Left: FastMCP Servers Telemetry)
tmux new-session -d -s "$SESSION" -n "mission-control" -c "$PROJECT_ROOT"

# Configure visible pane titles & Catppuccin-friendly border styling
tmux set-option -t "$SESSION" pane-border-status top
tmux set-option -t "$SESSION" pane-border-format " #[fg=#89dceb,bold]#[bg=#181825] #{pane_index}: #{pane_title} #[default] "
tmux set-option -t "$SESSION" pane-border-style "fg=#313244"
tmux set-option -t "$SESSION" pane-active-border-style "fg=#89b4fa,bold"
tmux set-option -t "$SESSION" status-style "bg=#11111b,fg=#cdd6f4"
tmux set-option -t "$SESSION" status-left "#[bg=#89b4fa,fg=#11111b,bold] NASA SPACE APPS 2026 #[bg=#181825,fg=#89dceb] DANCING WITH THE SARS "
tmux set-option -t "$SESSION" status-right "#[fg=#a6e3a1]Valle de Aburrá / Medellín #[fg=#fab387]| %H:%M:%S "

# 2. Split into 4 Equal Quadrants
# Split horizontally: Left (Pane 0) and Right (Pane 1)
tmux split-window -h -p 50 -t "$SESSION:mission-control.0" -c "$PROJECT_ROOT"
# Split Left vertically: Top-Left (Pane 0) and Bottom-Left (Pane 2)
tmux split-window -v -p 50 -t "$SESSION:mission-control.0" -c "$PROJECT_ROOT"
# Split Right vertically: Top-Right (Pane 1) and Bottom-Right (Pane 3)
tmux split-window -v -p 50 -t "$SESSION:mission-control.1" -c "$PROJECT_ROOT"

# Note: After splits, tmux pane indices are:
# 0 = Top-Left, 1 = Bottom-Left, 2 = Top-Right, 3 = Bottom-Right

# --- PANE 0 (Top-Left): Live FastMCP Tool Calls (Ports 8001 & 8002) ---
tmux select-pane -t "$SESSION:mission-control.0" -T "FASTMCP SERVERS (8001: NISAR S3/COG | 8002: GEE MATH ENGINE)"
tmux send-keys -t "$SESSION:mission-control.0" \
  "docker compose logs -f --tail=40 mcp-nisar-asf mcp-gee-fusion 2>/dev/null || echo 'Run [make up] or [make pitch] in Pane 3 to stream MCP tool calls...'" C-m

# --- PANE 2 (Top-Right): Live Zarr v3 Tensor & Circuit-Breaker Latency Monitor ---
tmux select-pane -t "$SESSION:mission-control.2" -T "ZARR v3 TENSOR LATENCY & CIRCUIT-BREAKER TELEMETRY"
tmux send-keys -t "$SESSION:mission-control.2" \
  "uv run python scripts/watch_zarr_telemetry.py" C-m

# --- PANE 1 (Bottom-Left): XYZ Tile Requests & SSE Stream Logs (Port 8000) ---
tmux select-pane -t "$SESSION:mission-control.1" -T "XYZ RASTER TILE STREAM & FASTAPI SSE EVENTS (PORT 8000)"
tmux send-keys -t "$SESSION:mission-control.1" \
  "docker compose logs -f --tail=40 sars-web-orchestrator | grep --line-buffered -E 'local-tiles|stream-hazards|agent_update|CIRCUIT-BREAKER|GET|POST'" C-m

# --- PANE 3 (Bottom-Right): LangGraph Multi-Agent Orchestrator & Interactive Trigger Console ---
tmux select-pane -t "$SESSION:mission-control.3" -T "LANGGRAPH MULTI-AGENT DAG & INTERACTIVE COMMAND CONSOLE"
tmux send-keys -t "$SESSION:mission-control.3" \
  "clear && printf '\033[1;36m=== LANGGRAPH MULTI-AGENT CONTROL DECK ===\033[0m\n' && \
   printf '  • \033[1;32mmake pitch\033[0m     -> Switch to <1.2s Offline Zarr Pitch Mode\n' && \
   printf '  • \033[1;32mmake up\033[0m        -> Switch to Live GEE + NASA S3 Cloud Mode\n' && \
   printf '  • \033[1;32mmake test-dag\033[0m  -> Trigger 4-Agent + Synthesis CLI Run\n\n'" C-m

# Focus on the Interactive Command Console (Bottom-Right)
tmux select-pane -t "$SESSION:mission-control.3"

# Open the 3-Panel MapLibre/Deck.gl UI automatically on macOS
if command -v open >/dev/null 2>&1; then
  (sleep 1 && open "http://localhost:8000") &
fi

exec tmux attach-session -t "$SESSION"
