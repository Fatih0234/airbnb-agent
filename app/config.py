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


def get_model_name() -> str:
    return os.getenv("MODEL_NAME", "MiniMax-M2.7")


def get_fast_model_name() -> str:
    return os.getenv("FAST_MODEL_NAME", "MiniMax-M2.7")


def get_google_maps_api_key() -> str:
    key = os.getenv("GOOGLE_MAPS_API_KEY")
    if not key:
        raise SystemExit(
            "Missing GOOGLE_MAPS_API_KEY. Copy .env.example to .env and add your key."
        )
    return key
