# 🛰️ Dancing with the SARs: Multi-Agent NISAR Early Warning & Cascading Hazard Observatory

[![NASA Space Apps 2026](https://img.shields.io/badge/NASA_Space_Apps_2026-Medell%C3%ADn%2C_Colombia-0B3D91?style=for-the-badge)](https://www.spaceappschallenge.org/2026/challenges/dancing-with-the-sars/)
[![Mission: NISAR L-Band](https://img.shields.io/badge/Sensor-NISAR_L--Band_(24cm)-00B4D8?style=for-the-badge)](https://nisar.jpl.nasa.gov/)
[![Compute: Google Earth Engine](https://img.shields.io/badge/Compute-GEE_High--Volume_%2B_Zarr_v3-34A853?style=for-the-badge&logo=google-earth)](https://earthengine.google.com/)
[![Orchestration: LangGraph + MCP](https://img.shields.io/badge/Agents-LangGraph_%2B_FastMCP-F97316?style=for-the-badge)](https://modelcontextprotocol.io/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=for-the-badge)](LICENSE)

> **"On Earth's surface there is an endless dance of natural processes and human activities... When upper-watershed deforestation strips root cohesion on 34° Andean slopes, 145 mm of tropical rainfall accelerates millimeter-scale slope creep into a catastrophic valley flood."**  
> — *Built in Medellín & Bello, Antioquia for the 2026 NASA Space Apps Challenge (`Dancing with the SARs`)*

---

## 🌍 1. Executive Summary & The "Hometown" Problem Statement

In the steep tropical topography of the **Aburrá Valley (Medellín, Bello, and Copacabana, Colombia)**, natural hazards do not happen in isolation—they **cascade**:
1. **Optical Blindness:** Persistent Andean cloud cover blinds optical satellites (`Sentinel-2`, `Landsat`) during critical rainy-season emergencies (`CHIRPS`).
2. **C-Band Foliage Decorrelation:** Short-wavelength C-band radar (`Sentinel-1`, $\lambda = 5.6\text{ cm}$) scatters off upper tree leaves, saturating at low forest biomass ($\sim 60\text{ Mg/ha}$) and suffering severe interferometric temporal decorrelation over vegetated hillslopes.
3. **The NISAR L-Band Breakthrough:** By exploiting **NISAR's 24.0 cm L-band wavelength** (`L2 GCOV`, `L2 GUNW`, and `L2 GOFF`), our system penetrates both tropical clouds and dense forest canopies to measure **bare-earth millimeter slope creep**, **sub-canopy dihedral double-bounce flooding**, **co-seismic urban building damage**, and **woody carbon disturbance** simultaneously.

We present an **open-source, multi-agent geospatial observatory** orchestrated via **LangGraph** and the **Model Context Protocol (MCP)**, powered by **Google Earth Engine's High-Volume Compute API**, **Zarr v3 Edge Data Cubes**, and an interactive **3-Panel Synchronized Curtain Slider & Radar Physics Inspector** (`MapLibre GL JS` + `Deck.gl`).

---

## 🏗️ 2. System Architecture (Mermaid Diagrams)

### 2.1 Zero-Download Cloud-to-Edge Data & Multi-Agent Topology

```mermaid
flowchart TB
    subgraph NASA_CLOUD["☁️ NASA Earthdata Cloud (AWS us-west-2 S3 / ASF DAAC)"]
        H5_GCOV["NISAR L2 GCOV (.h5)\nPolarimetric Covariance (HHHH, HVHV)"]
        H5_GUNW["NISAR L2 GUNW (.h5)\nUnwrapped Phase, Coherence & Ionosphere"]
        H5_GOFF["NISAR L2 GOFF (.h5)\n3D Range & Azimuth Pixel Offsets"]
    end

    subgraph MCP_TIER["🔌 Model Context Protocol (FastMCP Server Tier)"]
        MCP1["mcp-nisar-asf (Port 8001)\n• asf_search Track/Frame Pairing\n• GDAL /vsicurl/ Byte-Range Slicing\n• Split-Spectrum Ionosphere Removal"]
        MCP2["mcp-gee-fusion (Port 8002)\n• GEE High-Volume Compute Engine\n• Official + Awesome GEE Community Catalog\n• 1.8s Circuit-Breaker -> Local Zarr v3 Cube"]
    end

    subgraph GEE_CATALOGS["🌍 Google Earth Engine & Community Catalogs"]
        GEE_OFF["Official GEE Catalog\n• Sentinel-1 C-Band (5.6cm)\n• Sentinel-2 Optical RGB\n• CHIRPS Daily Rain\n• GEDI L4A Biomass Shots\n• MERIT Hydro HAND & JRC Water"]
        GEE_COMM["Awesome GEE Community Catalog\n• FABDEM (30m Tree-Free DEM)\n• ESA CCI AGB v6.0 Biomass\n• VIDA Combined Building Footprints\n• WorldPop Vulnerability"]
    end

    subgraph LANGGRAPH_DAG["🧠 LangGraph Parallel Multi-Agent Orchestrator"]
        INGEST["1. NISAR Ingestion Node\n(Stages COGs once per AOI)"]
        A_LAND["2a. Landslide Agent\n(3D Downslope InSAR + Rain)"]
        A_FLOOD["2b. Flood Agent\n(Specular vs Double-Bounce)"]
        A_QUAKE["2c. Seismic DPM Agent\n(Coherence Drop + VIDA)"]
        A_BIO["2d. Biomass Agent\n(HV Volume + GEDI GBDT)"]
        SYNTH["3. Cross-Hazard Synthesis Agent\n(Cascading Risk Chain & Bilingual Bulletin)"]
    end

    subgraph FRONTEND["🖥️ Interactive Mission Control UI (FastAPI SSE + MapLibre + Deck.gl)"]
        SLIDER["3-Panel Curtain Slider\nOptical vs. C-Band vs. NISAR L-Band"]
        INSPECTOR["Radar Physics Inspector\nDynamic Wave Scattering SVGs"]
        STORY["5-Chapter Story Map Tour\n3D Cascading Arcs over Bello & Medellín"]
    end

    H5_GCOV & H5_GUNW & H5_GOFF -->|"/vsicurl/ Byte-Range"| MCP1
    MCP1 -->|"Cloud-Optimized GeoTIFFs (gs://) & Local Zarr v3"| MCP2
    GEE_OFF & GEE_COMM --> MCP2
    INGEST --> MCP1
    INGEST --> A_LAND & A_FLOOD & A_QUAKE & A_BIO
    A_LAND & A_FLOOD & A_QUAKE & A_BIO <-->|"JSON-RPC Tool Calls"| MCP2
    A_LAND & A_FLOOD & A_QUAKE & A_BIO -->|"Annotated[Dict, operator.or_]"| SYNTH
    SYNTH -->|"Server-Sent Events (SSE) + XYZ Tiles"| SLIDER & INSPECTOR & STORY
