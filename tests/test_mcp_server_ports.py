"""MCP entrypoints must name a port key that operational config actually defines.

The pitch VM crash-looped because gee_fusion_mcp asked for ``mcp-gee-fusion``
while config/bailasar.yaml defines ``gee_fusion``.
"""

import re
from pathlib import Path

from mcp_servers.cache_guard import operational_config

ROOT = Path(__file__).resolve().parents[1]
ENTRYPOINTS = ("mcp_servers/gee_fusion_mcp.py", "mcp_servers/nisar_asf_mcp.py")
RUN_SERVER = re.compile(r'^    run_server\(mcp, "([^"]+)"\)$', re.MULTILINE)


def test_mcp_entrypoints_use_configured_port_keys():
    ports = operational_config()["mcp"]["ports"]
    assert set(ports) == {"nisar_asf", "gee_fusion"}
    for relative in ENTRYPOINTS:
        text = (ROOT / relative).read_text(encoding="utf-8")
        names = RUN_SERVER.findall(text)
        assert names, relative
        assert names[-1] in ports, (relative, names[-1], sorted(ports))
