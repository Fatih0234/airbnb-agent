from pydantic_ai.mcp import MCPServerStdio


def create_airbnb_mcp_server() -> MCPServerStdio:
    return MCPServerStdio(
        "docker",
        args=["mcp", "gateway", "run", "--servers", "openbnb-airbnb"],
    )
