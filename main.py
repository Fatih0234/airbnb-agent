import asyncio
import argparse
import logging
import os
import re
import webbrowser
from pathlib import Path

from app.agents.slides import generate_slides
from app.intake import collect_intake, load_intake_file
from app.pipeline import run_pipeline, save_html, save_output


# ---------------------------------------------------------------------------
# Log redaction — scrubs API keys from all log output
# ---------------------------------------------------------------------------

class _RedactingFilter(logging.Filter):
    def __init__(self):
        super().__init__()
        self._secrets: list[str] = []

    def add_secret(self, value: str | None) -> None:
        if value and len(value) > 8:
            self._secrets.append(re.escape(value))

    def filter(self, record: logging.LogRecord) -> bool:
        if self._secrets:
            pattern = "|".join(self._secrets)
            # Format first so %s/%d placeholders are resolved, then redact
            record.msg = re.sub(pattern, "***REDACTED***", record.getMessage())
            record.args = None
        return True


# ---------------------------------------------------------------------------
# Suppress noisy teardown messages from Docker MCP gateway
# ---------------------------------------------------------------------------

class _SuppressOAuthNoise(logging.Filter):
    _NOISE = (
        "OAuth notification",
        "context canceled",
        "Stop watching",
        "connection closed",
        "shutting down",
        "client disconnected",
    )

    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        return not any(n in msg for n in self._NOISE)


def _setup_logging() -> None:
    redactor = _RedactingFilter()
    redactor.add_secret(os.getenv("GOOGLE_MAPS_API_KEY"))
    redactor.add_secret(os.getenv("MINIMAX_API_KEY"))
    redactor.add_secret(os.getenv("TAVILY_API_KEY"))

    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("[%(name)s] %(message)s"))
    handler.addFilter(redactor)
    handler.addFilter(_SuppressOAuthNoise())

    logging.root.setLevel(logging.INFO)
    logging.root.addHandler(handler)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the trip planning pipeline from interactive prompts or a JSON intake file."
    )
    parser.add_argument(
        "--input",
        type=Path,
        help="Path to a JSON file containing IntakeOutput fields.",
    )
    return parser.parse_args()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def main():
    args = _parse_args()
    if args.input:
        intake = load_intake_file(args.input)
        print(f"Loaded trip intake from {args.input}")
    else:
        intake = await collect_intake()

    print("Researching your trip... this may take a minute.\n")

    result, summary = await run_pipeline(intake)
    print("Saving JSON travel brief...")
    path = save_output(result)

    # HTML travel book
    html_path = None
    slides_ok = False
    print("Generating HTML travel book...")
    try:
        html = await generate_slides(result)
        html_path = save_html(result, html)
        slides_ok = True
        webbrowser.open(html_path.as_uri())
    except Exception as exc:
        logging.error("Slides generation failed: %s", type(exc).__name__)

    # Status report
    curation_label = "curation ✓" if summary.curation_ok else "curation ✗"
    if summary.failed:
        print(f"\n⚠  Completed with partial results.")
        print(f"   OK      : {', '.join(summary.succeeded) or 'none'}, {curation_label}")
        print(f"   Failed  : {', '.join(summary.failed)}")
    else:
        print(f"\n✓  All {len(summary.succeeded)} research agents + {curation_label} completed successfully.")

    print(f"\nTravel brief : {path}")
    if slides_ok:
        print(f"Travel book  : {html_path}")
    else:
        print("Travel book  : ⚠ generation failed (JSON output still saved)")


if __name__ == "__main__":
    _setup_logging()
    asyncio.run(main())
