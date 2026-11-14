"""Repository rules that protect the evidence (AGENTS.md: Non-negotiables)."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_PATHS = ["scripts", "gee_math", "mcp_servers", "agents", "static", "app.py"]
SYNTHETIC = re.compile(r"synthesiz|simulat|np\.random|random\.(rand|normal|uniform|gauss)|nan=0\.0")


def _files():
    for p in DATA_PATHS:
        path = ROOT / p
        if path.is_file():
            yield path
        elif path.is_dir():
            yield from (f for f in path.rglob("*") if f.suffix in {".py", ".js", ".html"})


def test_no_synthetic_data_generators_in_data_paths():
    hits = [
        f"{f.relative_to(ROOT)}:{i}"
        for f in _files()
        for i, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1)
        if SYNTHETIC.search(line)
    ]
    assert hits == [], f"synthetic-data pattern found: {hits}"


def test_no_nasa_logo_badge():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "logo=nasa" not in readme


def test_preregistration_and_operational_config_are_separate():
    prereg = (ROOT / "config/preregistered.yaml").read_text(encoding="utf-8")
    ops = (ROOT / "config/bailasar.yaml").read_text(encoding="utf-8")
    assert "breaker_budgets_s" not in prereg
    assert "open_water_abs_hh_db" not in ops
