# Inside agents/orchestrator.py
import os
from pathlib import Path
from langchain_community.cache import SQLiteCache
from langchain_core.globals import set_llm_cache

# Optional deterministic SQLite LLM cache so repeated demo runs take <150ms
CACHE_DB = Path("/app/local_cache/antioquia_aburra/llm_cache.sqlite")
if os.environ.get("ENABLE_LLM_CACHE", "1") == "1" and CACHE_DB.parent.exists():
    set_llm_cache(SQLiteCache(database_path=str(CACHE_DB)))

SERVER_DIR = Path(__file__).resolve().parent.parent / "mcp_servers"

if os.environ.get("USE_DOCKER_MCP_SSE", "0") == "1":
    MCP_CONFIG = {
        "nisar_asf": {
            "transport": "sse",
            "url": os.environ.get("NISAR_MCP_URL", "http://mcp-nisar-asf:8001/sse"),
        },
        "gee_fusion": {
            "transport": "sse",
            "url": os.environ.get("GEE_MCP_URL", "http://mcp-gee-fusion:8002/sse"),
        },
    }
else:
    MCP_CONFIG = {
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
