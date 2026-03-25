import os

from dotenv import load_dotenv

load_dotenv()


MINIMAX_BASE_URL = "https://api.minimax.io/anthropic"


def get_minimax_api_key() -> str:
    key = os.getenv("MINIMAX_API_KEY")
    if not key:
        raise SystemExit(
            "Missing MINIMAX_API_KEY. Copy .env.example to .env and add your key."
        )
    return key


def get_fast_model_name() -> str:
    return os.getenv("FAST_MODEL_NAME", "MiniMax-M2.7")


def get_tavily_api_key() -> str:
    key = os.getenv("TAVILY_API_KEY")
    if not key:
        raise SystemExit(
            "Missing TAVILY_API_KEY. Copy .env.example to .env and add your key."
        )
    return key
