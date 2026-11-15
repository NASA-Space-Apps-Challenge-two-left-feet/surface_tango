"""Extract text from the curated landslide-risk corpus into the GraphRAG input dir.

Public official sources only (SGC methodology + Medellin POT detailed-risk
resolutions), listed in ``sources.yaml`` and cited by resolution. The source PDFs
live outside the repo; this writes extracted text + a provenance manifest into the
git-ignored ``local_cache/graphrag/input/`` for the GraphRAG index to consume.

Pages with no extractable text (scanned) are counted and reported as OCR
candidates; they are never fabricated or zero-filled.

Usage:
    uv run python -m knowledge.graphrag.ingest            # all curated sources
    uv run python -m knowledge.graphrag.ingest --only la-picacha sgc-guia-detalle
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import fitz  # PyMuPDF
import yaml

HERE = Path(__file__).resolve().parent
# Repo root is two levels up (knowledge/graphrag -> repo).
REPO_ROOT = HERE.parent.parent
INPUT_DIR = REPO_ROOT / "local_cache" / "graphrag" / "input"


def _expand(path: str) -> Path:
    return Path(path).expanduser()


def load_sources() -> list[dict]:
    data = yaml.safe_load((HERE / "sources.yaml").read_text(encoding="utf-8"))
    out: list[dict] = []
    for group in ("methodology", "studies"):
        for entry in data.get(group, []) or []:
            entry = dict(entry)
            entry["group"] = group
            out.append(entry)
    return out


def extract_text(pdf_path: Path) -> tuple[str, int, int]:
    """Return (text, n_pages, n_scanned_pages). Scanned = a page with no text layer."""
    parts: list[str] = []
    scanned = 0
    with fitz.open(pdf_path) as doc:
        n_pages = doc.page_count
        for i, page in enumerate(doc):
            txt = page.get_text("text").strip()
            if not txt:
                scanned += 1
                parts.append(f"\n[page {i + 1}: no text layer — scanned, pending OCR]\n")
            else:
                parts.append(txt)
    return "\n\n".join(parts), n_pages, scanned


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--only", nargs="*", help="slugs to ingest (default: all)")
    args = ap.parse_args()

    INPUT_DIR.mkdir(parents=True, exist_ok=True)
    sources = load_sources()
    if args.only:
        wanted = set(args.only)
        sources = [s for s in sources if s["slug"] in wanted]

    manifest: dict[str, dict] = {}
    missing: list[str] = []
    for s in sources:
        src = _expand(s["path"])
        slug = s["slug"]
        if not src.exists():
            missing.append(f"{slug}: {src}")
            print(f"  MISSING  {slug}: {src}")
            continue
        text, n_pages, scanned = extract_text(src)
        header = (
            f"# SOURCE: {s['citation']}\n"
            f"# SLUG: {slug} | GROUP: {s['group']}"
            + (f" | AOI: {s['aoi']}" if s.get("aoi") else "")
            + f"\n# PAGES: {n_pages} | SCANNED (no text layer): {scanned}\n\n"
        )
        out_path = INPUT_DIR / f"{slug}.txt"
        out_path.write_text(header + text, encoding="utf-8")
        manifest[slug] = {
            "citation": s["citation"],
            "group": s["group"],
            "aoi": s.get("aoi"),
            "source_path": str(src),
            "pages": n_pages,
            "scanned_pages": scanned,
            "chars": len(text),
            "output": out_path.name,
        }
        flag = f"  ({scanned} scanned → OCR pending)" if scanned else ""
        print(f"  OK  {slug}: {n_pages} pp, {len(text):,} chars{flag}")

    (INPUT_DIR / "_provenance.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\nWrote {len(manifest)} docs to {INPUT_DIR}")
    if missing:
        print(f"MISSING {len(missing)}: " + "; ".join(missing))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
