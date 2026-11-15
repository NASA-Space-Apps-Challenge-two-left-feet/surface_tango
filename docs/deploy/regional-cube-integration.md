# Regional cube integration decision

Recommendation: integrate as an optional cached-data explorer after VM acceptance.
Local correctness is verified; deployment and interactive browser acceptance are pending.
Do not replace the mission-control evidence or hazard decisions with preview imagery.

## Evidence

Reproduce with `make cube-check`. The measured results and source granule references
are recorded in [regional-cube-local.json](../../reports/regional-cube-local.json).
Every tested layer carries its original file name and provenance. The check compares
all stored pixels against the source (including nodata) and requests each preview.
Timing includes a source read, cube read, comparison and preview generation; it is
an in-process local measurement, not a network, concurrency or VM latency claim.

| Region | Packaged layers (measured) | Store bytes (measured) | State |
|---|---:|---:|---|
| La Mojana | 28 | 3,128,798 | cached |
| Aburrá | 14 | 11,171,798 | cached |
| Eje Cafetero | 13 | 10,267,428 | cached |
| La Picacha | 0 | 0 | not cached |
| Chocó epicenter | 0 | 0 | not cached |
| Valle del Cauca | 0 | 0 | not cached |

Denominator: all layers in the packaged catalogs, generated from extracted
GeoTIFFs. These counts do not assert completeness of all project datasets.
JSON and Parquet evidence is referenced by name, not copied into raster arrays.
NPZ stacks, vector features and Sentinel PNG tiles are not yet cube variables.

## Repository and application fit

- `/cube` is an additional FastAPI page; `/api/cube` provides its catalog and
  `/api/cube/{aoi}/{layer}/preview.png` serves decimated native-grid previews.
- `Dockerfile` already copies `app.py`, `scripts/` and `static/`; dependencies
  already include Xarray, Rasterio and Zarr. No new service or public port is needed.
- `docker-compose.yml` mounts `./local_cache:/app/local_cache` into the web service.
  Copy the complete `regional-cubes/` directory into that cache before serving it.
  The cubes are git-ignored data; a Git checkout or image rebuild alone omits them.
- The wake-on-request front door preserves request paths, so `/cube` can reach
  the application using the existing redirect. This is source inspection, not a
  verified public endpoint. Existing `/api/` requests also count toward VM activity.

## Local launch

From this worktree run `make cube`, then visit `http://127.0.0.1:8768/cube`.
Alternatively run `uv run python scripts/serve_cube.py --port 8769`.
The launcher changes to the repository directory and checks port binding before
starting. The current agent sandbox denies listening sockets; launch from the
user's terminal. In-process tests do not establish that a TCP server is running.

## VM acceptance before shipping

The documented VM is the existing pitch-mode host in `gcp-evaluation.md`.
Its current state has not been verified: the direct HTTP probe failed from this
session, and access to the local Docker daemon was denied. No cloud changes ran.

1. Review and merge the feature through the normal repository workflow, within
   the submission/code-freeze policy documented in `gcp-evaluation.md`.
2. Preserve the running image and cache for rollback. Build the candidate image
   and copy the packaged cube directory without replacing existing science inputs.
3. In a candidate container with the existing cache mount, execute
   `python scripts/check_regional_cube.py --output /tmp/cube-check.json`.
   Confirm `passed: true`; verify source granules if the VM has a different cache release.
4. Verify `/`, `/cube`, `/api/cube` and every cached preview through VM HTTP.
   Verify missing regions remain explicit and test the public front-door `/cube` path.
5. Inspect the page on desktop and mobile; compare an observed raster with its
   source. Measure concurrent preview requests and container peak memory on the VM
   before deciding acceptable performance. Local store size is not a RAM estimate.
6. Run the existing pitch smoke tests. Roll back the candidate image if any fail;
   the explorer data is separate from the original science cache.

## Decision limits

This is a native-grid raster collection in Zarr groups. It supports browsing
observations and provenance. It does not yet implement aligned temporal arrays,
spatial subsetting, an analytical query service, map pyramids, cloud object-store
access, or full multi-dataset cube semantics. Native-grid grayscale previews are
for inspection; they are not calibrated hazard maps. Unit metadata is incomplete
where the original sources did not serialize units. Production approval requires
browser review, VM memory/load measurements and a verified deployment rollback.
