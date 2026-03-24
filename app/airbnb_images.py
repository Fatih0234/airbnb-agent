"""Scrape listing photo URLs directly from the Airbnb listing page.

Airbnb embeds photo URLs in the page HTML under the pattern:
  a0.muscache.com/im/pictures/…/Hosting-{listing_id}/original/{uuid}.jpeg

The MCP tool (openbnb-airbnb) does not expose these, so we fetch them ourselves.
"""
import asyncio
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


def _listing_id(url: str) -> str | None:
    m = re.search(r"/rooms/(\d+)", url)
    return m.group(1) if m else None


async def fetch_listing_images(listing_url: str) -> list[str]:
    """Return up to _MAX_PHOTOS photo URLs for an Airbnb listing. Returns [] on failure."""
    listing_id = _listing_id(listing_url)
    if not listing_id:
        return []

    try:
        async with httpx.AsyncClient(headers=_HEADERS, follow_redirects=True, timeout=15) as client:
            r = await client.get(listing_url)
            r.raise_for_status()
    except Exception as exc:
        log.warning("Could not fetch Airbnb page %s: %s", listing_url, exc)
        return []

    seen: set[str] = set()
    photos: list[str] = []

    # New-style listings: Hosting-{id}/original/{uuid}.ext
    new_pattern = re.compile(
        rf"https://a0\.muscache\.com/im/pictures/[^\"\\]+Hosting-{listing_id}/original/[^\"\\?]+"
        r"\.(?:jpeg|jpg|webp|png)"
    )
    for m in new_pattern.finditer(r.text):
        url = m.group(0)
        if url not in seen:
            seen.add(url)
            photos.append(url)
        if len(photos) >= _MAX_PHOTOS:
            break

    # Old-style listings: flat {uuid}.jpg (no subdirectory)
    if not photos:
        old_pattern = re.compile(
            r"https://a0\.muscache\.com/im/pictures/"
            r"([a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})"
            r"\.(?:jpeg|jpg|webp|png)"
        )
        for m in old_pattern.finditer(r.text):
            url = m.group(0)
            if url not in seen:
                seen.add(url)
                photos.append(url)
            if len(photos) >= _MAX_PHOTOS:
                break

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
