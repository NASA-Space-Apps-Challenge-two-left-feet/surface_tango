"""One way to start Earth Engine: the application-default login and the shared project.

Earth Engine's own saved login (`earthengine authenticate`) can belong to a different Google
account than the gcloud application-default login, and `ee.Initialize()` prefers it. Passing
ADC credentials explicitly makes every component use the same identity, the one that IAM grants
target. The project comes only from `GCP_PROJECT_ID`; there is no invented default.
"""

from __future__ import annotations

import os

import ee
import google.auth

EE_SCOPES = [
    "https://www.googleapis.com/auth/earthengine",
    "https://www.googleapis.com/auth/cloud-platform",
]
HIGH_VOLUME_URL = "https://earthengine-highvolume.googleapis.com"


def init_ee(high_volume: bool = True) -> str:
    """Initialize Earth Engine with ADC on GCP_PROJECT_ID; returns the project used."""
    project = os.environ.get("GCP_PROJECT_ID")
    if not project:
        raise RuntimeError("GCP_PROJECT_ID is not set (see .env.example)")
    credentials, _ = google.auth.default(scopes=EE_SCOPES)
    kwargs = {"credentials": credentials, "project": project}
    if high_volume:
        kwargs["opt_url"] = HIGH_VOLUME_URL
    ee.Initialize(**kwargs)
    return project
