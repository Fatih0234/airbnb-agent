import json

from pydantic_ai.mcp import MCPServerStdio

from .config import get_tavily_api_key


def create_airbnb_mcp_server() -> MCPServerStdio:
    return MCPServerStdio(
        "docker",
        args=["mcp", "gateway", "run", "--servers", "openbnb-airbnb"],
    )


def create_tavily_mcp_server() -> MCPServerStdio:
    return MCPServerStdio(
        "npx",
        args=["-y", "tavily-mcp@latest"],
        env={
            "TAVILY_API_KEY": get_tavily_api_key(),
            "DEFAULT_PARAMETERS": json.dumps(
                {
                    "search_depth": "advanced",
                    "max_results": 8,
                    "include_images": False,
                    "include_raw_content": False,
                }
            ),
        },
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
