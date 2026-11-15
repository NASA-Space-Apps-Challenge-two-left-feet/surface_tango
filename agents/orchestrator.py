# agents/orchestrator.py
import asyncio
import os
from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.sessions import Connection
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import create_react_agent

from agents.llm import get_orchestrator_llm
from agents.state import (
    CascadingMultiHazardBulletin,
    HazardAgentReport,
    MultiHazardGraphState,
)
from agents.tracing import configure_tracing, run_metadata

SERVER_DIR = Path(__file__).resolve().parent.parent / "mcp_servers"

MCP_CONFIG: dict[str, Connection] = {
    "nisar_asf": {
        "transport": "stdio",
        "command": "python",
        "args": [str(SERVER_DIR / "nisar_asf_mcp.py")],
    },
    "gee_fusion": {
        "transport": "stdio",
        "command": "python",
        "args": [str(SERVER_DIR / "gee_fusion_mcp.py")],
    },
}

llm = get_orchestrator_llm()  # fallback chain from config/bailasar.yaml (llm:)


async def build_and_run_multi_hazard_graph(initial_state: MultiHazardGraphState):
    client = MultiServerMCPClient(MCP_CONFIG)
    all_tools = await client.get_tools()
    tool_map = {t.name: t for t in all_tools}

    # 1. Ingestion Node: Searches and stages NISAR GCOV & GUNW COGs once for all downstream agents
    async def nisar_ingestion_node(state: MultiHazardGraphState):
        ingestion_agent = create_react_agent(
            llm,
            tools=[
                tool_map["search_nisar_granules"],
                tool_map["stage_nisar_gcov_to_gcs"],
                tool_map["stage_nisar_gunw_ionosphere_corrected_to_gcs"],
            ],
        )
        prompt = (
            f"Search NISAR GCOV and GUNW granules for bbox {state['bbox']} between "
            f"{state['start_date']} and {state['end_date']}. Stage the latest GCOV (HHHH, HVHV), "
            f"pre-event GCOV HHHH, and ionosphere-corrected GUNW phase & coherence to GCS. "
            f"Return all gs:// URIs."
        )
        res = await ingestion_agent.ainvoke({"messages": [HumanMessage(content=prompt)]})
        return {"staged_nisar_assets": {"summary": res["messages"][-1].content}}

    # Helper factory for the 4 specialized Hazard Agents
    def make_domain_node(domain_name: str, tool_name: str, physics_instructions: str):
        async def _node(state: MultiHazardGraphState):
            worker = create_react_agent(
                llm,
                tools=[tool_map[tool_name]],
                response_format=HazardAgentReport,
            )
            msg = (
                f"Domain: {domain_name.upper()}\n"
                f"Region: {state['region_name']} | BBox: {state['bbox']}\n"
                f"Date Window: {state['start_date']} to {state['end_date']}\n"
                f"Staged NISAR GCS Assets: {state['staged_nisar_assets']}\n"
                f"Instructions: {physics_instructions}"
            )
            result = await worker.ainvoke({"messages": [HumanMessage(content=msg)]})
            structured: HazardAgentReport = result["structured_response"]
            return {"hazard_reports": {domain_name: structured.model_dump()}}

        return _node

    landslide_node = make_domain_node(
        "landslide",
        "analyze_landslide_kinematics",
        "Call analyze_landslide_kinematics using the staged GUNW phase and coherence GCS URIs. "
        "Explain how L-band 24cm wavelength penetrates tropical foliage over steep FABDEM slopes and interacts with 15-day CHIRPS rainfall.",
    )

    flood_node = make_domain_node(
        "flood",
        "analyze_flood_inundation",
        "Call analyze_flood_inundation. Differentiate open-water specular reflection (low HH/HV) "
        "from sub-canopy wetland double-bounce scattering (high HH surge due to dielectric water-trunk interaction).",
    )

    earthquake_node = make_domain_node(
        "earthquake",
        "analyze_earthquake_dpm",
        "Call analyze_earthquake_dpm. Evaluate interferometric coherence loss across VIDA building footprints and WorldPop exposure.",
    )

    biomass_node = make_domain_node(
        "biomass",
        "analyze_biomass_disturbance",
        "Call analyze_biomass_disturbance. Explain how HV cross-polarized volume scattering tracks woody canopy loss against ESA CCI AGB v6.0.",
    )

    # 3. Cross-Hazard Synthesis Agent (Fan-In Node)
    async def cross_hazard_synthesis_node(state: MultiHazardGraphState):
        structured_llm = llm.with_structured_output(CascadingMultiHazardBulletin)
        sys_prompt = SystemMessage(
            content=(
                "You are the Principal Cross-Hazard Synthesis Agent for the 'Dancing with the SARs' system. "
                "Analyze the 4 domain reports (Landslide, Flood, Earthquake, Biomass) simultaneously. "
                "Identify physical cascading chains: e.g., how deforestation (Biomass HV drop) or seismic shaking "
                "(Earthquake DPM) reduces root cohesion and triggers translational slope failure (Landslide GUNW phase creep), "
                "which can dam mountain streams and cause downstream inundation (Flood GCOV double-bounce)."
            )
        )
        human_prompt = HumanMessage(
            content=f"Region: {state['region_name']}\nReports: {state['hazard_reports']}"
        )
        bulletin: CascadingMultiHazardBulletin = await structured_llm.ainvoke(
            [sys_prompt, human_prompt]
        )
        return {"final_bulletin": bulletin.model_dump()}

    # Build the Parallel Fan-Out / Fan-In StateGraph
    builder = StateGraph(MultiHazardGraphState)
    builder.add_node("nisar_ingestion", nisar_ingestion_node)
    builder.add_node("landslide_agent", landslide_node)
    builder.add_node("flood_agent", flood_node)
    builder.add_node("earthquake_agent", earthquake_node)
    builder.add_node("biomass_agent", biomass_node)
    builder.add_node("cross_hazard_synthesis", cross_hazard_synthesis_node)

    builder.add_edge(START, "nisar_ingestion")

    # Parallel Fan-Out from Ingestion to all 4 Hazard Agents
    builder.add_edge("nisar_ingestion", "landslide_agent")
    builder.add_edge("nisar_ingestion", "flood_agent")
    builder.add_edge("nisar_ingestion", "earthquake_agent")
    builder.add_edge("nisar_ingestion", "biomass_agent")

    # Parallel Fan-In to Cross-Hazard Synthesis Agent
    builder.add_edge(
        ["landslide_agent", "flood_agent", "earthquake_agent", "biomass_agent"],
        "cross_hazard_synthesis",
    )
    builder.add_edge("cross_hazard_synthesis", END)

    graph = builder.compile()
    print(configure_tracing())
    mode = "cached" if os.environ.get("OFFLINE_DEMO_MODE") == "1" else "live"
    return await graph.ainvoke(initial_state, config=run_metadata(mode))


if __name__ == "__main__":
    # Example invocation over the Aburra Valley / Bello / Medellin Northern Slopes
    sample_state: MultiHazardGraphState = {
        "region_name": "Valle de Aburrá - Bello & Medellín Eastern/Northern Slopes, Antioquia",
        "bbox": [-75.63, 6.22, -75.50, 6.38],
        "start_date": "2026-09-01",
        "end_date": "2026-11-13",
        "staged_nisar_assets": {},
        "hazard_reports": {},
        "final_bulletin": None,
    }
    final_output = asyncio.run(build_and_run_multi_hazard_graph(sample_state))
    print(final_output["final_bulletin"])
