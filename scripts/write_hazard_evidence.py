"""Serialize measured hazard runs into the MCP evidence artifacts (#122 schema).

The `analyze_*` tools on `mcp-gee-fusion` read
`local_cache/<aoi>/<hazard>_evidence*.json` (see
`docs/kb/mcp-evidence-artifact-schema.md`). This writer produces those artifacts
from the **structured measured outputs already in `local_cache/`** — it reads,
it never recomputes science or invents numbers, and a missing input is skipped
with a printed reason.

    uv run python scripts/write_hazard_evidence.py --hazard landslide
    uv run python scripts/write_hazard_evidence.py --hazard flood
    uv run python scripts/write_hazard_evidence.py --hazard quake --track 11

Landslide (`aburra`): from `local_cache/aburra/summary.json` and
`calibration.json`. The verdict outcome is `no_motion` when neither stack's kept
fraction exceeds its sign-flip null (the #109 result); `motion` otherwise.

Flood (`mojana`): from `local_cache/mojana/provenance.json` (baseline, dated
counts) and `manifest.json`. The display date is the ratified headline date
(2026-06-17, `reports/mojana.md`); areas carry their pixel counts and the
pixel area (from the manifest when it states one, else the 90 m GCOV posting
measured in the same run).

Quake (`eje_cafetero`, one artifact per track): from
`local_cache/quake/dpm_track<N>.zarr` provenance (counts, pairs, units, grid).
The C/K summaries are copied into `coherence_statistics` **only** when
`config/preregistered.yaml` says `status: frozen` (the same source the serving
tool reads); while the pre-registration is a draft the sealed statistics are
never written to disk at all (deviation 1, `validation/README.md`).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "local_cache"
PREREG = ROOT / "config" / "preregistered.yaml"

FLOOD_DISPLAY_DATE = "2026-06-17"  # ratified headline date (validation/README.md, #25)

# 90 m posting of the NISAR GCOV granules, measured in the same run
# (reports/mojana.md); used only when the manifest states no pixel size.
FLOOD_PIXEL_AREA_M2 = 90.0 * 90.0


def _prereg_is_frozen() -> bool:
    data = yaml.safe_load(PREREG.read_text(encoding="utf-8")) or {}
    return str(data.get("status", "draft")).strip().lower() == "frozen"


def _cache_build_time(summary: dict) -> str:
    return summary.get("measured_at_utc") or "unknown"


def landslide_artifact(aoi: str = "aburra") -> dict | None:
    base = CACHE / aoi
    summary_path, calib_path = base / "summary.json", base / "calibration.json"
    if not summary_path.is_file() or not calib_path.is_file():
        print(f"skip landslide {aoi}: summary.json or calibration.json absent")
        return None
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    calibration = json.loads(calib_path.read_text(encoding="utf-8"))
    if not calibration:
        print(f"skip landslide {aoi}: empty calibration")
        return None

    granule_ids = [p["scene_name"] for p in summary.get("pairs", []) if p.get("scene_name")]
    exceeds = any(row.get("exceeds_null") for row in calibration)
    n_pairs = int(summary.get("n_pairs_with_rms", 0))
    floor = summary.get("noise_floor_mm")
    outcome = "motion" if exceeds else "no_motion"
    text = (
        f"no motion detected above {floor:.3f} mm ({n_pairs} pairs); "
        "kept fraction below the sign-flip null on every stack"
        if not exceeds
        else f"motion retained above {floor:.3f} mm ({n_pairs} pairs)"
    )
    verdict = {
        "outcome": outcome,
        "evidence_status": "present",
        "text": text,
        "test": "per-pair residual RMS with sign agreement across independent pairs, sign-flip calibrated",
        "units": "mm",
        "noise_floor_mm": floor,
        "n_pairs": n_pairs,
        "calibration": [
            {
                "stack": row["stack"],
                "n_pairs": row["n_pairs"],
                "eligible_pixels": row["n_eligible"],
                "observed_kept_fraction": row["observed_kept_fraction"],
                "null_mean": row["null_mean"],
                "null_p95": row["null_p95"],
                "exceeds_null": row["exceeds_null"],
            }
            for row in calibration
        ],
    }
    pairs = [
        {
            "granule_id": p["scene_name"],
            "track": p.get("track"),
            "frame": p.get("frame"),
            "direction": p.get("direction"),
            "reference_date": p.get("reference_date"),
            "secondary_date": p.get("secondary_date"),
            "residual_rms_mm": p.get("residual_rms_mm"),
            "n_stable": p.get("n_stable"),
        }
        for p in summary.get("pairs", [])
    ]
    return {
        "schema": "landslide/1",
        "provenance": {
            "source": "cache",
            "granule_ids": granule_ids,
            "cache_build_time": _cache_build_time(summary),
            "command": summary.get("command"),
            "aoi_key": summary.get("aoi_key"),
            "stream": "PR (provisional)",
        },
        "uncalibrated": [],
        "noise_floor_verdict": verdict,
        "pairs": pairs,
        "key_quantitative_metrics": {
            "noise_floor_mm": {"value": floor, "n_pairs": n_pairs, "units": "mm"}
        },
    }


# --------------------------------------------------------------------------- #
# Flood — La Mojana, the ratified headline                                     #
# --------------------------------------------------------------------------- #
def _flood_uncalibrated() -> list[str]:
    data = yaml.safe_load(PREREG.read_text(encoding="utf-8")) or {}
    return list((data.get("labels") or {}).get("uncalibrated") or [])


def _stated_pixel_area_m2(manifest: dict) -> float | None:
    for key in ("pixel_area_m2", "cell_area_m2"):
        v = manifest.get(key)
        if isinstance(v, int | float) and not isinstance(v, bool):
            return float(v)
    for key in ("pixel_size_m", "posting_m", "cell_size_m"):
        v = manifest.get(key)
        if isinstance(v, int | float) and not isinstance(v, bool):
            return float(v) ** 2
    return None


def flood_artifact(aoi: str = "mojana") -> dict | None:
    base = CACHE / aoi
    prov_path, manifest_path = base / "provenance.json", base / "manifest.json"
    if not prov_path.is_file() or not manifest_path.is_file():
        print(f"skip flood {aoi}: provenance.json or manifest.json absent")
        return None
    prov = json.loads(prov_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    baseline = prov.get("baseline")
    dates = prov.get("dates") or []
    display = next((d for d in dates if d.get("date") == FLOOD_DISPLAY_DATE), None)
    if not isinstance(baseline, dict) or "accepted" not in baseline or display is None:
        print(f"skip flood {aoi}: baseline or display date {FLOOD_DISPLAY_DATE} absent")
        return None
    ref_date = baseline.get("reference_date")
    ref_row = next((d for d in dates if d.get("date") == ref_date), None)

    stated = _stated_pixel_area_m2(manifest)
    pixel_area = stated if stated is not None else FLOOD_PIXEL_AREA_M2
    area_source = (
        "manifest.json states the pixel area/size"
        if stated is not None
        else "constant 90 m NISAR GCOV posting measured in the same run "
        "(reports/mojana.md, #102); the manifest states no pixel size"
    )

    def _area(n_px: int, n_valid: int, source_ids: list[str], **extra) -> dict:
        return {
            "value_ha": n_px * pixel_area / 1e4,
            "pixel_count": n_px,
            "valid_pixel_count": n_valid,
            "pixel_area_m2": pixel_area,
            "source_ids": source_ids,
            "measurement": "measured",
            "command": prov.get("command"),
            "sensitivity_range": None,
            "sensitivity_reason": "sweep not serialized in provenance.json "
            "(only reports/mojana.md holds the range)",
            **extra,
        }

    display_ids = list(display.get("granule_ids") or [])
    ref_ids = list((ref_row or {}).get("granule_ids") or [])
    change_ids = sorted(set(ref_ids + display_ids)) or display_ids

    return {
        "schema": "flood/1",
        "provenance": {
            "source": "cache",
            "granule_ids": sorted({g for d in dates for g in (d.get("granule_ids") or [])}),
            "cache_build_time": prov.get("generated_utc") or "unknown",
            "command": prov.get("command"),
            "aoi": aoi,
            "aoi_key": manifest.get("aoi_key"),
            "bbox": prov.get("bbox") or manifest.get("bbox"),
            "display_date": FLOOD_DISPLAY_DATE,
            "pixel_area_m2_source": area_source,
            "stream": "PR (provisional)",
        },
        "uncalibrated": _flood_uncalibrated(),
        "baseline": baseline,
        "dates": dates,
        "water_extent": _area(
            display["n_water"], display["n_valid"], display_ids, reference_date=FLOOD_DISPLAY_DATE
        ),
        "open_water_flood": _area(
            display["n_class1"],
            display["n_valid_class1"],
            change_ids,
            reference_date=ref_date,
            target_date=FLOOD_DISPLAY_DATE,
        ),
        "subcanopy_double_bounce_flood": _area(
            display["n_class2"],
            display["n_valid_class2"],
            change_ids,
            reference_date=ref_date,
            target_date=FLOOD_DISPLAY_DATE,
        ),
    }


# --------------------------------------------------------------------------- #
# Quake — per-track DPM evidence; C/K statistics only once frozen              #
# --------------------------------------------------------------------------- #
_QUAKE_COUNT_KEYS = (
    "n_px_valid",
    "n_px_total",
    "n_units_total",
    "n_units_evaluated",
    "n_units_excluded",
)


def quake_artifact(aoi: str = "eje_cafetero", track: int = 11) -> dict | None:
    zarr = CACHE / "quake" / f"dpm_track{int(track)}.zarr" / "zarr.json"
    if not zarr.is_file():
        print(f"skip quake track {track}: dpm_track{track}.zarr absent")
        return None
    prov = json.loads(json.loads(zarr.read_text(encoding="utf-8"))["attributes"]["provenance"])
    summary = prov.get("summary_C")
    if not isinstance(summary, dict) or any(k not in summary for k in _QUAKE_COUNT_KEYS):
        print(f"skip quake track {track}: summary_C counts incomplete")
        return None
    pairs = prov.get("pairs") or {}
    granule_ids = [pairs[r]["granule_id"] for r in ("C", "R", "K") if r in pairs]
    artifact = {
        "schema": "quake/1",
        "provenance": {
            "source": "cache",
            "granule_ids": granule_ids,
            "cache_build_time": prov.get("run_utc") or "unknown",
            "command": f"uv run python -m gee_math.earthquake_dpm_math --track {int(track)}",
            "aoi": aoi,
            "track": int(track),
            "run_prereg_status": prov.get("prereg_status"),
            "run_prereg_sha1": prov.get("prereg_sha1"),
            "baseline_mismatch": prov.get("baseline_mismatch"),
            "stream": "PR (provisional)",
        },
        "uncalibrated": [],
        "counts": {
            "valid_pixels": summary["n_px_valid"],
            "window_pixels": summary["n_px_total"],
            "units_total": summary["n_units_total"],
            "evaluated": summary["n_units_evaluated"],
            "excluded": summary["n_units_excluded"],
        },
        "pairs": pairs,
        "units": prov.get("units"),
        "scorecard": {
            "state": "uninformative",
            "reason": "no barrio labels (reports/ground_truth.md, #24)",
        },
    }
    if _prereg_is_frozen():
        # Served only after the pre-registration freeze (#130); the run recorded
        # its own (possibly draft) status in provenance.run_prereg_status.
        artifact["coherence_statistics"] = {
            "coevent_C": prov["summary_C"],
            "control_K": prov["summary_K_control"],
            "note": "served after the pre-registration freeze (#130); run recorded "
            + str(prov.get("prereg_status")),
        }
    # Sealed while draft (deviation 1): with the freeze not in force the C/K
    # statistics are never written to disk at all — not in this artifact,
    # not anywhere else.
    return artifact


BUILDERS = {"landslide": landslide_artifact, "flood": flood_artifact, "quake": quake_artifact}
OUT_NAME = {
    "landslide": ("aburra", "landslide_evidence.json"),
    "flood": ("mojana", "flood_evidence.json"),
    "quake": ("eje_cafetero", "quake_evidence_track{track}.json"),
}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--hazard", choices=sorted(BUILDERS), default="landslide")
    ap.add_argument("--track", type=int, default=11, help="quake GUNW track (11 or 47)")
    args = ap.parse_args(argv)
    if args.hazard == "quake":
        artifact = BUILDERS[args.hazard](track=args.track)
    else:
        artifact = BUILDERS[args.hazard]()
    if artifact is None:
        return 0
    aoi, name = OUT_NAME[args.hazard]
    if "{track}" in name:
        name = name.format(track=args.track)
    out = CACHE / aoi / name
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(artifact, indent=1) + "\n", encoding="utf-8")
    if args.hazard == "landslide":
        print(
            f"wrote {out.relative_to(ROOT)} (outcome={artifact['noise_floor_verdict']['outcome']})"
        )
    elif args.hazard == "flood":
        w = artifact["water_extent"]
        print(
            f"wrote {out.relative_to(ROOT)} "
            f"(display={FLOOD_DISPLAY_DATE} water {w['pixel_count']}/{w['valid_pixel_count']} px, "
            f"baseline accepted={artifact['baseline']['accepted']})"
        )
    else:
        c = artifact["counts"]
        stats = (
            "included (pre-registration frozen)"
            if "coherence_statistics" in artifact
            else "omitted (sealed)"
        )
        print(
            f"wrote {out.relative_to(ROOT)} "
            f"(valid {c['valid_pixels']}/{c['window_pixels']} px, "
            f"units {c['units_total']}/{c['evaluated']}/{c['excluded']}, statistics {stats})"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
