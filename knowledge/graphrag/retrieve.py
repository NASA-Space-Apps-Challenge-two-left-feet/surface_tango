"""Query the landslide GraphRAG index for conceptual grounding.

Thin wrapper over the Microsoft GraphRAG CLI (`graphrag query`) so the landslide
agent can ground its reasoning in the SGC methodology + Medellin POT detailed-risk
studies. Returns a clear state when the index is not built yet, mirroring the
project's evidence-envelope convention (never a fabricated answer).

Methods:
  - local   : entity-centric; best for "what does study X say about zone Y".
  - global  : community-summary; best for "which areas are prioritized / why".

Usage:
    uv run python -m knowledge.graphrag.retrieve --method global \
        "Which Valle de Aburra polygons are prioritized as high landslide risk and why?"
"""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE  # graphrag --root (settings.yaml lives here)
OUTPUT_DIR = HERE.parent.parent / "local_cache" / "graphrag" / "output"


def index_built() -> bool:
    """The index exists once GraphRAG has written its entity/community parquet outputs."""
    if not OUTPUT_DIR.exists():
        return False
    return any(OUTPUT_DIR.glob("*.parquet"))


def ground(question: str, method: str = "local") -> dict:
    """Return {'state', 'answer'|'reason'} — never a fabricated answer.

    state is one of: 'grounded' (index served), 'not_built' (run the index first),
    or 'error' (the query failed).
    """
    if method not in {"local", "global", "drift", "basic"}:
        raise ValueError(f"unknown method: {method}")
    if not index_built():
        return {
            "state": "not_built",
            "reason": (
                "GraphRAG index not built yet. Set the GRAPHRAG_* Azure OpenAI keys in "
                ".env, run `uv run python -m knowledge.graphrag.ingest`, then "
                "`uv run graphrag index --root knowledge/graphrag`."
            ),
        }
    try:
        proc = subprocess.run(
            [
                "uv",
                "run",
                "graphrag",
                "query",
                "--root",
                str(ROOT),
                "--method",
                method,
                "--query",
                question,
            ],
            capture_output=True,
            text=True,
            cwd=str(HERE.parent.parent),
            timeout=300,
        )
    except subprocess.TimeoutExpired:
        return {"state": "error", "reason": "graphrag query timed out (300s)"}
    if proc.returncode != 0:
        return {"state": "error", "reason": proc.stderr.strip()[-800:] or "query failed"}
    return {"state": "grounded", "answer": proc.stdout.strip(), "method": method}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("question")
    ap.add_argument("--method", default="local", choices=["local", "global", "drift", "basic"])
    args = ap.parse_args()
    result = ground(args.question, method=args.method)
    print(f"[{result['state']}]")
    print(result.get("answer") or result.get("reason", ""))
    return 0 if result["state"] in {"grounded", "not_built"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
