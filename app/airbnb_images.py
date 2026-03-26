"""Scrape listing photo URLs from Airbnb listing pages.

Airbnb embeds photo URLs in two places:
  1. Inside <script id="data-deferred-state-0"> as JSON (primary, reliable)
  2. Inline in HTML attributes (fallback, less reliable)

CDN URL patterns seen:
  - a0.muscache.com/im/pictures/{uuid}.jpg                  (old-style)
  - a0.muscache.com/im/pictures/hosting/Hosting-{id}/…/{uuid}.jpeg (new-style)
  - a0.muscache.com/im/pictures/miso/Hosting-{id}/…/{uuid}.jpeg    (variant)

The search results may already have images from contextualPictures —
enrich_stays_with_images only fetches per-listing images when needed.
"""

import asyncio
import json
import logging
import re

import httpx

log = logging.getLogger("airbnb_images")

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}
_MAX_PHOTOS = 6

# Broad pattern that catches all known CDN URL formats (old, hosting/, miso/, etc.)
_MUSCACHE_IMAGE_RE = re.compile(
    r"https://a0\.muscache\.com/im/pictures/"
    r"[^\s\"'\\>]+\.(?:jpeg|jpg|webp|png)"
)


def _listing_id(url: str) -> str | None:
    m = re.search(r"/rooms/(\d+)", url)
    return m.group(1) if m else None


def _extract_images_from_json(json_text: str, listing_id: str) -> list[str]:
    """Find all muscache image URLs inside the deferred-state JSON string."""
    seen: set[str] = set()
    photos: list[str] = []
    for m in _MUSCACHE_IMAGE_RE.finditer(json_text):
        url = m.group(0)
        if url not in seen:
            seen.add(url)
            photos.append(url)
        if len(photos) >= _MAX_PHOTOS:
            break
    return photos


def _extract_images_from_html(html: str, listing_id: str) -> list[str]:
    """Fallback: find muscache image URLs directly in raw HTML."""
    seen: set[str] = set()
    photos: list[str] = []
    for m in _MUSCACHE_IMAGE_RE.finditer(html):
        url = m.group(0)
        if url not in seen:
            seen.add(url)
            photos.append(url)
        if len(photos) >= _MAX_PHOTOS:
            break
    return photos


async def fetch_listing_images(listing_url: str) -> list[str]:
    """Return up to _MAX_PHOTOS photo URLs for an Airbnb listing. Returns [] on failure."""
    listing_id = _listing_id(listing_url)
    if not listing_id:
        return []

    try:
        async with httpx.AsyncClient(
            headers=_HEADERS, follow_redirects=True, timeout=15
        ) as client:
            r = await client.get(listing_url)
            r.raise_for_status()
    except Exception as exc:
        log.warning("Could not fetch Airbnb page %s: %s", listing_url, exc)
        return []

    html = r.text
    photos: list[str] = []

    # Strategy 1: Parse deferred-state JSON (most reliable)
    match = re.search(
        r'<script\s+id="data-deferred-state-0"[^>]*>(.*?)</script>',
        html,
        re.DOTALL,
    )
    if match:
        try:
            json_text = match.group(1)
            json.loads(json_text)  # validate it's real JSON
            photos = _extract_images_from_json(json_text, listing_id)
        except (json.JSONDecodeError, Exception) as exc:
            log.debug("JSON parse failed for listing %s: %s", listing_id, exc)

    # Strategy 2: Regex on full HTML (catches images in inline attributes)
    if not photos:
        photos = _extract_images_from_html(html, listing_id)

    log.info("Scraped %d photos for listing %s", len(photos), listing_id)
    return photos


async def enrich_stays_with_images(stays: list) -> list:
    """Fill image_urls for any StayCandidate that has an empty list and a valid url."""
    tasks = []
    indices = []
    for i, stay in enumerate(stays):
        if not stay.image_urls and stay.url:
            tasks.append(fetch_listing_images(stay.url))
            indices.append(i)

    if not tasks:
        return stays

    results = await asyncio.gather(*tasks, return_exceptions=True)
    for i, result in zip(indices, results):
        if isinstance(result, list) and result:
            stays[i].image_urls = result

    return stays
