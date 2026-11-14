# Append to Makefile
hud: ## Launch the 4-pane tmux Mission Control HUD + open http://localhost:8000
	chmod +x scripts/tmux_mission_control.sh
	./scripts/tmux_mission_control.sh

demo: pitch hud ## One-command Judging Setup: Boot Pitch Mode (<1.2s Zarr) + Open 4-Pane tmux HUD & Browser
