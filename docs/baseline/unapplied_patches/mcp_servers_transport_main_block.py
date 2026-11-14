# Replace the bottom `if __name__ == "__main__":` block in BOTH mcp_servers/*.py files with:
if __name__ == "__main__":
    transport = os.environ.get("MCP_TRANSPORT", "stdio")
    if transport == "sse":
        mcp.run(
            transport="sse",
            host="0.0.0.0",
            port=int(os.environ.get("MCP_PORT", "8001")),
        )
    else:
        mcp.run(transport="stdio")
