from __future__ import annotations

import html
from urllib.parse import urlparse


def escape(value: object | None) -> str:
    if value is None:
        return ""
    return html.escape(str(value))


def format_money(value: float | None) -> str:
    if value is None:
        return "N/A"
    if value.is_integer():
        return f"${int(value)}"
    return f"${value:.0f}"


def format_duration(minutes: int | None) -> str:
    if minutes is None:
        return "N/A"
    hours, remainder = divmod(minutes, 60)
    if hours and remainder:
        return f"{hours}h {remainder}m"
    if hours:
        return f"{hours}h"
    return f"{remainder}m"


def format_stops(stops: int) -> str:
    if stops == 0:
        return "Non-stop"
    if stops == 1:
        return "1 stop"
    return f"{stops} stops"


def format_trip_type(trip_type: str) -> str:
    return trip_type.replace("_", " ")


def price_badge_color(price_range: str) -> str:
    return {
        "$": "#2E7D32",
        "$$": "#D68910",
        "$$$": "#C0392B",
    }.get(price_range, "#7F8C8D")


def source_host(source_url: str | None) -> str:
    if not source_url:
        return ""
    host = urlparse(source_url).netloc.lower()
    return host[4:] if host.startswith("www.") else host


def source_cta(source_url: str | None) -> str:
    if not source_url:
        return ""
    host = source_host(source_url)
    host_line = f'<p class="source-host">{escape(host)}</p>' if host else ""
    return (
        f"{host_line}"
        f'<a href="{escape(source_url)}" class="button source-button" target="_blank" rel="noreferrer">Visit link →</a>'
    )


def truncate_to_headline(text: str, max_words: int = 25) -> tuple[str, str | None]:
    """Split *text* into a short headline and an optional remainder.

    Strategy: take the first sentence (split on ``". "`` or a trailing period).
    If the first sentence exceeds *max_words*, cut at *max_words* and add an
    ellipsis.  Returns ``(headline, remainder_or_none)``.
    """
    text = text.strip()
    if not text:
        return ("", None)

    # Try splitting on first sentence boundary.
    dot_pos = text.find(". ")
    if dot_pos == -1 and text.endswith("."):
        dot_pos = len(text) - 1
    if dot_pos != -1:
        first_sentence = text[: dot_pos + 1].strip()
        remainder = text[dot_pos + 1 :].strip() or None
    else:
        first_sentence = text
        remainder = None

    words = first_sentence.split()
    if len(words) > max_words:
        headline = " ".join(words[:max_words]) + "\u2026"
        leftover = " ".join(words[max_words:])
        if remainder:
            remainder = f"{leftover} {remainder}"
        else:
            remainder = leftover
    else:
        headline = first_sentence

    return (headline, remainder)


_SVG_ICONS: dict[str, str] = {
    "shield": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" '
        'stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>'
    ),
    "sparkles": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" '
        'stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M12 3l1.5 5.5L19 10l-5.5 1.5L12 17l-1.5-5.5L5 10l5.5-1.5z"/>'
        '<path d="M19 15l.5 1.5L21 17l-1.5.5L19 19l-.5-1.5L17 17l1.5-.5z"/></svg>'
    ),
    "walking": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" '
        'stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<circle cx="13" cy="4" r="2"/>'
        '<path d="M7 21l3-4 2.5 3 3.5-5-2-4-3 1-2-3-3 4z"/></svg>'
    ),
    "plane": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" '
        'stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M17.8 19.2L16 11l3.5-3.5C21 6 21.5 4 21 3c-1-.5-3 0-4.5 1.5L13 8 4.8 6.2c-.5-.1-.9.1-1.1.5l-.3.5 '
        '5.1 3.1-3.3 3.3-2.1-.6-.5.5 2.5 2.5.5-.5-.6-2.1 3.3-3.3 3.1 5.1.5-.3c.4-.2.6-.6.5-1.1z"/></svg>'
    ),
    "dollar": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" '
        'stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<line x1="12" y1="1" x2="12" y2="23"/>'
        '<path d="M17 5H9.5a3.5 3.5 0 000 7h5a3.5 3.5 0 010 7H6"/></svg>'
    ),
    "layers": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" '
        'stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<polygon points="12 2 2 7 12 12 22 7 12 2"/>'
        '<polyline points="2 17 12 22 22 17"/>'
        '<polyline points="2 12 12 17 22 12"/></svg>'
    ),
}


def inline_svg_icon(name: str) -> str:
    """Return an inline SVG icon string for *name*, or empty string if unknown."""
    return _SVG_ICONS.get(name, "")


def image_wrap(
    label: str,
    image_url: str | None,
    height: int,
    *,
    class_name: str = "img-wrap",
) -> str:
    image_html = ""
    if image_url:
        image_html = (
            f'<img src="{escape(image_url)}" alt="{escape(label)}" loading="lazy" '
            'onerror="this.style.opacity=0">'
        )
    return (
        f'<div class="{class_name}" style="height:{height}px" data-label="{escape(label)}">'
        f"{image_html}</div>"
    )
