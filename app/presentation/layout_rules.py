from __future__ import annotations

from collections.abc import Sequence


HERO_MAX_METRICS = 3
RECOMMENDATION_MAX_REASONS = 3
NEIGHBORHOOD_MAX_NOTES = 4
LOGISTICS_MAX_ROWS = 5
ACTIVITY_VISIBLE_CARDS = 4
FOOD_VISIBLE_CARDS = 4
COMPARISON_MAX_STAYS = 10
NEIGHBORHOOD_TRUNCATE_WORDS = 25
CARD_IMAGE_HEIGHT = 210
STAY_IMAGE_HEIGHT = 250
MAP_IMAGE_HEIGHT = 320


def cap_items(items: Sequence[object], limit: int) -> list[object]:
    return list(items[:limit])


def split_visible(items: Sequence[object], visible_count: int) -> tuple[list[object], list[object]]:
    visible = list(items[:visible_count])
    hidden = list(items[visible_count:])
    return visible, hidden
