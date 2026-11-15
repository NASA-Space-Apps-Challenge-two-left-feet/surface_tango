"""Wake-on-request front door for the judging-period demo VM.

The public URL points here (Cloud Run, scales to zero). A visit starts the VM if it is
stopped, shows a waiting page while it boots, and redirects to the web app on the VM
once it answers. The VM stops itself when idle (deploy/vm/idle_shutdown.py), so the
16 GB machine only bills while someone is using it.

Configuration comes from the environment (set at deploy time):
GCP_PROJECT_ID, VM_ZONE, VM_NAME, VM_PORT (8000), VM_PROBE_PATH.
"""

from __future__ import annotations

import html
import os
import urllib.error
import urllib.request

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

PROJECT = os.environ.get("GCP_PROJECT_ID", "")
ZONE = os.environ.get("VM_ZONE", "us-central1-a")
INSTANCE = os.environ.get("VM_NAME", "surface-tango-pitch-e2e")
PORT = int(os.environ.get("VM_PORT", "8000"))
# A static asset, so the idle check on the VM can tell probes from real visits.
PROBE_PATH = os.environ.get("VM_PROBE_PATH", "/assets/mission-control.css")
COMPUTE = "https://compute.googleapis.com/compute/v1"

app = FastAPI(title="surface-tango-waker", docs_url=None, redoc_url=None)

# Instance states (Compute Engine API) and what the front door does in each.
START_STATES = {"TERMINATED", "STOPPED"}
RESUME_STATES = {"SUSPENDED"}


def decide(status: str, ready: bool) -> str:
    """Return the action for an instance status: redirect, start, resume or wait."""
    if status == "RUNNING" and ready:
        return "redirect"
    if status in START_STATES:
        return "start"
    if status in RESUME_STATES:
        return "resume"
    return "wait"  # PROVISIONING, STAGING, booting RUNNING, STOPPING, SUSPENDING, REPAIRING


def target_url(ip: str, path: str = "/", query: str = "") -> str:
    """The web app URL on the VM, keeping the visitor's path and query."""
    url = f"http://{ip}:{PORT}{path if path.startswith('/') else '/' + path}"
    return f"{url}?{query}" if query else url


def _session():
    import google.auth
    from google.auth.transport.requests import AuthorizedSession

    credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/compute"])
    return AuthorizedSession(credentials)


def _instance_url() -> str:
    return f"{COMPUTE}/projects/{PROJECT}/zones/{ZONE}/instances/{INSTANCE}"


def instance_state() -> tuple[str, str | None]:
    """Return (status, external IP) of the VM."""
    response = _session().get(_instance_url(), timeout=10)
    response.raise_for_status()
    body = response.json()
    ip = None
    for interface in body.get("networkInterfaces", []):
        for config in interface.get("accessConfigs", []):
            ip = ip or config.get("natIP")
    return body.get("status", "UNKNOWN"), ip


def instance_action(verb: str) -> None:
    """POST start or resume; a second call while it is already starting is harmless."""
    response = _session().post(f"{_instance_url()}/{verb}", timeout=10)
    if response.status_code >= 400 and response.status_code != 409:
        response.raise_for_status()


def app_ready(ip: str | None) -> bool:
    if not ip:
        return False
    try:
        with urllib.request.urlopen(target_url(ip, PROBE_PATH), timeout=2) as response:
            return response.status == 200
    except (urllib.error.URLError, OSError, ValueError):
        return False


def advance() -> tuple[str, str, str | None]:
    """Look at the VM, start or resume it if needed, and return (action, status, ip)."""
    status, ip = instance_state()
    action = decide(status, app_ready(ip) if status == "RUNNING" else False)
    if action in {"start", "resume"}:
        instance_action(action)
    return action, status, ip


WAITING_PAGE = """<!doctype html>
<html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Surface Tango</title>
<style>
  :root {{ --blue:#1B3FD6; --vermilion:#F04A23; --ink:#121212; --paper:#FFFFFF; --grey:#5A5A5A; }}
  body {{ margin:0; min-height:100vh; display:flex; flex-direction:column; align-items:center;
    justify-content:center; gap:20px; background:var(--ink); color:var(--paper);
    font-family:'Jost','Poppins',system-ui,sans-serif; padding:0 16px; text-align:center; }}
  h1 {{ font-weight:600; letter-spacing:.18em; text-transform:uppercase; font-size:15px; margin:0; }}
  p {{ font-family:'Libre Caslon Text',Georgia,serif; font-size:14px; max-width:34em; margin:0; color:#d4d4d4; }}
  .sub {{ color:var(--vermilion); font-size:12px; letter-spacing:.08em; }}
  svg {{ overflow:visible; width:min(330px,80vw); height:auto; }}
  .f {{ transform-box:fill-box; transform-origin:center; opacity:0; animation:step 3.2s linear infinite; }}
  .b {{ fill:var(--paper); }} .v {{ fill:var(--vermilion); }}
  .s1 {{ animation-delay:0s; }} .s2 {{ animation-delay:.8s; }} .s3 {{ animation-delay:1.6s; }}
  .s4 {{ animation-delay:2s; }} .s5 {{ animation-delay:2.4s; }}
  @keyframes step {{ 0% {{ opacity:0; transform:scale(.82); }} 5% {{ opacity:1; transform:scale(1); }}
    28% {{ opacity:.4; }} 88% {{ opacity:.4; }} 100% {{ opacity:0; }} }}
  @media (prefers-reduced-motion: reduce) {{ .f {{ animation:none; opacity:1; }} }}
</style></head>
<body>
  <svg viewBox="0 0 210 104" aria-hidden="true"><defs>
    <g id="lfoot"><ellipse cx="0" cy="-5" rx="6.5" ry="12"/><circle cx="1.5" cy="10" r="5.5"/></g></defs>
    <g transform="translate(26 80) rotate(6)"><use href="#lfoot" class="f v s1"/></g>
    <g transform="translate(74 66) rotate(10)"><use href="#lfoot" class="f b s2"/></g>
    <g transform="translate(112 58) rotate(4)"><use href="#lfoot" class="f v s3"/></g>
    <g transform="translate(142 46) rotate(22)"><use href="#lfoot" class="f b s4"/></g>
    <g transform="translate(160 56) rotate(-6)"><use href="#lfoot" class="f v s5"/></g>
  </svg>
  <h1>Surface Tango</h1>
  <p>Encendiendo el observatorio. Tarda uno o dos minutos; esta página se abrirá sola.<br>
     Starting the observatory. It takes a minute or two; this page will open by itself.</p>
  <div class="sub" id="state">{status}</div>
<script>
  const next = {next_path};
  async function poll() {{
    try {{
      const r = await fetch('/status', {{cache: 'no-store'}});
      const s = await r.json();
      document.getElementById('state').textContent = s.status;
      if (s.ready) {{ location.replace('/go' + next); return; }}
    }} catch (e) {{}}
    setTimeout(poll, 4000);
  }}
  setTimeout(poll, 3000);
</script>
</body></html>
"""


def waiting_page(status: str, next_path: str) -> HTMLResponse:
    import json

    body = WAITING_PAGE.format(status=html.escape(status), next_path=json.dumps(next_path))
    return HTMLResponse(body, headers={"Cache-Control": "no-store"})


@app.get("/status")
def status() -> JSONResponse:
    action, state, _ = advance()
    return JSONResponse(
        {"status": state, "ready": action == "redirect"}, headers={"Cache-Control": "no-store"}
    )


@app.get("/{path:path}")
def front_door(path: str, request: Request):
    # /go/<path> is the waiting page's hand-off; anything else is a first visit.
    visit = path[3:] if path == "go" or path.startswith("go/") else path
    action, state, ip = advance()
    query = request.url.query
    if action == "redirect" and ip:
        return RedirectResponse(target_url(ip, "/" + visit, query), status_code=302)
    next_path = "/" + visit + (f"?{query}" if query else "")
    return waiting_page(state, next_path)
