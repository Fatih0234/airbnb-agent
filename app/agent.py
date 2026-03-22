from pydantic_ai import Agent
from pydantic_ai.models.openrouter import OpenRouterModel
from pydantic_ai.providers.openrouter import OpenRouterProvider

from .config import get_model_name, get_openrouter_api_key
from .mcp_client import create_airbnb_mcp_server
from .prompt import SYSTEM_PROMPT


def create_agent() -> Agent:
    api_key = get_openrouter_api_key()
    model_name = get_model_name()

    model = OpenRouterModel(
        model_name,
        provider=OpenRouterProvider(api_key=api_key),
    )

    mcp_server = create_airbnb_mcp_server()

    return Agent(
        model,
        toolsets=[mcp_server],
        system_prompt=SYSTEM_PROMPT,
    )
