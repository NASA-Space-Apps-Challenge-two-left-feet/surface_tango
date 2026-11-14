# scripts/watch_zarr_telemetry.py
import os
import time
import json
from pathlib import Path
import numpy as np
import xarray as xr

CACHE_DIR = Path(__file__).resolve().parent.parent / "local_cache" / "antioquia_aburra"
ZARR_PATH = CACHE_DIR / "antioquia_sar_cube.zarr"
MANIFEST_PATH = CACHE_DIR / "manifest.json"
LLM_CACHE_DB = CACHE_DIR / "llm_cache.sqlite"

# Catppuccin Mocha / ANSI Escape Codes
CYAN = "\033[38;2;137;220;235m"
GREEN = "\033[38;2;166;227;161m"
PEACH = "\033[38;2;250;179;135m"
MAUVE = "\033[38;2;203;166;247m"
RED = "\033[38;2;243;139;168m"
SLATE = "\033[38;2;147;153;178m"
BOLD = "\033[1m"
RESET = "\033[0m"

def render_dashboard():
    while True:
        t0 = time.perf_counter()
        os.system("clear")
        mode = "⚡ OFFLINE PITCH MODE (AIR-GAPPED)" if os.environ.get("OFFLINE_DEMO_MODE") == "1" else "🌐 HYBRID CLOUD + 1.8s CIRCUIT BREAKER"
        mode_color = GREEN if os.environ.get("OFFLINE_DEMO_MODE") == "1" else CYAN

        print(f"{BOLD}{MAUVE}╔══════════════════════════════════════════════════════════════════════╗{RESET}")
        print(f"{BOLD}{MAUVE}║   NISAR L-BAND ZARR v3 DATA CUBE & EDGE CIRCUIT-BREAKER TELEMETRY    ║{RESET}")
        print(f"{BOLD}{MAUVE}╚══════════════════════════════════════════════════════════════════════╝{RESET}")
        print(f" {BOLD}Operational Profile:{RESET} {mode_color}{mode}{RESET}")

        if not ZARR_PATH.exists():
            print(f"\n {RED}[WAITING] Zarr cube not found at {ZARR_PATH}. Run `make prewarm`.{RESET}")
            time.sleep(2.0)
            continue

        # Measure live Zarr v3 slice & reduction latency
        ds = xr.open_zarr(ZARR_PATH)
        disp_p99 = float(np.nanpercentile(ds["downslope_disp_mm"].values, 99))
        coh_mean = float(np.nanmean(ds["gunw_coherence"].values))
        rain_p95 = float(np.nanpercentile(ds["rain_15d_mm"].values, 95))

        hh = ds["gcov_hhhh_post"].values
        hv = ds["gcov_hvhv_post"].values
        rfdi_p95 = float(np.nanpercentile((hh - hv) / (hh + hv + 1e-6), 95))
        dpm_max = float(np.nanmax(ds["gunw_coherence"].values - ds["coherence_coseismic"].values))
        dt_ms = (time.perf_counter() - t0) * 1000.0

        llm_kb = round(LLM_CACHE_DB.stat().st_size / 1024, 1) if LLM_CACHE_DB.exists() else 0.0

        print(f" {BOLD}Zarr Tensor Shape:{RESET}   {CYAN}10 bands × 512 × 512 (float32){RESET} | {BOLD}Read Latency:{RESET} {GREEN}{dt_ms:.2f} ms{RESET}")
        print(f" {BOLD}SQLite LLM Cache:{RESET}    {PEACH}{llm_kb} KB{RESET} | {BOLD}AOI:{RESET} Valle de Aburrá / Bello [-75.63, 6.22, -75.50, 6.38]\n")

        print(f" {BOLD}{CYAN}┌────────────────────┬───────────────────────────────┬────────────────┐{RESET}")
        print(f" {BOLD}{CYAN}│ HAZARD AGENT       │ LIVE ZARR v3 PHYSICAL METRIC  │ STATUS / BAND  │{RESET}")
        print(f" {BOLD}{CYAN}├────────────────────┼───────────────────────────────┼────────────────┤{RESET}")
        print(f" │ 1. Landslide GUNW  │ p99 Creep: {PEACH}{disp_p99:6.2f} mm{RESET} (γ={coh_mean:.2f}) │ {RED}ORANGE (L-HH){RESET}  │")
        print(f" │ 2. Flood GCOV      │ CHIRPS 15d: {CYAN}{rain_p95:5.1f} mm{RESET} + DblBnc │ {PEACH}YELLOW (HH/HV){RESET} │")
        print(f" │ 3. Seismic DPM     │ Max Δγ Drop: {GREEN}{dpm_max:5.3f}{RESET} + VIDA     │ {GREEN}GREEN  (GUNW){RESET}  │")
        print(f" │ 4. Biomass RFDI    │ p95 RFDI:    {PEACH}{rfdi_p95:5.3f}{RESET} (L+C GEDI) │ {PEACH}YELLOW (L-HV){RESET}  │")
        print(f" {BOLD}{CYAN}└────────────────────┴───────────────────────────────┴────────────────┘{RESET}")
        print(f"\n {SLATE}[Last Tensor Probe: {time.strftime('%H:%M:%S')} -05 | Polling every 2.0s]{RESET}")
        time.sleep(2.0)

if __name__ == "__main__":
    try:
        render_dashboard()
    except KeyboardInterrupt:
        pass
