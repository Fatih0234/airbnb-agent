from __future__ import annotations

from pydantic import BaseModel

from ..schemas import CurationOutput
from .deck_spec import DeckSpec


class StylePreset(BaseModel):
    name: str
    vibe: str
    fonts: dict[str, str]
    colors: dict[str, str]
    radius: str
    shadow: str
    hero_layout: str
    card_style: str
    badge_style: str
    image_treatment: str
    motion_profile: str
    density_profile: str


EDITORIAL_ESCAPE = StylePreset(
    name="editorial_escape",
    vibe="warm editorial",
    fonts={
        "display": '"Iowan Old Style", "Palatino Linotype", "Book Antiqua", Georgia, serif',
        "body": '"Avenir Next", "Segoe UI", sans-serif',
    },
    colors={
        "primary": "#6C4A3B",
        "accent": "#D79C63",
        "bg": "#F6F1E8",
        "surface": "rgba(255, 252, 247, 0.88)",
        "text": "#241913",
        "muted": "rgba(36, 25, 19, 0.72)",
        "border": "rgba(36, 25, 19, 0.10)",
    },
    radius="24px",
    shadow="0 28px 60px rgba(60, 34, 19, 0.16)",
    hero_layout="full_bleed",
    card_style="glass-warm",
    badge_style="soft-pill",
    image_treatment="editorial",
    motion_profile="gentle",
    density_profile="airy",
)

PRACTICAL_PLANNER = StylePreset(
    name="practical_planner",
    vibe="structured utility",
    fonts={
        "display": '"Avenir Next Condensed", "Segoe UI", sans-serif',
        "body": '"Avenir Next", "Segoe UI", sans-serif',
    },
    colors={
        "primary": "#183B56",
        "accent": "#118AB2",
        "bg": "#F4F7FB",
        "surface": "rgba(255, 255, 255, 0.92)",
        "text": "#102A43",
        "muted": "rgba(16, 42, 67, 0.72)",
        "border": "rgba(16, 42, 67, 0.10)",
    },
    radius="18px",
    shadow="0 18px 44px rgba(16, 42, 67, 0.12)",
    hero_layout="structured_split",
    card_style="clean-elevated",
    badge_style="data-pill",
    image_treatment="crisp",
    motion_profile="snappy",
    density_profile="compact",
)

CONCIERGE_LUXURY = StylePreset(
    name="concierge_luxury",
    vibe="polished premium",
    fonts={
        "display": '"Didot", "Bodoni 72", "Times New Roman", serif',
        "body": '"Helvetica Neue", "Segoe UI", sans-serif',
    },
    colors={
        "primary": "#191817",
        "accent": "#C8A45D",
        "bg": "#F5F1EA",
        "surface": "rgba(20, 18, 17, 0.92)",
        "text": "#F7F2EA",
        "muted": "rgba(247, 242, 234, 0.76)",
        "border": "rgba(200, 164, 93, 0.18)",
        "surfaceAlt": "rgba(255, 250, 242, 0.92)",
        "textAlt": "#1C1916",
        "mutedAlt": "rgba(28, 25, 22, 0.72)",
        "borderAlt": "rgba(28, 25, 22, 0.10)",
    },
    radius="22px",
    shadow="0 28px 70px rgba(14, 11, 9, 0.28)",
    hero_layout="high_contrast",
    card_style="luxury-panel",
    badge_style="outlined-pill",
    image_treatment="high-contrast",
    motion_profile="restrained",
    density_profile="balanced",
)


STYLE_PRESETS = {
    EDITORIAL_ESCAPE.name: EDITORIAL_ESCAPE,
    PRACTICAL_PLANNER.name: PRACTICAL_PLANNER,
    CONCIERGE_LUXURY.name: CONCIERGE_LUXURY,
}


def choose_style_preset(deck: DeckSpec, result: CurationOutput) -> StylePreset:
    if deck.style_preset != "auto":
        return STYLE_PRESETS.get(deck.style_preset, EDITORIAL_ESCAPE)

    if result.trip_type in {"business", "workcation", "event_based", "family"}:
        return PRACTICAL_PLANNER

    if result.trip_type == "romantic" or result.destination_vibe in {"romantic", "cosmopolitan"}:
        return CONCIERGE_LUXURY

    return EDITORIAL_ESCAPE
