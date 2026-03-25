from __future__ import annotations

from functools import lru_cache
import logging

from geopy.exc import GeocoderServiceError, GeocoderTimedOut, GeocoderUnavailable
from geopy.geocoders import Nominatim

log = logging.getLogger("geocoding")

_GEOCODER = Nominatim(user_agent="liveaudio-airbnb-assistant/0.1")


@lru_cache(maxsize=128)
def geocode_destination_center(destination: str) -> tuple[float, float] | None:
    query = destination.strip()
    if not query:
        return None

    try:
        location = _GEOCODER.geocode(query, exactly_one=True, language="en")
    except (GeocoderTimedOut, GeocoderUnavailable, GeocoderServiceError) as exc:
        log.warning("Destination center geocode failed for '%s': %s", query, exc)
        return None

    if location is None:
        return None

    return float(location.latitude), float(location.longitude)
