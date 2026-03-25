from __future__ import annotations

import logging
import re
from typing import Any, TypedDict
from urllib.parse import urlparse

from .mcp_client import create_tavily_mcp_server

log = logging.getLogger("activity_search")

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
    r"one|some|great|standout|easy|safe|daytime|nighttime|late-night)\s+",
    re.IGNORECASE,
)
_IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif")

_CATEGORY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "nightlife": ("nightlife", "late night", "cocktail", "bar", "club", "concert", "music", "live music"),
    "cultural": ("museum", "gallery", "art", "architecture", "historic", "history", "cultural", "exhibit"),
    "food": ("taco", "food", "dinner", "restaurant", "coffee", "cafe", "market", "culinary"),
    "outdoor": ("park", "outdoor", "hike", "walking", "bike", "garden", "canal", "boat"),
    "sports": ("sports", "stadium", "game", "surf", "cycling", "climb"),
    "sightseeing": ("landmark", "viewpoint", "neighborhood", "square", "tour", "attraction", "visit"),
}
_ACTIVITY_HINTS = {
    keyword
    for keywords in _CATEGORY_KEYWORDS.values()
    for keyword in keywords
}
_TRIP_TYPE_HINTS: dict[str, tuple[str, str]] = {
    "event_based": ("live music", "nightlife"),
    "romantic": ("romantic walk", "art"),
    "family": ("family friendly", "museum"),
    "business": ("coffee", "walkable sightseeing"),
    "weekend_getaway": ("top attractions", "local food"),
}


class ActivityCandidate(TypedDict, total=False):
    name: str
    description: str
    source_url: str | None
    category: str
    image_url: str | None
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
    lower = parsed.path.lower()
    return lower.endswith(_IMAGE_EXTENSIONS)


def _clean_title(value: str | None) -> str:
    if not value or not isinstance(value, str):
        return ""
    title = value.strip()
    for separator in (" | ", " - ", " — ", " – "):
        if separator in title:
            title = title.split(separator, 1)[0].strip()
            break
    return title


def _activity_phrase_score(phrase: str) -> int:
    lower = phrase.lower()
    score = 0
    for hint in _ACTIVITY_HINTS:
        if hint in lower:
            score += 3 if " " in hint else 2
    token_count = len(_tokenize(phrase))
    if 2 <= token_count <= 10:
        score += 1
    if token_count > 14:
        score -= 2
    return score


def build_activity_search_queries(
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
        ((phrase, _activity_phrase_score(phrase)) for phrase in phrases),
        key=lambda item: (-item[1], len(item[0])),
    )
    useful_phrases = [phrase for phrase, score in scored_phrases if score > 0]

    if not useful_phrases:
        trip_hints = _TRIP_TYPE_HINTS.get(trip_type, ("top attractions",))
        useful_phrases = list(trip_hints)

    queries: list[str] = []
    for phrase in useful_phrases[:SEARCH_MAX_QUERIES]:
        query = f"best things to do in {destination} {phrase}"
        if query not in queries:
            queries.append(query)

    if not queries:
        queries.append(f"best things to do in {destination}")

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


def _infer_category(*values: str) -> str:
    haystack = " ".join(value for value in values if value).lower()
    for category, keywords in _CATEGORY_KEYWORDS.items():
        if any(keyword in haystack for keyword in keywords):
            return category
    return "sightseeing"


def extract_activity_candidates(
    search_result: object,
    *,
    query: str,
    query_index: int,
) -> list[ActivityCandidate]:
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

    extracted: list[ActivityCandidate] = []
    for result_index, item in enumerate(raw_results):
        source_url = item.get("url")
        if not isinstance(source_url, str) or not source_url.strip():
            continue

        name = _clean_title(item.get("title"))
        description = _candidate_description(item)
        if not name and not description:
            continue

        extracted.append(
            ActivityCandidate(
                name=name or description[:80],
                description=description or name,
                source_url=source_url.strip(),
                category=_infer_category(query, name, description),
                image_url=_candidate_image_url(item),
                query=query,
                query_index=query_index,
                result_index=result_index,
            )
        )

    return extracted


def _candidate_score(candidate: ActivityCandidate) -> int:
    query_tokens = set(_tokenize(candidate.get("query", "")))
    body_tokens = set(
        _tokenize(
            " ".join(
                [
                    candidate.get("name", ""),
                    candidate.get("description", ""),
                    candidate.get("category", ""),
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


def dedupe_and_limit_activity_candidates(
    candidates: list[ActivityCandidate],
    *,
    limit: int = MODEL_CANDIDATE_LIMIT,
) -> list[ActivityCandidate]:
    scored = [
        ActivityCandidate(
            **candidate,
            score=_candidate_score(candidate),
        )
        for candidate in candidates
        if candidate.get("source_url") and (candidate.get("name") or candidate.get("description"))
    ]
    scored.sort(key=lambda candidate: (-candidate["score"], candidate.get("query_index", 0), candidate.get("result_index", 0)))

    deduped: list[ActivityCandidate] = []
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


async def _search_activities(query: str) -> object | None:
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
        log.warning("Tavily activity search failed for '%s': %s", query, exc)
        return None


async def collect_activity_candidates(
    *,
    destination: str,
    trip_type: str,
    time_preferences: str,
    limit: int = MODEL_CANDIDATE_LIMIT,
) -> tuple[list[ActivityCandidate], dict[str, object]]:
    queries = build_activity_search_queries(destination, trip_type, time_preferences)
    all_candidates: list[ActivityCandidate] = []
    raw_result_count = 0
    failed_queries = 0

    for query_index, query in enumerate(queries):
        response = await _search_activities(query)
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
            extract_activity_candidates(
                response,
                query=query,
                query_index=query_index,
            )
        )

    limited = dedupe_and_limit_activity_candidates(all_candidates, limit=limit)
    metadata = {
        "queries": queries,
        "query_count": len(queries),
        "failed_queries": failed_queries,
        "raw_result_count": raw_result_count,
        "extracted_candidate_count": len(all_candidates),
        "model_candidate_count": len(limited),
    }
    return limited, metadata
