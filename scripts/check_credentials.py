"""Hour-0 credential check: one read-only call per service, never prints a secret value.

    uv run python scripts/check_credentials.py                 # all services
    uv run python scripts/check_credentials.py --only gee,gcs  # a subset

Exit code 0 when every checked service passes, 1 otherwise. Output lists which variables are
set (never their values) and the result of one read-only call per service.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

SERVICES = {
    "earthdata": ["EARTHDATA_USERNAME", "EARTHDATA_PASSWORD", "EARTHDATA_TOKEN"],
    "gee": ["GCP_PROJECT_ID", "GEE_SERVICE_ACCOUNT", "GOOGLE_APPLICATION_CREDENTIALS"],
    "gcs": ["GCP_PROJECT_ID", "GCS_BUCKET", "GOOGLE_APPLICATION_CREDENTIALS"],
    "llm": ["ANTHROPIC_API_KEY"],
}


def load_env(path: Path) -> None:
    """Load KEY=VALUE lines from .env into os.environ without overriding existing values."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


def presence(keys: list[str]) -> str:
    return ", ".join(f"{k}={'set' if os.environ.get(k) else 'empty'}" for k in keys)


def check_earthdata() -> str:
    import earthaccess

    auth = earthaccess.login(strategy="environment", persist=False)
    if not getattr(auth, "authenticated", False):
        raise RuntimeError("earthaccess login did not authenticate")
    return "earthaccess login ok"


def check_gee() -> str:
    import ee

    project = os.environ["GCP_PROJECT_ID"]
    ee.Initialize(project=project)
    ee.Number(1).getInfo()  # read-only round trip
    return "ee.Initialize(project=<set>) and a read-only getInfo ok"


def check_gcs() -> str:
    from google.cloud import storage

    client = storage.Client(project=os.environ["GCP_PROJECT_ID"])
    bucket = client.bucket(os.environ["GCS_BUCKET"])
    next(iter(bucket.list_blobs(max_results=1)), None)  # read-only list
    return "bucket list (max 1 object) ok"


def check_llm() -> str:
    import anthropic

    client = anthropic.Anthropic()
    client.models.list(limit=1)  # read-only, no tokens generated
    return "models.list ok"


CHECKS = {"earthdata": check_earthdata, "gee": check_gee, "gcs": check_gcs, "llm": check_llm}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--only", default=",".join(CHECKS), help="comma list: " + ",".join(CHECKS))
    args = parser.parse_args()
    load_env(ROOT / ".env")

    failed = 0
    for name in [s.strip() for s in args.only.split(",") if s.strip()]:
        if name not in CHECKS:
            print(f"[skip] {name}: unknown service")
            continue
        print(f"[{name}] {presence(SERVICES[name])}")
        try:
            print(f"  PASS {CHECKS[name]()}")
        except Exception as exc:  # report the class only: messages can echo credentials
            failed += 1
            print(f"  FAIL {type(exc).__name__}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
