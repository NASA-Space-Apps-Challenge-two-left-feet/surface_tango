# Cache release `cache-2026-11-15-v2` — staged (not published)

Issues: #30, #42. Branch: `feat/data-cache-rebuild-restage`. Staged 2026-11-15 UTC.
Scope per the brief: ship only the three AOI folders + their `*_evidence.json`
artifacts; `local_cache/quake/` (the raw 584 MB DPM zarr dir) stays excluded.
The pre-registration is frozen (`config/preregistered.yaml` `status: frozen`,
hash `36a90fa…`, `validation/README.md`), so the C-pair coherence bands and the
quake `coherence_statistics` are no longer sealed and are included.

No file is fabricated or zero-filled anywhere in this pass; unknown sidecar
provenance stays explicitly `missing: true` in the release manifest (the
`scripts/cache_release.py` design), while band-level provenance ships inside
each AOI's `manifest.json`.

## 1. `hand_m` band — all three AOIs *(measured)*

MERIT Hydro `MERIT/Hydro/v1_0_1` band `hnd`, sampled onto each AOI's own cube
grid (512×512, EPSG:4326) via Earth Engine `ee.data.computePixels`; missing
pixels stay NaN and nothing is resampled with `"nearest"`. Command per AOI
(aburra and eje_cafetero appended in this pass; mojana already carried the
band from #137 and was skipped, unchanged):

```
uv run python scripts/build_cache.py --aoi <aoi> --only-band hand_m
```

Measured from the cubes on disk
(`uv run python -c` over `local_cache/<aoi>/<aoi>_sar_cube.zarr` and
`manifest.json`):

| AOI | bands in manifest | hand_m status | hand_m finite pixels | finite ratio | hand_m range (m) |
|---|---|---|---|---|---|
| aburra | 17 | cached | 262144 / 262144 | 1.0 | 0.0 – 1214.2 |
| eje_cafetero | 16 | cached | 262144 / 262144 | 1.0 | 0.0 – 1204.3 |
| mojana | 17 (unchanged) | cached | 262144 / 262144 | 1.0 | 0.0 – 716.0 |

Same numbers appear as `finite_pixel_count` / `finite_pixel_ratio` in each
`local_cache/<aoi>/manifest.json` `bands.hand_m` record, with the grid affine
and source id `GEE MERIT/Hydro/v1_0_1 band hnd version v1_0_1`.

## 2. Evidence artifacts regenerated *(measured)*

```
uv run python scripts/write_hazard_evidence.py --hazard landslide
uv run python scripts/write_hazard_evidence.py --hazard flood
uv run python scripts/write_hazard_evidence.py --hazard quake --track 11
uv run python scripts/write_hazard_evidence.py --hazard quake --track 47
```

- `local_cache/aburra/landslide_evidence.json` — outcome `no_motion` (the #109
  null gate result).
- `local_cache/mojana/flood_evidence.json` — display 2026-06-17, water
  5539/197758 px, baseline `accepted: true`.
- `local_cache/eje_cafetero/quake_evidence_track11.json` — valid 316399/10353357
  px, units 32/28/4 (total/evaluated/excluded), `coherence_statistics` included.
- `local_cache/eje_cafetero/quake_evidence_track47.json` — valid 316398/10353357
  px, units 32/28/4, `coherence_statistics` included.

Co-event vs control statistics are now on disk in the artifacts and unsealed at
serve time because the pre-registration is frozen; while it was a draft the
writer never wrote them.

## 3. Tool-serve check — the exact numbers the tools now serve *(measured)*

In-memory `fastmcp.Client(mcp)` calls against `mcp_servers/gee_fusion_mcp.py`
(the #127 pattern); every call returned the #122 envelope, zero drift against
the serialized artifacts:

| Tool | state | numbers served (denominators as shipped) |
|---|---|---|
| `analyze_flood_inundation(mojana)` | `live` | `water_extent_ha`: 5539 / **197758** valid px, 4486.59 ha, `pixel_area_m2` 8100.0 (90 m posting); baseline accepted; matches `reports/mojana.md` (5539 px, 4486.59 ha, denominator 197758 valid px) |
| `analyze_landslide_kinematics(aburra)` | `gate result` | `noise_floor_verdict.outcome = no_motion`, noise floor 9.105440970850369 mm over **17** pairs (the #109 null gate) |
| `analyze_earthquake_dpm(eje_cafetero, 11)` | `live` | valid 316399 / **10353357** window px; units total/evaluated/excluded 32/28/4; `coherence_statistics` **present** (`coevent_C` + `control_K`) post-freeze |
| `analyze_earthquake_dpm(eje_cafetero, 47)` | `live` | valid 316398 / **10353357** window px; units 32/28/4; `coherence_statistics` **present** |

## 4. Staged release — parts and hashes *(measured)*

Staging input: real copies of `local_cache/{aburra,eje_cafetero,mojana}` under
`dist/staged-aois/` (symlinks are rejected by the stager). Commands:

```
uv run python scripts/cache_release.py stage --cache-dir dist/staged-aois \
  --output-dir dist/cache-release --source-commit $(git rev-parse HEAD)
uv run python scripts/cache_release.py verify --manifest \
  dist/cache-release/cache_manifest.json --parts-dir dist/cache-release
```

Outcome: `cache stage: verified` and `cache verify: verified`. Contents of
`dist/cache-release/` (git-ignored; **not published**, never written to GCS):

| Asset | size (bytes, `stat`) | sha256 (`shasum -a 256`) |
|---|---|---|
| `cache.tar.gz.part-000000` | 137264762 | `ba24939ce6faec8019a0e0ec0ba3c62cf1131ebf9676e4a1ac5716f028614667` |
| `cache_manifest.json` | 392705 | `9f5266474b4b33316a6f2f5b8bb6ea71b5bb81bbdc3ff04d573b5a493943a9f8` |

Manifest facts: `schema_version` 1; `source_commit`
`9508d1ef5a75538ed8efc4bf3844e70fac190367` (this branch);
`build_time_utc` 2026-11-15T08:52:58Z; one part (137264762 bytes, below the
2 GiB GitHub per-asset ceiling); archive sha256 equals the single part's.

Inventory (1740 files, measured from the manifest's `provenance` list):
aburra 312, eje_cafetero 710, mojana 718. Includes the four
`*_evidence.json` artifacts, each AOI's cube with the `hand_m` array (16
`hand_m` member files across the three cubes plus the mojana `hand_m` COG), the
now-unsealed `coherence_C`/`coherence_coseismic` bands, COGs, tiles and
manifests; **zero** `quake/` files. All 1740 entries carry per-file sha256 and
`missing: true` provenance (no sidecar/zarr-attribute records exist in this
cache layout; explicitly unknown per the stager design, never fabricated).

## 5. Notes

- The v1 draft pre-release `cache-2026-11-15` (122,697,992 bytes, README status
  table) withheld C-pair coherence; v2 (137,264,762 bytes staged) includes it
  plus the `hand_m` bands and the evidence artifacts. Publishing/teammate
  download instructions remain the owner's action.
- `tests/test_cache_builder.py`: 15 passed after the builder change
  (`uv run python -m pytest tests/test_cache_builder.py -q`); full
  `make ci` green (422 passed, 7 deselected).
