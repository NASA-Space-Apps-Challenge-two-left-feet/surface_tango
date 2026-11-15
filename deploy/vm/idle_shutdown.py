"""Power the demo VM off after a quiet spell, so it only bills while someone uses it.

Runs on the VM every 5 minutes (surface-tango-idle.timer) as root with the system
python3; standard library only. The wake-on-request front door (deploy/waker/main.py)
starts the VM again on the next visit.

A visit is any access-log line of the web container for `/` or `/api/...`. The front
door's readiness probe fetches a static asset, so probes never count as visits.
"""

from __future__ import annotations

import re
import subprocess
import sys

CONTAINER = "sars-web-orchestrator"
IDLE_MINUTES = 45  # no visits for this long -> power off
BOOT_GRACE_MINUTES = 20  # never power off this soon after boot (a visitor is waiting)
VISIT = re.compile(r'"(GET|POST|HEAD) (/|/api/\S*)(\?\S*)? HTTP/')


def count_visits(log_text: str) -> int:
    """Number of real visits (page or API requests) in uvicorn access-log text."""
    return sum(1 for line in log_text.splitlines() if VISIT.search(line))


def should_stop(uptime_s: float, log_text: str, container_running: bool) -> bool:
    """Stop only after the boot grace, and only when the web app saw no visit."""
    if uptime_s < BOOT_GRACE_MINUTES * 60:
        return False
    if not container_running:
        return False  # the stack is broken or restarting: leave it up for a human to look
    return count_visits(log_text) == 0


def uptime_seconds() -> float:
    with open("/proc/uptime", encoding="ascii") as handle:
        return float(handle.read().split()[0])


def main() -> int:
    running = subprocess.run(
        ["docker", "inspect", "-f", "{{.State.Running}}", CONTAINER],
        capture_output=True,
        text=True,
        check=False,
    )
    container_running = running.returncode == 0 and running.stdout.strip() == "true"
    logs = subprocess.run(
        ["docker", "logs", "--since", f"{IDLE_MINUTES}m", CONTAINER],
        capture_output=True,
        text=True,
        check=False,
    )
    text = logs.stdout + logs.stderr
    uptime = uptime_seconds()
    stop = should_stop(uptime, text, container_running)
    print(
        f"uptime={uptime:.0f}s visits_last_{IDLE_MINUTES}m={count_visits(text)} "
        f"container_running={container_running} stop={stop}",
        flush=True,
    )
    if stop:
        subprocess.run(["shutdown", "-h", "now", "surface-tango idle"], check=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
