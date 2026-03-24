from pydantic_ai.mcp import MCPServerStdio


def create_airbnb_mcp_server() -> MCPServerStdio:
    return MCPServerStdio(
        "docker",
        args=["mcp", "gateway", "run", "--servers", "openbnb-airbnb"],
    )


def create_brave_mcp_server() -> MCPServerStdio:
    return MCPServerStdio(
        "docker",
        args=["mcp", "gateway", "run", "--servers", "brave"],
        timeout=30,
    )


def create_openweather_mcp_server() -> MCPServerStdio:
    return MCPServerStdio(
        "docker",
        args=["mcp", "gateway", "run", "--servers", "openweather"],
    )


def create_google_maps_mcp_server() -> MCPServerStdio:
    return MCPServerStdio(
        "npx",
        args=["@cablate/mcp-google-map", "--stdio"],
        timeout=30,
    )
