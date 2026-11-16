"""The regional cube page is not part of the observatory."""

from pathlib import Path

from fastapi.testclient import TestClient

import app as web

ROOT = Path(__file__).resolve().parents[1]


def test_regional_cube_page_is_gone():
    assert not (ROOT / "static/cube.html").exists()
    with TestClient(web.app) as client:
        assert client.get("/cube").status_code == 404
        assert client.get("/api/cube").status_code == 404
        assert client.get("/api/cube/mojana").status_code == 404
        home = client.get("/")
        assert home.status_code == 200
        assert 'href="/cube"' not in home.text
