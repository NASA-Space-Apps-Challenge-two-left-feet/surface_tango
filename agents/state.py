# agents/state.py
import operator
from typing import Annotated, Dict, List, Literal, Optional
from typing_extensions import TypedDict
from pydantic import BaseModel, Field

class HazardAgentReport(BaseModel):
    domain: Literal["landslide", "flood", "earthquake", "biomass"]
    alert_level: Literal["GREEN", "YELLOW", "ORANGE", "RED"]
    confidence_score: float = Field(ge=0.0, le=1.0)
    physical_radar_driver: str = Field(
        description="Explanation of dielectric constant, roughness, polarization, or InSAR phase mechanism."
    )
    key_quantitative_metrics: Dict[str, float]
    gee_xyz_tile_url: str
    hotspot_coordinates: List[float] = Field(description="[lon, lat] of peak anomaly")
    technical_summary: str

class CascadingMultiHazardBulletin(BaseModel):
    overall_alert_level: Literal["GREEN", "YELLOW", "ORANGE", "RED"]
    cascading_interactions: List[str] = Field(
        description="Compound hazard chains (e.g., Biomass loss + Seismic tremor -> Slope creep -> River damming flood)"
    )
    citizen_story_es: str = Field(description="Actionable early warning narrative in Spanish for local communities")
    decision_maker_brief_en: str = Field(description="Executive technical brief in English for NASA Space Apps judges")
    prioritized_layer_stack: List[Dict[str, str]]

class MultiHazardGraphState(TypedDict):
    region_name: str
    bbox: List[float]  # [min_lon, min_lat, max_lon, max_lat]
    start_date: str
    end_date: str
    # Populated by the Ingestion Node
    staged_nisar_assets: Dict[str, str]
    # Parallel Fan-In Reducer: merges dicts from the 4 parallel hazard agents
    hazard_reports: Annotated[Dict[str, dict], operator.or_]
    # Populated by the Cross-Hazard Synthesis Agent
    final_bulletin: Optional[dict]
