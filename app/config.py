import os

from dotenv import load_dotenv

load_dotenv()


def get_openrouter_api_key() -> str:
    key = os.getenv("OPENROUTER_API_KEY")
    if not key:
        raise SystemExit(
            "Missing OPENROUTER_API_KEY. Copy .env.example to .env and add your key."
        )
    return key


def get_model_name() -> str:
    return os.getenv("MODEL_NAME", "minimax/minimax-m2.7")
