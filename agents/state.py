"""Explicit graph state; numeric observations remain unmodified tool results."""

import operator
from typing import Annotated, Any

from typing_extensions import TypedDict


class MultiHazardGraphState(TypedDict, total=False):
    region_name: str
    bbox: list[float]
    start_date: str
    end_date: str
    ingestion_requests: list[dict[str, Any]]
    tool_requests: dict[str, dict[str, Any]]
    staged_nisar_assets: dict[str, Any]
    hazard_reports: Annotated[dict[str, dict[str, Any]], operator.or_]
    final_bulletin: dict[str, Any] | None
