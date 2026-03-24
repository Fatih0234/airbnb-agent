from __future__ import annotations

import asyncio
import json
import logging
import re
import unicodedata
from collections.abc import Callable
from html.parser import HTMLParser
from typing import TypeVar
from urllib.parse import urljoin, urlparse

import httpx

from .schemas import ActivitiesOutput, ActivityItem, FoodItem, FoodOutput

log = logging.getLogger("content_enrichment")

_FETCH_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}
_FETCH_TIMEOUT_SECONDS = 15
_FETCH_CONCURRENCY = 4
_MIN_LINKED_ITEMS = 6
_INVALID_IMAGE_MARKERS = (
    "favicon",
    "apple-touch-icon",
    "mask-icon",
    "logo",
    "icon",
    "sprite",
    "avatar",
    "placeholder",
    "spacer",
    "pixel",
    "blank",
)

T = TypeVar("T", ActivityItem, FoodItem)


class _PageMetadataParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.meta_tags: list[dict[str, str]] = []
        self.link_tags: list[dict[str, str]] = []
        self.json_ld_blobs: list[str] = []
        self._capture_json_ld = False
        self._json_ld_chunks: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        normalized_attrs = {
            (key or "").lower(): (value or "").strip()
            for key, value in attrs
        }
        if tag == "meta":
            self.meta_tags.append(normalized_attrs)
            return
        if tag == "link":
            self.link_tags.append(normalized_attrs)
            return
        if tag == "script":
            script_type = normalized_attrs.get("type", "").split(";", 1)[0].strip().lower()
            if script_type == "application/ld+json":
                self._capture_json_ld = True
                self._json_ld_chunks = []

    def handle_data(self, data: str) -> None:
        if self._capture_json_ld:
            self._json_ld_chunks.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "script" and self._capture_json_ld:
            blob = "".join(self._json_ld_chunks).strip()
            if blob:
                self.json_ld_blobs.append(blob)
            self._capture_json_ld = False
            self._json_ld_chunks = []


def _normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_only = normalized.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", " ", ascii_only.lower()).strip()


def _normalize_source_url(url: str | None) -> str | None:
    if not url:
        return None
    parsed = urlparse(url.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    path = parsed.path or "/"
    cleaned = parsed._replace(fragment="", params="", path=path.rstrip("/") or "/")
    return cleaned.geturl()


def _normalize_name(value: str) -> str:
    return _normalize_text(value)


def _is_valid_image_candidate(url: str, *, width: int | None = None, height: int | None = None) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return False

    lower = url.lower()
    if lower.endswith(".svg"):
        return False
    if any(marker in lower for marker in _INVALID_IMAGE_MARKERS):
        return False
    if width is not None and height is not None and min(width, height) < 150:
        return False
    return True


def _coerce_int(value: str | None) -> int | None:
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _resolve_image_candidate(
    raw_url: str | None,
    *,
    page_url: str,
    width: int | None = None,
    height: int | None = None,
) -> str | None:
    if not raw_url:
        return None
    resolved = urljoin(page_url, raw_url.strip())
    if not _is_valid_image_candidate(resolved, width=width, height=height):
        return None
    return resolved


def _meta_content(meta_tags: list[dict[str, str]], key: str) -> str | None:
    lowered_key = key.lower()
    for attrs in meta_tags:
        if attrs.get("property", "").lower() == lowered_key:
            return attrs.get("content")
        if attrs.get("name", "").lower() == lowered_key:
            return attrs.get("content")
    return None


def _extract_json_ld_images(value: object) -> list[str]:
    images: list[str] = []

    def visit(node: object) -> None:
        if isinstance(node, str):
            images.append(node)
            return
        if isinstance(node, list):
            for item in node:
                visit(item)
            return
        if not isinstance(node, dict):
            return

        node_type = str(node.get("@type", "")).lower()
        if node_type == "imageobject":
            for key in ("url", "contentUrl"):
                candidate = node.get(key)
                if isinstance(candidate, str):
                    images.append(candidate)

        if "image" in node:
            visit(node["image"])

        for key, nested in node.items():
            if key != "image":
                visit(nested)

    visit(value)
    return images


def extract_image_url_from_html(page_url: str, html_text: str) -> str | None:
    parser = _PageMetadataParser()
    parser.feed(html_text)

    og_image = _resolve_image_candidate(
        _meta_content(parser.meta_tags, "og:image"),
        page_url=page_url,
        width=_coerce_int(_meta_content(parser.meta_tags, "og:image:width")),
        height=_coerce_int(_meta_content(parser.meta_tags, "og:image:height")),
    )
    if og_image:
        return og_image

    twitter_image = _resolve_image_candidate(
        _meta_content(parser.meta_tags, "twitter:image"),
        page_url=page_url,
    )
    if twitter_image:
        return twitter_image

    seen: set[str] = set()
    for blob in parser.json_ld_blobs:
        try:
            payload = json.loads(blob)
        except json.JSONDecodeError:
            continue
        for candidate in _extract_json_ld_images(payload):
            resolved = _resolve_image_candidate(candidate, page_url=page_url)
            if resolved and resolved not in seen:
                return resolved
            if resolved:
                seen.add(resolved)

    for attrs in parser.link_tags:
        rel = attrs.get("rel", "").lower()
        if rel != "image_src":
            continue
        resolved = _resolve_image_candidate(attrs.get("href"), page_url=page_url)
        if resolved:
            return resolved

    return None


def _normalize_collection(
    items: list[T],
    *,
    minimum_linked_items: int,
    update: Callable[[T, str | None], T],
    item_label: str,
) -> list[T]:
    unique: list[T] = []
    seen_urls: set[str] = set()
    seen_names: set[str] = set()

    for item in items:
        normalized_source = _normalize_source_url(getattr(item, "source_url", None))
        normalized_name = _normalize_name(item.name)

        if normalized_source and normalized_source in seen_urls:
            continue
        if normalized_name and normalized_name in seen_names:
            continue

        if normalized_source:
            seen_urls.add(normalized_source)
        if normalized_name:
            seen_names.add(normalized_name)

        unique.append(update(item, normalized_source))

    linked = [item for item in unique if getattr(item, "source_url", None)]
    unlinked = [item for item in unique if not getattr(item, "source_url", None)]

    if len(linked) >= minimum_linked_items:
        dropped = len(unique) - len(linked)
        if dropped:
            log.info("Dropped %d %s item(s) without source_url after normalization", dropped, item_label)
        return linked

    return linked + unlinked


def normalize_activities_output(output: ActivitiesOutput) -> ActivitiesOutput:
    normalized = _normalize_collection(
        output.activities,
        minimum_linked_items=_MIN_LINKED_ITEMS,
        update=lambda item, source_url: item.model_copy(update={"source_url": source_url}),
        item_label="activity",
    )
    return ActivitiesOutput(activities=normalized)


def normalize_food_output(output: FoodOutput) -> FoodOutput:
    normalized = _normalize_collection(
        output.picks,
        minimum_linked_items=_MIN_LINKED_ITEMS,
        update=lambda item, source_url: item.model_copy(update={"source_url": source_url}),
        item_label="food",
    )
    return FoodOutput(picks=normalized)


async def _fetch_image_url(client: httpx.AsyncClient, source_url: str) -> str | None:
    try:
        response = await client.get(source_url, follow_redirects=True, timeout=_FETCH_TIMEOUT_SECONDS)
        response.raise_for_status()
    except Exception as exc:
        log.warning("Could not fetch content page %s: %s", source_url, exc)
        return None
    return extract_image_url_from_html(str(response.url), response.text)


async def _enrich_collection(
    items: list[T],
    *,
    update: Callable[[T, str | None], T],
) -> list[T]:
    semaphore = asyncio.Semaphore(_FETCH_CONCURRENCY)

    async with httpx.AsyncClient(headers=_FETCH_HEADERS) as client:
        async def enrich_one(item: T) -> T:
            source_url = getattr(item, "source_url", None)
            if not source_url or getattr(item, "image_url", None):
                return item

            async with semaphore:
                image_url = await _fetch_image_url(client, source_url)
            return update(item, image_url)

        return await asyncio.gather(*(enrich_one(item) for item in items))


async def enrich_activities_output(output: ActivitiesOutput) -> ActivitiesOutput:
    if not output.activities:
        return output
    enriched = await _enrich_collection(
        output.activities,
        update=lambda item, image_url: item.model_copy(update={"image_url": image_url}),
    )
    return ActivitiesOutput(activities=enriched)


async def enrich_food_output(output: FoodOutput) -> FoodOutput:
    if not output.picks:
        return output
    enriched = await _enrich_collection(
        output.picks,
        update=lambda item, image_url: item.model_copy(update={"image_url": image_url}),
    )
    return FoodOutput(picks=enriched)
