from __future__ import annotations

from ..presentation import build_deck_spec, choose_style_preset, render_html
from ..schemas import CurationOutput


async def generate_slides(result: CurationOutput) -> str:
    deck = build_deck_spec(result)
    style = choose_style_preset(deck, result)
    return render_html(deck, style, result)
