from __future__ import annotations

import logging
import re
from typing import Any, TypedDict
from urllib.parse import urlparse

from .mcp_client import create_tavily_mcp_server

log = logging.getLogger("food_search")

SEARCH_MAX_QUERIES = 2
SEARCH_RESULTS_PER_QUERY = 5
MODEL_CANDIDATE_LIMIT = 10

_TOKEN_RE = re.compile(r"[a-z0-9]+")
_PHRASE_SPLIT_RE = re.compile(r"[.;]|,|\b(?:and|plus|with|then|also)\b", re.IGNORECASE)
_WHITESPACE_RE = re.compile(r"\s+")
_TAVILY_TEXT_RESULT_RE = re.compile(
    r"Title:\s*(?P<title>.*?)\nURL:\s*(?P<url>\S+)\nContent:\s*(?P<content>.*?)(?=\nTitle:\s*|\Z)",
    re.DOTALL,
)
_LEADING_FILLER_RE = re.compile(
    r"^(?:prioritize|priority|focus on|focused on|looking for|want|wants|need|needs|"
    r"one|some|great|standout|best|local|easy|cozy|good)\s+",
    re.IGNORECASE,
)
_IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif")
_PRICE_RANGE_RE = re.compile(r"\${1,4}")

_FOOD_HINTS = {
    "restaurant",
    "restaurants",
    "food",
    "dinner",
    "lunch",
    "brunch",
    "breakfast",
    "tasting menu",
    "coffee",
    "cafe",
    "pastry",
    "bakery",
    "bar",
    "cocktail",
    "wine",
    "dessert",
    "market",
    "chef",
    "michelin",
    "family-friendly",
    "romantic",
    "business lunch",
}

_TRIP_TYPE_HINTS: dict[str, tuple[str, ...]] = {
    "business": ("business lunch", "coffee near downtown"),
    "event_based": ("pre-show dinner", "late-night food"),
    "family": ("family-friendly restaurants", "casual lunch"),
    "romantic": ("romantic dinner", "wine bar"),
    "vacation": ("local restaurants", "best cafes"),
    "weekend_getaway": ("best brunch", "local restaurants"),
    "workcation": ("coffee shops", "great lunch spots"),
}

_CUISINE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "Cafe": ("coffee", "cafe", "espresso", "pastry"),
    "Bar": ("bar", "cocktail", "wine"),
    "French": ("french", "bistro", "brasserie"),
    "Italian": ("italian", "pasta", "pizza", "osteria", "trattoria"),
    "Japanese": ("japanese", "sushi", "izakaya", "ramen", "omakase"),
    "Mexican": ("mexican", "taco", "taqueria", "mezcal"),
    "Mediterranean": ("mediterranean", "greek", "levantine", "mezze"),
    "Seafood": ("seafood", "oyster", "fish", "shellfish"),
    "Steakhouse": ("steakhouse", "steak", "grill"),
    "Vegetarian": ("vegetarian", "vegan", "plant-based"),
}

_PRICE_KEYWORDS: tuple[tuple[str, str], ...] = (
    ("$$$", "michelin"),
    ("$$$", "fine dining"),
    ("$$$", "tasting menu"),
    ("$$$", "upscale"),
    ("$$$", "luxury"),
    ("$", "budget"),
    ("$", "cheap"),
    ("$", "street food"),
    ("$", "casual"),
    ("$", "affordable"),
    ("$$", "brunch"),
    ("$$", "cafe"),
    ("$$", "bistro"),
    ("$$", "neighborhood spot"),
    ("$$", "family-friendly"),
)


class FoodCandidate(TypedDict, total=False):
    name: str
    cuisine_type: str
    price_range: str
    description: str
    image_url: str | None
    source_url: str | None
    query: str
    query_index: int
    result_index: int
    score: int


def _normalize_text(value: str) -> str:
    return " ".join(_TOKEN_RE.findall(value.lower()))


def _tokenize(value: str) -> list[str]:
    return _TOKEN_RE.findall(value.lower())


def _clean_phrase(value: str) -> str:
    cleaned = _LEADING_FILLER_RE.sub("", value.strip())
    cleaned = cleaned.strip(" -:|")
    cleaned = _WHITESPACE_RE.sub(" ", cleaned)
    return cleaned


def _looks_like_image_url(value: str | None) -> bool:
    if not value or not isinstance(value, str):
        return False
    parsed = urlparse(value.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return False
    return parsed.path.lower().endswith(_IMAGE_EXTENSIONS)


def _clean_title(value: str | None) -> str:
    if not value or not isinstance(value, str):
        return ""
    title = value.strip()
    for separator in (" | ", " - ", " — ", " – "):
        if separator in title:
            title = title.split(separator, 1)[0].strip()
            break
    return title


def _food_phrase_score(phrase: str) -> int:
    lower = phrase.lower()
    score = 0
    for hint in _FOOD_HINTS:
        if hint in lower:
            score += 3 if " " in hint else 2
    token_count = len(_tokenize(phrase))
    if 2 <= token_count <= 10:
        score += 1
    if token_count > 14:
        score -= 2
    return score


def build_food_search_queries(
    destination: str,
    trip_type: str,
    time_preferences: str,
) -> list[str]:
    phrases: list[str] = []
    for raw_phrase in _PHRASE_SPLIT_RE.split(time_preferences or ""):
        phrase = _clean_phrase(raw_phrase)
        if phrase:
            phrases.append(phrase)

    scored_phrases = sorted(
        ((phrase, _food_phrase_score(phrase)) for phrase in phrases),
        key=lambda item: (-item[1], len(item[0])),
    )
    useful_phrases = [phrase for phrase, score in scored_phrases if score > 0]

    if not useful_phrases:
        useful_phrases = list(_TRIP_TYPE_HINTS.get(trip_type, ("local restaurants",)))

    queries: list[str] = []
    for phrase in useful_phrases[:SEARCH_MAX_QUERIES]:
        query = f"best restaurants in {destination} {phrase}"
        if query not in queries:
            queries.append(query)

    if not queries:
        queries.append(f"best restaurants in {destination}")

    return queries[:SEARCH_MAX_QUERIES]


def _candidate_description(result: dict[str, Any]) -> str:
    for key in ("content", "snippet", "description", "raw_content"):
        value = result.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _string_result_items(search_result: str) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    for match in _TAVILY_TEXT_RESULT_RE.finditer(search_result):
        title = match.group("title").strip()
        url = match.group("url").strip()
        content = _WHITESPACE_RE.sub(" ", match.group("content").strip())
        if title and url:
            items.append({"title": title, "url": url, "content": content})
    return items


def _candidate_image_url(result: dict[str, Any]) -> str | None:
    for key in ("image_url", "image", "thumbnail_url", "thumbnail"):
        value = result.get(key)
        if _looks_like_image_url(value):
            return str(value).strip()
    return None


def _infer_cuisine_type(*values: str) -> str:
    haystack = " ".join(value for value in values if value).lower()
    for cuisine_type, keywords in _CUISINE_KEYWORDS.items():
        if any(keyword in haystack for keyword in keywords):
            return cuisine_type
    return "Restaurant"


def _infer_price_range(result: dict[str, Any], *values: str) -> str:
    explicit_sources: list[str] = []
    for key in ("price", "price_range", "cost"):
        value = result.get(key)
        if isinstance(value, str) and value.strip():
            explicit_sources.append(value.strip())

    haystack = " ".join(explicit_sources + [value for value in values if value])
    price_match = _PRICE_RANGE_RE.search(haystack)
    if price_match:
        return "$" * min(len(price_match.group(0)), 3)

    lower = haystack.lower()
    for price_range, keyword in _PRICE_KEYWORDS:
        if keyword in lower:
            return price_range

    return "$$"


def extract_food_candidates(
    search_result: object,
    *,
    query: str,
    query_index: int,
) -> list[FoodCandidate]:
    raw_results: list[dict[str, Any]]
    if isinstance(search_result, dict):
        raw = search_result.get("results")
        if not isinstance(raw, list):
            return []
        raw_results = [item for item in raw if isinstance(item, dict)]
    elif isinstance(search_result, str):
        raw_results = _string_result_items(search_result)
    else:
        return []

    extracted: list[FoodCandidate] = []
    for result_index, item in enumerate(raw_results):
        source_url = item.get("url")
        if not isinstance(source_url, str) or not source_url.strip():
            continue

        name = _clean_title(item.get("title"))
        description = _candidate_description(item)
        if not name and not description:
            continue

        extracted.append(
            FoodCandidate(
                name=name or description[:80],
                cuisine_type=_infer_cuisine_type(query, name, description),
                price_range=_infer_price_range(item, query, name, description),
                description=description or name,
                image_url=_candidate_image_url(item),
                source_url=source_url.strip(),
                query=query,
                query_index=query_index,
                result_index=result_index,
            )
        )

    return extracted


def _candidate_score(candidate: FoodCandidate) -> int:
    query_tokens = set(_tokenize(candidate.get("query", "")))
    body_tokens = set(
        _tokenize(
            " ".join(
                [
                    candidate.get("name", ""),
                    candidate.get("description", ""),
                    candidate.get("cuisine_type", ""),
                    candidate.get("price_range", ""),
                ]
            )
        )
    )
    overlap = len(query_tokens & body_tokens)
    return (SEARCH_MAX_QUERIES - candidate.get("query_index", 0)) * 100 + overlap * 10 - candidate.get("result_index", 0)


def _normalized_source_url(value: str | None) -> str | None:
    if not value:
        return None
    parsed = urlparse(value.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    return parsed._replace(fragment="").geturl()


def _candidate_name_key(value: str) -> str:
    return _normalize_text(value)


def dedupe_and_limit_food_candidates(
    candidates: list[FoodCandidate],
    *,
    limit: int = MODEL_CANDIDATE_LIMIT,
) -> list[FoodCandidate]:
    scored = [
        FoodCandidate(
            **candidate,
            score=_candidate_score(candidate),
        )
        for candidate in candidates
        if candidate.get("source_url") and (candidate.get("name") or candidate.get("description"))
    ]
    scored.sort(key=lambda candidate: (-candidate["score"], candidate.get("query_index", 0), candidate.get("result_index", 0)))

    deduped: list[FoodCandidate] = []
    seen_urls: set[str] = set()
    seen_names: set[str] = set()

    for candidate in scored:
        normalized_url = _normalized_source_url(candidate.get("source_url"))
        name_key = _candidate_name_key(candidate.get("name", ""))

        if normalized_url and normalized_url in seen_urls:
            continue
        if name_key and name_key in seen_names:
            continue

        if normalized_url:
            seen_urls.add(normalized_url)
        if name_key:
            seen_names.add(name_key)

        deduped.append(candidate)
        if len(deduped) >= limit:
            break

    return deduped


async def _search_food(query: str) -> object | None:
    server = create_tavily_mcp_server()
    try:
        return await server.direct_call_tool(
            "tavily_search",
            {
                "query": query,
                "max_results": SEARCH_RESULTS_PER_QUERY,
                "search_depth": "advanced",
                "include_images": False,
                "include_raw_content": False,
            },
        )
    except Exception as exc:
        log.warning("Tavily food search failed for '%s': %s", query, exc)
        return None


async def collect_food_candidates(
    *,
    destination: str,
    trip_type: str,
    time_preferences: str,
    limit: int = MODEL_CANDIDATE_LIMIT,
) -> tuple[list[FoodCandidate], dict[str, object]]:
    queries = build_food_search_queries(destination, trip_type, time_preferences)
    all_candidates: list[FoodCandidate] = []
    raw_result_count = 0
    failed_queries = 0

    for query_index, query in enumerate(queries):
        response = await _search_food(query)
        if response is None:
            failed_queries += 1
            continue

        if isinstance(response, dict):
            raw_results = response.get("results")
            if isinstance(raw_results, list):
                raw_result_count += len(raw_results)
        elif isinstance(response, str):
            raw_result_count += len(_string_result_items(response))

        all_candidates.extend(
            extract_food_candidates(
                response,
                query=query,
                query_index=query_index,
            )
        )

    limited = dedupe_and_limit_food_candidates(all_candidates, limit=limit)
    metadata = {
        "queries": queries,
        "query_count": len(queries),
        "failed_queries": failed_queries,
        "raw_result_count": raw_result_count,
        "extracted_candidate_count": len(all_candidates),
        "model_candidate_count": len(limited),
    }
    return limited, metadata
