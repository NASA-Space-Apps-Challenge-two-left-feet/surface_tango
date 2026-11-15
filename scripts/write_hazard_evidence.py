"""Serialize measured hazard runs into the MCP evidence artifacts (#122 schema).

The `analyze_*` tools on `mcp-gee-fusion` read
`local_cache/<aoi>/<hazard>_evidence*.json` (see
`docs/kb/mcp-evidence-artifact-schema.md`). This writer produces those artifacts
from the **structured measured outputs already in `local_cache/`** — it reads,
it never recomputes science or invents numbers, and a missing input is skipped
with a printed reason.

    uv run python scripts/write_hazard_evidence.py --hazard landslide

Landslide (`aburra`): from `local_cache/aburra/summary.json` and
`calibration.json`. The verdict outcome is `no_motion` when neither stack's kept
fraction exceeds its sign-flip null (the #109 result); `motion` otherwise.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "local_cache"


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


BUILDERS = {"landslide": landslide_artifact}
OUT_NAME = {"landslide": ("aburra", "landslide_evidence.json")}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--hazard", choices=sorted(BUILDERS), default="landslide")
    args = ap.parse_args(argv)
    artifact = BUILDERS[args.hazard]()
    if artifact is None:
        return 0
    aoi, name = OUT_NAME[args.hazard]
    out = CACHE / aoi / name
    out.write_text(json.dumps(artifact, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {out.relative_to(ROOT)} (outcome={artifact['noise_floor_verdict']['outcome']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
