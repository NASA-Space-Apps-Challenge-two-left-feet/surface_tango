"""Config loader (plan 01-02, CFG-01): one loader, no defaults, no hardcoded thresholds or AOIs.

The YAML written in these tests is configuration, not data: hand-written files with values
chosen to exercise each rule.
"""

import io
import shutil
import subprocess
import sys
import tokenize
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from bailasar.config import (  # noqa: E402
    Config,
    ConfigError,
    clear_cache,
    get_config,
    git_blob_hash,
    load_config,
)

PREREG = """\
status: {status}
quake:
  pairs: {{reference_R: {r}, coevent_C: {c}, control_K: {k}}}
  k_rule: {{fraction: 0.10, minimum: 5}}
  ranking: {{access_weight: 0.25}}
flood:
  open_water_abs_hh_db: -18.0
  hand_max_m: 18
labels: {{uncalibrated: [open_water_abs_hh_db, hand_max_m]}}
"""

OPS = """\
preregistered: config/preregistered.yaml
aois:
  1_aburra_medellin_bello: [-75.63, 6.22, -75.50, 6.38]
  2_eje_cafetero_quake: null
mcp:
  transport: sse
  ports: {nisar_asf: 8001, gee_fusion: 8002}
breaker_budgets_s:
  default: 1.8
  search_granules: 2.4
features:
  mathlab_corrections: false
"""


def _write(tmp_path, prereg=None, ops=OPS, **pairs):
    fields = {"status": "draft", "r": "null", "c": "null", "k": "null", **pairs}
    directory = tmp_path / "config"
    directory.mkdir()
    (directory / "preregistered.yaml").write_text(prereg or PREREG.format(**fields), "utf-8")
    (directory / "bailasar.yaml").write_text(ops, "utf-8")
    return directory


@pytest.fixture(autouse=True)
def _fresh_cache():
    clear_cache()
    yield
    clear_cache()


# --- The repository's own files -------------------------------------------------------------


def test_repository_config_loads():
    cfg = get_config()
    assert isinstance(cfg, Config)
    assert cfg.status in ("draft", "frozen")
    assert cfg.prereg("flood.open_water_abs_hh_db") == -18.0
    assert cfg.ops("mcp.transport") == "sse"


def test_repository_hash_matches_git_hash_object():
    git = shutil.which("git")
    if git is None:
        pytest.skip("git not on PATH")
    path = ROOT / "config/preregistered.yaml"
    expected = subprocess.run(
        [git, "hash-object", str(path)], capture_output=True, text=True, check=True, cwd=ROOT
    ).stdout.strip()
    assert get_config().preregistered_hash == expected


# --- Known answers --------------------------------------------------------------------------


def test_git_blob_hash_known_answers():
    # git itself is the oracle; the 40-hex answers are not written here (detect-secrets flags them)
    for blob in (b"", b"hello\n"):
        expected = (
            subprocess.run(
                ["git", "hash-object", "--stdin"], input=blob, capture_output=True, check=True
            )
            .stdout.decode()
            .strip()
        )
        assert git_blob_hash(blob) == expected
    assert git_blob_hash(b"hello\r\n") == git_blob_hash(b"hello\n")


# --- Lookups never invent a value -----------------------------------------------------------


def test_lookups(tmp_path):
    cfg = load_config(_write(tmp_path))
    assert cfg.prereg("quake.k_rule.minimum") == 5
    assert cfg.prereg("quake.ranking.access_weight") == 0.25
    assert cfg.ops("mcp.ports.gee_fusion") == 8002
    assert cfg.aoi_names() == ("1_aburra_medellin_bello", "2_eje_cafetero_quake")
    assert cfg.aoi_bbox("1_aburra_medellin_bello") == (-75.63, 6.22, -75.50, 6.38)


def test_missing_key_raises(tmp_path):
    cfg = load_config(_write(tmp_path))
    with pytest.raises(ConfigError, match="no key 'flood.not_a_threshold'"):
        cfg.prereg("flood.not_a_threshold")
    with pytest.raises(ConfigError, match="no key 'mcp.ports.nope'"):
        cfg.ops("mcp.ports.nope")


def test_null_value_raises_unless_allowed(tmp_path):
    cfg = load_config(_write(tmp_path))
    with pytest.raises(ConfigError, match="is null"):
        cfg.prereg("quake.pairs.coevent_C")
    assert cfg.prereg("quake.pairs.coevent_C", allow_null=True) is None


def test_aoi_not_set_at_gate_raises(tmp_path):
    cfg = load_config(_write(tmp_path))
    with pytest.raises(ConfigError, match="no bbox yet"):
        cfg.aoi_bbox("2_eje_cafetero_quake")
    with pytest.raises(ConfigError, match="unknown AOI"):
        cfg.aoi_bbox("3_somewhere_else")


def test_breaker_budget_per_tool_then_default(tmp_path):
    cfg = load_config(_write(tmp_path))
    assert cfg.breaker_budget_s("search_granules") == 2.4
    assert cfg.breaker_budget_s("not_measured_yet") == 1.8


def test_feature_flags(tmp_path):
    cfg = load_config(_write(tmp_path))
    assert cfg.feature("mathlab_corrections") is False
    with pytest.raises(ConfigError, match="unknown feature flag"):
        cfg.feature("not_a_flag")


def test_config_is_read_only(tmp_path):
    cfg = load_config(_write(tmp_path))
    with pytest.raises(TypeError):
        cfg.preregistered["flood"]["hand_max_m"] = 24
    with pytest.raises(TypeError):
        cfg.operational["aois"]["new"] = [0, 0, 1, 1]
    assert isinstance(cfg.operational["aois"]["1_aburra_medellin_bello"], tuple)


def test_env_var_selects_config_dir(tmp_path, monkeypatch):
    directory = _write(tmp_path)
    monkeypatch.setenv("BAILASAR_CONFIG_DIR", str(directory))
    assert load_config().operational_path == directory.resolve() / "bailasar.yaml"


# --- Freeze and hash (CFG-02 builds on these) -----------------------------------------------


def test_draft_is_not_frozen(tmp_path):
    cfg = load_config(_write(tmp_path))
    assert not cfg.is_frozen
    with pytest.raises(ConfigError, match="not frozen"):
        cfg.require_frozen()


def test_frozen_with_nulls_is_rejected(tmp_path):
    with pytest.raises(ConfigError, match="frozen but these values are null"):
        load_config(_write(tmp_path, status="frozen", r="R1"))


def test_frozen_and_hash_checked(tmp_path):
    directory = _write(tmp_path, status="frozen", r="R1", c="C1", k="K1")
    cfg = load_config(directory)
    expected = git_blob_hash((directory / "preregistered.yaml").read_bytes())
    assert cfg.preregistered_hash == expected
    cfg.require_frozen(expected)
    with pytest.raises(ConfigError, match="frozen file was edited"):
        cfg.require_frozen("0" * 40)


# --- Validation at load ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("ops", "message"),
    [
        (OPS.replace("[-75.63, 6.22, -75.50, 6.38]", "[-75.50, 6.22, -75.63, 6.38]"), "valid"),
        (OPS.replace("[-75.63, 6.22, -75.50, 6.38]", "[-75.63, 6.22, -75.50]"), "must be null"),
        (OPS.replace("default: 1.8", "default: 0"), "positive number"),
        (OPS.replace("  default: 1.8\n", ""), "explicit 'default'"),
        (OPS.replace("mathlab_corrections: false", "mathlab_corrections: maybe"), "true/false"),
        (OPS + "flood: {hand_max_m: 18}\n", "belong in the frozen file"),
        (OPS.replace("features:\n  mathlab_corrections: false\n", ""), "missing sections"),
    ],
)
def test_invalid_operational_rejected(tmp_path, ops, message):
    with pytest.raises(ConfigError, match=message):
        load_config(_write(tmp_path, ops=ops))


@pytest.mark.parametrize(
    ("edit", "message"),
    [
        (lambda t: t.replace("status: draft", "status: final"), "status must be one of"),
        (lambda t: t + "breaker_budgets_s: {default: 1.8}\n", "belong in bailasar.yaml"),
        (lambda t: t.replace("[open_water_abs_hh_db", "[open_water_db"), "unknown parameters"),
        (lambda t: t.replace("flood:", "flooding:"), "missing sections"),
    ],
)
def test_invalid_preregistered_rejected(tmp_path, edit, message):
    text = edit(PREREG.format(status="draft", r="null", c="null", k="null"))
    with pytest.raises(ConfigError, match=message):
        load_config(_write(tmp_path, prereg=text))


def test_missing_file_raises(tmp_path):
    directory = _write(tmp_path)
    (directory / "preregistered.yaml").unlink()
    with pytest.raises(ConfigError, match="not found"):
        load_config(directory)


# --- No hardcoded thresholds or AOIs outside config/ (CFG-01) ---------------------------------

DATA_PATHS = ["scripts", "gee_math", "mcp_servers", "agents", "src", "app.py"]

# Files that still carry config literals, each fixed by the plan that owns the file.
# Remove an entry when that plan wires the file to bailasar.config. Never add a new one.
PENDING_WIRING = {
    "gee_math/flood_polarimetric_math.py": "01-04 (EstebanOchoaedos)",
    "gee_math/earthquake_dpm_math.py": "quake modeling lane (LEONOB2014): AOI bbox hardcoded",
}


def _distinctive_values():
    """Values specific enough that a literal copy in code is a hardcoded config value, mapped to
    whether the config writes them as integers: flood thresholds with |v| >= 1 and every AOI
    coordinate. Generic counts and fractions (5, 20, 0.10, 0.25) are left out."""
    cfg = get_config()
    flood = dict(cfg.preregistered["flood"])
    flood.pop("sensitivity", None)
    values = {}
    for raw in _raw_numbers(flood):
        if abs(raw) >= 1:
            values[float(raw)] = isinstance(raw, int)
    for bbox in cfg.operational["aois"].values():
        for raw in bbox or ():
            values[float(raw)] = isinstance(raw, int)
    return values


def _raw_numbers(tree):
    if isinstance(tree, dict):
        for v in tree.values():
            yield from _raw_numbers(v)
    elif isinstance(tree, list | tuple):
        for v in tree:
            yield from _raw_numbers(v)
    elif isinstance(tree, int | float) and not isinstance(tree, bool):
        yield tree


def _literals(path):
    """(line, value, is_integer_literal) for every numeric literal, with a leading minus."""
    tokens = list(tokenize.generate_tokens(io.StringIO(path.read_text("utf-8")).readline))
    for i, tok in enumerate(tokens):
        if tok.type != tokenize.NUMBER:
            continue
        try:
            value = float(tok.string)
        except ValueError:
            continue
        if i and tokens[i - 1].type == tokenize.OP and tokens[i - 1].string == "-":
            value = -value
        is_int = not any(c in tok.string.lower() for c in ".e")
        yield tok.start[0], value, is_int


def _offending_files():
    values = _distinctive_values()
    found = {}
    for p in DATA_PATHS:
        base = ROOT / p
        files = [base] if base.is_file() else sorted(base.rglob("*.py")) if base.is_dir() else []
        for f in files:
            if f == ROOT / "src/bailasar/config.py":
                continue
            # A float threshold (-5.5, 3.0) only matches a float literal, so `ndim == 3` does not;
            # an integer one (hand 18 m) matches either spelling.
            hits = [
                f"{line}:{v:g}"
                for line, v, is_int in _literals(f)
                if v in values and (values[v] or not is_int)
            ]
            if hits:
                found[f.relative_to(ROOT).as_posix()] = hits
    return found


def test_no_new_hardcoded_thresholds_or_aois():
    unexpected = {f: h for f, h in _offending_files().items() if f not in PENDING_WIRING}
    assert unexpected == {}, f"read these from bailasar.config instead: {unexpected}"


# --- Quake control pairs follow the design date rule (#131) ---------------------------------

_ACQ = __import__("re").compile(r"_SH_(\d{8})T\d+_\d{8}T\d+_(\d{8})T")


def _acquisitions(granule_id):
    match = _ACQ.search(granule_id)
    assert match, f"cannot read acquisition dates from {granule_id}"
    return match.group(1), match.group(2)


def test_control_pairs_share_no_date_with_r_or_c_and_are_labelled():
    """Design doc, Data layer: K shares no acquisition with R or C. A pre-event K ends on or
    before R starts; a post-event K (the design's fallback) starts after the event date."""
    import json

    facts = json.loads((ROOT / "validation/event_facts.json").read_text("utf-8"))
    event = facts["quake_2026_08_10"]["date"].replace("-", "")
    for triplet in get_config().prereg("quake.pairs"):
        r, c, k = (_acquisitions(triplet[key]) for key in ("reference_R", "coevent_C", "control_K"))
        track = triplet["track"]
        assert not set(k) & (set(r) | set(c)), f"track {track}: K shares a date with R or C"
        timing = triplet["control_K_timing"]
        if timing == "pre_event":
            assert k[1] < r[0], f"track {track}: pre-event K must end before R starts"
        else:
            assert timing == "post_event", f"track {track}: unknown control_K_timing {timing!r}"
            assert k[0] > event, f"track {track}: post-event K must start after the event"
