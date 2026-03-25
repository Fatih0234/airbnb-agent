from __future__ import annotations

import logging
import re
from typing import Any, TypedDict
from urllib.parse import urlparse

from .mcp_client import create_tavily_mcp_server

log = logging.getLogger("neighborhood_search")

SAFETY_AREA_FIT_TOPIC = "safety_area_fit"
WALKABILITY_CAVEATS_TOPIC = "walkability_caveats"

SEARCH_RESULTS_PER_QUERY = 5
EVIDENCE_PER_TOPIC_LIMIT = 3
TOTAL_EVIDENCE_LIMIT = 6

_TOKEN_RE = re.compile(r"[a-z0-9]+")
_WHITESPACE_RE = re.compile(r"\s+")
_TAVILY_TEXT_RESULT_RE = re.compile(
    r"Title:\s*(?P<title>.*?)\nURL:\s*(?P<url>\S+)\nContent:\s*(?P<content>.*?)(?=\nTitle:\s*|\Z)",
    re.DOTALL,
)
_SEPARATOR_RE = re.compile(r"\s(?:\||-|—|–)\s")
_MAX_TITLE_LENGTH = 120
_MAX_SNIPPET_LENGTH = 280


class NeighborhoodSearchQuery(TypedDict):
    topic: str
    query: str


class NeighborhoodEvidenceItem(TypedDict):
    title: str
    url: str
    snippet: str
    source_domain: str
    topic: str
    query: str
    query_index: int
    result_index: int


class NeighborhoodEvidencePayload(TypedDict):
    queries: list[NeighborhoodSearchQuery]
    query_count: int
    failed_queries: int
    raw_result_count: int
    extracted_evidence_count: int
    evidence_count: int
    evidence_by_topic: dict[str, list[NeighborhoodEvidenceItem]]


def _normalize_text(value: str) -> str:
    return " ".join(_TOKEN_RE.findall(value.lower()))


def _truncate(value: str, limit: int) -> str:
    trimmed = value.strip()
    if len(trimmed) <= limit:
        return trimmed
    return f"{trimmed[: limit - 1].rstrip()}…"


def _clean_text(value: str | None, *, limit: int) -> str:
    if not value or not isinstance(value, str):
        return ""
    compact = _WHITESPACE_RE.sub(" ", value).strip()
    return _truncate(compact, limit)


def _clean_title(value: str | None) -> str:
    title = _clean_text(value, limit=_MAX_TITLE_LENGTH)
    if not title:
        return ""
    match = _SEPARATOR_RE.search(title)
    if match is None:
        return title
    return title[: match.start()].strip()


def _clean_snippet(value: str | None) -> str:
    return _clean_text(value, limit=_MAX_SNIPPET_LENGTH)


def _fallback_title(snippet: str) -> str:
    if not snippet:
        return ""
    if len(snippet) <= 80:
        return snippet
    return f"{snippet[:79].rstrip()}…"


def _candidate_snippet(result: dict[str, Any]) -> str:
    for key in ("content", "snippet", "description", "raw_content"):
        snippet = _clean_snippet(result.get(key))
        if snippet:
            return snippet
    return ""


def _normalized_source_url(value: str | None) -> str | None:
    if not value or not isinstance(value, str):
        return None
    parsed = urlparse(value.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    return parsed._replace(fragment="").geturl()


def _source_domain(url: str) -> str:
    parsed = urlparse(url)
    return parsed.netloc.lower().removeprefix("www.")


def _string_result_items(search_result: str) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    for match in _TAVILY_TEXT_RESULT_RE.finditer(search_result):
        title = _clean_title(match.group("title"))
        url = match.group("url").strip()
        content = _clean_snippet(match.group("content"))
        if url and (title or content):
            items.append({"title": title, "url": url, "content": content})
    return items


def build_neighborhood_search_queries(
    destination: str,
    trip_type: str,
) -> list[NeighborhoodSearchQuery]:
    trip_label = trip_type.replace("_", " ")
    return [
        {
            "topic": SAFETY_AREA_FIT_TOPIC,
            "query": f"{destination} neighborhood safety area fit best areas for {trip_label} travelers",
        },
        {
            "topic": WALKABILITY_CAVEATS_TOPIC,
            "query": f"{destination} walkability public transit hills noise practical caveats",
        },
    ]


def extract_neighborhood_evidence(
    search_result: object,
    *,
    topic: str,
    query: str,
    query_index: int,
) -> list[NeighborhoodEvidenceItem]:
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

    evidence: list[NeighborhoodEvidenceItem] = []
    for result_index, item in enumerate(raw_results):
        url = _normalized_source_url(item.get("url"))
        if url is None:
            continue

        title = _clean_title(item.get("title"))
        snippet = _candidate_snippet(item)
        if not title and not snippet:
            continue

        evidence.append(
            NeighborhoodEvidenceItem(
                title=title or _fallback_title(snippet),
                url=url,
                snippet=snippet or title,
                source_domain=_source_domain(url),
                topic=topic,
                query=query,
                query_index=query_index,
                result_index=result_index,
            )
        )

    return evidence


def dedupe_and_limit_neighborhood_evidence(
    evidence: list[NeighborhoodEvidenceItem],
    *,
    per_topic_limit: int = EVIDENCE_PER_TOPIC_LIMIT,
    total_limit: int = TOTAL_EVIDENCE_LIMIT,
) -> dict[str, list[NeighborhoodEvidenceItem]]:
    ordered = sorted(
        evidence,
        key=lambda item: (item["query_index"], item["result_index"], item["title"]),
    )
    by_topic: dict[str, list[NeighborhoodEvidenceItem]] = {
        SAFETY_AREA_FIT_TOPIC: [],
        WALKABILITY_CAVEATS_TOPIC: [],
    }
    seen_urls: set[str] = set()
    seen_titles: set[str] = set()
    total = 0

    for item in ordered:
        if total >= total_limit:
            break

        topic = item["topic"]
        bucket = by_topic.get(topic)
        if bucket is None or len(bucket) >= per_topic_limit:
            continue

        title_key = _normalize_text(item["title"])
        if item["url"] in seen_urls or (title_key and title_key in seen_titles):
            continue

        seen_urls.add(item["url"])
        if title_key:
            seen_titles.add(title_key)

        bucket.append(item)
        total += 1

    return by_topic


async def _search_neighborhood(query: str) -> object | None:
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
        log.warning("Tavily neighborhood search failed for '%s': %s", query, exc)
        return None


async def collect_neighborhood_evidence(
    *,
    destination: str,
    trip_type: str,
) -> NeighborhoodEvidencePayload:
    queries = build_neighborhood_search_queries(destination, trip_type)
    all_evidence: list[NeighborhoodEvidenceItem] = []
    raw_result_count = 0
    failed_queries = 0

    for query_index, search_query in enumerate(queries):
        response = await _search_neighborhood(search_query["query"])
        if response is None:
            failed_queries += 1
            continue

        if isinstance(response, dict):
            raw_results = response.get("results")
            if isinstance(raw_results, list):
                raw_result_count += len(raw_results)
        elif isinstance(response, str):
            raw_result_count += len(_string_result_items(response))

        all_evidence.extend(
            extract_neighborhood_evidence(
                response,
                topic=search_query["topic"],
                query=search_query["query"],
                query_index=query_index,
            )
        )

    evidence_by_topic = dedupe_and_limit_neighborhood_evidence(all_evidence)
    evidence_count = sum(len(bucket) for bucket in evidence_by_topic.values())
    return NeighborhoodEvidencePayload(
        queries=queries,
        query_count=len(queries),
        failed_queries=failed_queries,
        raw_result_count=raw_result_count,
        extracted_evidence_count=len(all_evidence),
        evidence_count=evidence_count,
        evidence_by_topic=evidence_by_topic,
    )
