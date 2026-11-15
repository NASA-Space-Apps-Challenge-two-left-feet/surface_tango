"""The one loader for `config/preregistered.yaml` and `config/bailasar.yaml` (CFG-01; D5, D13).

Every component reads thresholds, AOIs, pre-registered parameters, breaker budgets and feature
flags through this module, so no value is hardcoded anywhere else.

- `preregistered.yaml` is the frozen pre-registration. Its `git hash-object` is recorded in
  `validation/README.md` (CFG-02). Once `status: frozen`, every value must be set (no nulls).
- `bailasar.yaml` holds operational settings that may change at any time.

Nothing here supplies a default. A missing key, an unknown AOI or an AOI whose bbox was not set
at the hour-2 gate raises `ConfigError`, so a gap can never turn into a made-up value.
"""

from __future__ import annotations

import hashlib
import math
import os
from collections.abc import Mapping
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from types import MappingProxyType
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_DIR = REPO_ROOT / "config"
CONFIG_DIR_ENV = "BAILASAR_CONFIG_DIR"
OPERATIONAL_FILENAME = "bailasar.yaml"

PREREG_STATUSES = ("draft", "frozen")
PREREG_REQUIRED_SECTIONS = ("status", "quake", "flood")
OPERATIONAL_REQUIRED_SECTIONS = ("preregistered", "aois", "mcp", "breaker_budgets_s", "features")
# Keys that belong to exactly one file (AGENTS.md: frozen parameters live only in preregistered).
PREREG_ONLY_KEYS = ("status", "quake", "flood", "labels")

BBox = tuple[float, float, float, float]


class ConfigError(ValueError):
    """The configuration is missing, malformed or not yet set where a value is required."""


def git_blob_hash(data: bytes) -> str:
    """Return what `git hash-object` prints for a file with these bytes.

    CRLF is normalized to LF first, matching git's clean filter on a Windows checkout
    with `core.autocrlf=true`, so the hash agrees with the committed blob.
    """
    data = data.replace(b"\r\n", b"\n")
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def _deep_freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({k: _deep_freeze(v) for k, v in value.items()})
    if isinstance(value, list | tuple):
        return tuple(_deep_freeze(v) for v in value)
    return value


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ConfigError(f"config file not found: {path}")
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ConfigError(f"{path}: invalid YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise ConfigError(f"{path}: top level must be a mapping")
    return data


def _null_leaves(value: Any, prefix: str = "") -> list[str]:
    if isinstance(value, Mapping):
        return [leaf for k, v in value.items() for leaf in _null_leaves(v, f"{prefix}{k}.")]
    if isinstance(value, list | tuple):
        return [leaf for i, v in enumerate(value) for leaf in _null_leaves(v, f"{prefix}{i}.")]
    return [prefix.rstrip(".")] if value is None else []


def _lookup(tree: Mapping[str, Any], dotted: str, source: Path, allow_null: bool) -> Any:
    node: Any = tree
    walked: list[str] = []
    for part in dotted.split("."):
        walked.append(part)
        if not isinstance(node, Mapping) or part not in node:
            raise ConfigError(f"{source}: no key {'.'.join(walked)!r}")
        node = node[part]
    if node is None and not allow_null:
        raise ConfigError(f"{source}: {dotted!r} is null (not set yet)")
    return node


def _validate_bbox(name: str, bbox: Any, source: Path) -> None:
    if bbox is None:
        return
    if (
        not isinstance(bbox, list)
        or len(bbox) != 4
        or not all(isinstance(v, int | float) and not isinstance(v, bool) for v in bbox)
        or not all(math.isfinite(v) for v in bbox)
    ):
        raise ConfigError(
            f"{source}: aois.{name} must be null or [W, S, E, N] numbers, got {bbox!r}"
        )
    west, south, east, north = bbox
    if not (-180 <= west < east <= 180 and -90 <= south < north <= 90):
        raise ConfigError(f"{source}: aois.{name} is not a valid [W, S, E, N] bbox: {bbox!r}")


def _validate_preregistered(data: dict[str, Any], source: Path) -> None:
    missing = [k for k in PREREG_REQUIRED_SECTIONS if k not in data]
    if missing:
        raise ConfigError(f"{source}: missing sections {missing}")
    if data["status"] not in PREREG_STATUSES:
        raise ConfigError(
            f"{source}: status must be one of {PREREG_STATUSES}, got {data['status']!r}"
        )
    for section in ("quake", "flood"):
        if not isinstance(data[section], dict):
            raise ConfigError(f"{source}: {section} must be a mapping")
    leaked = [k for k in OPERATIONAL_REQUIRED_SECTIONS if k in data]
    if leaked:
        raise ConfigError(f"{source}: operational keys {leaked} belong in {OPERATIONAL_FILENAME}")
    labelled = (data.get("labels") or {}).get("uncalibrated") or []
    known = {k for section in ("quake", "flood") for k in data[section]}
    unknown = [k for k in labelled if k not in known]
    if unknown:
        raise ConfigError(f"{source}: labels.uncalibrated names unknown parameters {unknown}")
    if data["status"] == "frozen":
        nulls = _null_leaves(data)
        if nulls:
            raise ConfigError(f"{source}: status is frozen but these values are null: {nulls}")


def _validate_operational(data: dict[str, Any], source: Path) -> None:
    missing = [k for k in OPERATIONAL_REQUIRED_SECTIONS if k not in data]
    if missing:
        raise ConfigError(f"{source}: missing sections {missing}")
    leaked = [k for k in PREREG_ONLY_KEYS if k in data]
    if leaked:
        raise ConfigError(f"{source}: pre-registered keys {leaked} belong in the frozen file")
    if not isinstance(data["aois"], dict) or not data["aois"]:
        raise ConfigError(f"{source}: aois must be a non-empty mapping")
    for name, bbox in data["aois"].items():
        _validate_bbox(name, bbox, source)
    budgets = data["breaker_budgets_s"]
    if not isinstance(budgets, dict) or "default" not in budgets:
        raise ConfigError(f"{source}: breaker_budgets_s needs an explicit 'default'")
    for tool, seconds in budgets.items():
        if isinstance(seconds, bool) or not isinstance(seconds, int | float) or seconds <= 0:
            raise ConfigError(f"{source}: breaker_budgets_s.{tool} must be a positive number")
    if not isinstance(data["features"], dict) or not all(
        isinstance(v, bool) for v in data["features"].values()
    ):
        raise ConfigError(f"{source}: features must map flag names to true/false")


@dataclass(frozen=True)
class Config:
    """Read-only view of both config files. Build it with `load_config()` or `get_config()`."""

    preregistered: Mapping[str, Any]
    operational: Mapping[str, Any]
    preregistered_path: Path
    operational_path: Path
    preregistered_hash: str

    @property
    def status(self) -> str:
        return self.preregistered["status"]

    @property
    def is_frozen(self) -> bool:
        return self.status == "frozen"

    def prereg(self, dotted: str, *, allow_null: bool = False) -> Any:
        """A pre-registered value, e.g. `prereg("flood.hand_max_m")`. Raises if missing or null."""
        return _lookup(self.preregistered, dotted, self.preregistered_path, allow_null)

    def ops(self, dotted: str, *, allow_null: bool = False) -> Any:
        """An operational value, e.g. `ops("mcp.ports.nisar_asf")`. Raises if missing or null."""
        return _lookup(self.operational, dotted, self.operational_path, allow_null)

    def aoi_names(self) -> tuple[str, ...]:
        return tuple(self.operational["aois"])

    def aoi_bbox(self, name: str) -> BBox:
        """[W, S, E, N] in EPSG:4326. Raises if the AOI is unknown or not set at the gate yet."""
        aois = self.operational["aois"]
        if name not in aois:
            raise ConfigError(f"{self.operational_path}: unknown AOI {name!r}; known: {list(aois)}")
        bbox = aois[name]
        if bbox is None:
            raise ConfigError(
                f"{self.operational_path}: AOI {name!r} has no bbox yet (set at the hour-2 gate)"
            )
        return tuple(float(v) for v in bbox)  # type: ignore[return-value]

    def breaker_budget_s(self, tool: str) -> float:
        """The measured per-tool budget, or the configured `default` until it is measured (D6)."""
        budgets = self.operational["breaker_budgets_s"]
        return float(budgets.get(tool, budgets["default"]))

    def feature(self, flag: str) -> bool:
        features = self.operational["features"]
        if flag not in features:
            raise ConfigError(f"{self.operational_path}: unknown feature flag {flag!r}")
        return features[flag]

    def require_frozen(self, expected_hash: str | None = None) -> None:
        """Raise unless the pre-registration is frozen (and, if given, matches `expected_hash`)."""
        if not self.is_frozen:
            raise ConfigError(f"{self.preregistered_path}: status is {self.status!r}, not frozen")
        if expected_hash is not None and expected_hash != self.preregistered_hash:
            raise ConfigError(
                f"{self.preregistered_path}: hash {self.preregistered_hash} does not match the "
                f"recorded {expected_hash}; the frozen file was edited"
            )


def load_config(config_dir: str | Path | None = None) -> Config:
    """Load and validate both config files from `config_dir`.

    `config_dir` defaults to `$BAILASAR_CONFIG_DIR`, else the repository's `config/`. The
    operational file names the pre-registration file, relative to the parent of `config_dir`.
    """
    if config_dir is None:
        config_dir = os.environ.get(CONFIG_DIR_ENV) or DEFAULT_CONFIG_DIR
    return _load_cached(str(Path(config_dir).resolve()))


@lru_cache(maxsize=8)
def _load_cached(config_dir: str) -> Config:
    directory = Path(config_dir)
    operational_path = directory / OPERATIONAL_FILENAME
    operational = _read_yaml(operational_path)
    _validate_operational(operational, operational_path)

    pointer = operational["preregistered"]
    if not isinstance(pointer, str) or not pointer:
        raise ConfigError(f"{operational_path}: 'preregistered' must be a path")
    preregistered_path = (directory.parent / pointer).resolve()
    if preregistered_path.parent != directory:
        raise ConfigError(f"{operational_path}: pre-registration must live in {directory}")
    preregistered = _read_yaml(preregistered_path)
    _validate_preregistered(preregistered, preregistered_path)

    return Config(
        preregistered=_deep_freeze(preregistered),
        operational=_deep_freeze(operational),
        preregistered_path=preregistered_path,
        operational_path=operational_path,
        preregistered_hash=git_blob_hash(preregistered_path.read_bytes()),
    )


def get_config() -> Config:
    """The repository configuration, loaded once per process."""
    return load_config()


def clear_cache() -> None:
    """Forget loaded configs (tests, or after editing operational settings in a live process)."""
    _load_cached.cache_clear()
