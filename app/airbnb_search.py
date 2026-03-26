"""Airbnb search scraper using HTTP requests (mirrors MCP server approach).

Fetches search results via a single HTTP GET request and extracts structured
data from Airbnb's embedded JSON (niobeClientData). No browser automation
needed - same approach proven reliable by openbnb-org/mcp-server-airbnb.
"""

from __future__ import annotations

import base64
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any

import httpx

from .exceptions import NoResultsError, RateLimitError, ScraperException

log = logging.getLogger("airbnb_search")

BASE_URL = "https://www.airbnb.com"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)

REQUEST_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Cache-Control": "no-cache",
}

# Schema to filter listing fields (mirrors MCP server's allowSearchResultSchema)
LISTING_SCHEMA: dict[str, Any] = {
    "demandStayListing": {
        "id": True,
        "description": True,
        "location": True,
    },
    "badges": {"text": True},
    "structuredContent": {
        "mapCategoryInfo": {"body": True},
        "mapSecondaryLine": {"body": True},
        "primaryLine": {"body": True},
        "secondaryLine": {"body": True},
    },
    "avgRatingA11yLabel": True,
    "structuredDisplayPrice": {
        "primaryLine": {"accessibilityLabel": True},
        "secondaryLine": {"accessibilityLabel": True},
        "explanationData": {
            "title": True,
            "priceDetails": True,
        },
    },
}


# ---------------------------------------------------------------------------
# Helpers (mirrors MCP server util.ts)
# ---------------------------------------------------------------------------


def _clean_object(obj: Any) -> None:
    """Remove falsy keys and __typename in-place (mirrors MCP cleanObject)."""
    if isinstance(obj, dict):
        for key in list(obj.keys()):
            if not obj[key] or key == "__typename":
                del obj[key]
            elif isinstance(obj[key], (dict, list)):
                _clean_object(obj[key])
    elif isinstance(obj, list):
        for item in obj:
            _clean_object(item)


def _pick_by_schema(obj: Any, schema: dict[str, Any]) -> Any:
    """Keep only keys defined in schema (mirrors MCP pickBySchema)."""
    if not isinstance(obj, dict):
        return obj
    result: dict[str, Any] = {}
    for key, rule in schema.items():
        if key in obj:
            if rule is True:
                result[key] = obj[key]
            elif isinstance(rule, dict):
                result[key] = _pick_by_schema(obj[key], rule)
    return result


def _flatten_arrays(obj: Any, in_array: bool = False) -> Any:
    """Flatten nested arrays to strings (mirrors MCP flattenArraysInObject)."""
    if isinstance(obj, list):
        items = [_flatten_arrays(item, True) for item in obj]
        return ", ".join(str(i) for i in items)
    if isinstance(obj, dict):
        if in_array:
            vals = [_flatten_arrays(v, True) for v in obj.values()]
            return ": ".join(str(v) for v in vals if v)
        return {k: _flatten_arrays(v, False) for k, v in obj.items()}
    return obj


def _extract_listing_id(encoded_id: str) -> str:
    """Decode base64 listing ID (MCP uses base64('StayListing:NNN'))."""
    try:
        decoded = base64.b64decode(encoded_id).decode()
        return decoded.split(":")[-1]
    except Exception:
        return encoded_id


def _picture_url(pic: dict[str, Any]) -> str | None:
    """Extract image URL from a contextualPictures entry.

    Search results: ``picture`` is a string URL.
    Listing pages:  ``picture`` is a dict with ``url`` or ``baseUrl``.
    """
    raw = pic.get("picture")
    if isinstance(raw, str):
        return raw
    if isinstance(raw, dict):
        return raw.get("url") or raw.get("baseUrl")
    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


@dataclass
class SearchResult:
    """Result of an Airbnb search operation."""

    listings: list[dict[str, Any]]
    search_url: str
    total_found: int


async def search_airbnb(
    location: str,
    checkin: str,
    checkout: str,
    adults: int,
    max_price: int | None = None,
) -> SearchResult:
    """Search Airbnb listings via HTTP (same approach as MCP server).

    Args:
        location: Search location (city, neighborhood, etc.)
        checkin: Check-in date in YYYY-MM-DD format
        checkout: Check-out date in YYYY-MM-DD format
        adults: Number of adult guests
        max_price: Optional maximum price per night

    Returns:
        SearchResult with listings in MCP-compatible dict format.

    Raises:
        RateLimitError: If Airbnb returns 429/503
        NoResultsError: If no results found
        ScraperException: On other failures
    """
    # Build search URL
    url = f"{BASE_URL}/s/{_encode_location(location)}/homes"
    params: dict[str, str] = {}
    if checkin:
        params["checkin"] = checkin
    if checkout:
        params["checkout"] = checkout
    if adults > 0:
        params["adults"] = str(adults)
    if max_price:
        params["price_max"] = str(max_price)

    search_url = url
    log.info("Searching Airbnb: %s", location)

    # Make HTTP request
    async with httpx.AsyncClient(
        headers=REQUEST_HEADERS,
        timeout=httpx.Timeout(30.0, connect=10.0),
        follow_redirects=True,
    ) as client:
        resp = await client.get(url, params=params)

    if resp.status_code in (429, 503):
        raise RateLimitError(f"Airbnb returned {resp.status_code}")
    if resp.status_code != 200:
        raise ScraperException(f"Airbnb returned HTTP {resp.status_code}")

    html = resp.text

    # Extract JSON from <script id="data-deferred-state-0">
    match = re.search(
        r'<script\s+id="data-deferred-state-0"[^>]*>(.*?)</script>',
        html,
        re.DOTALL,
    )
    if not match:
        raise ScraperException("Could not find data-deferred-state-0 script tag")

    try:
        data = json.loads(match.group(1))
    except json.JSONDecodeError as e:
        raise ScraperException(f"Failed to parse niobeClientData JSON: {e}")

    # Navigate: niobeClientData[0][1].data.presentation.staysSearch.results
    try:
        niobe = data["niobeClientData"][0][1]
        results = niobe["data"]["presentation"]["staysSearch"]["results"]
    except (KeyError, IndexError, TypeError) as e:
        raise ScraperException(f"Unexpected JSON structure: {e}")

    raw_listings = results.get("searchResults", [])
    if not raw_listings:
        raise NoResultsError(f"No listings found for '{location}'")

    # Process each listing
    listings: list[dict[str, Any]] = []
    for raw in raw_listings:
        # Extract images before schema filter destroys the array.
        # contextualPictures[].picture is a string URL in search results.
        image_urls = [
            url
            for pic in raw.get("contextualPictures", [])
            if (url := _picture_url(pic))
        ]

        _clean_object(raw)
        filtered = _pick_by_schema(raw, LISTING_SCHEMA)
        # Flatten arrays to strings (matches MCP server behavior)
        filtered = _flatten_arrays(filtered)

        # Extract ID
        encoded_id = filtered.get("demandStayListing", {}).get("id", "")
        listing_id = _extract_listing_id(encoded_id)
        filtered["id"] = listing_id
        filtered["url"] = f"{BASE_URL}/rooms/{listing_id}"
        filtered["image_urls"] = image_urls[:6]
        listings.append(filtered)

    log.info("Found %d listings for '%s'", len(listings), location)
    return SearchResult(
        listings=listings,
        search_url=search_url,
        total_found=len(listings),
    )


def _encode_location(location: str) -> str:
    """URL-encode the location for the Airbnb search path."""
    import urllib.parse

    return urllib.parse.quote(location)
