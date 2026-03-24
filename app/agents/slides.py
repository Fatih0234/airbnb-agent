from __future__ import annotations

import html
import os
from urllib.parse import urlparse

from ..schemas import CurationOutput


_PALETTES: dict[str, dict[str, str]] = {
    "historic": {"primary": "#8B4513", "accent": "#D2691E", "bg": "#FFF8F0", "text": "#3D1C02"},
    "coastal": {"primary": "#1E6B8C", "accent": "#4A9EBF", "bg": "#F0F7FA", "text": "#0D3347"},
    "urban": {"primary": "#1A1A2E", "accent": "#4A90D9", "bg": "#F4F4F4", "text": "#111111"},
    "mountain": {"primary": "#2D5016", "accent": "#6B8E23", "bg": "#F5F5F0", "text": "#1A2E0A"},
    "tropical": {"primary": "#007A7A", "accent": "#FF6B6B", "bg": "#FFFDF0", "text": "#003D3D"},
    "cosmopolitan": {"primary": "#2C2C2C", "accent": "#C9A84C", "bg": "#FAFAFA", "text": "#111111"},
    "romantic": {"primary": "#722F37", "accent": "#C8647A", "bg": "#FFF5F5", "text": "#3D0A10"},
}
_DEFAULT_PALETTE = {"primary": "#2C3E50", "accent": "#3498DB", "bg": "#F8F9FA", "text": "#1A252F"}


def _get_palette(vibe: str) -> dict[str, str]:
    key = vibe.lower().strip()
    for palette_name, palette in _PALETTES.items():
        if palette_name in key or key in palette_name:
            return palette
    return _DEFAULT_PALETTE


def _escape(value: str | None) -> str:
    return html.escape(value or "")


def _format_money(value: float | None) -> str:
    if value is None:
        return "N/A"
    if value.is_integer():
        return f"${int(value)}"
    return f"${value:.0f}"


def _format_duration(minutes: int) -> str:
    hours, remainder = divmod(minutes, 60)
    if hours and remainder:
        return f"{hours}h {remainder}m"
    if hours:
        return f"{hours}h"
    return f"{remainder}m"


def _format_stops(stops: int) -> str:
    if stops == 0:
        return "Non-stop"
    if stops == 1:
        return "1 stop"
    return f"{stops} stops"


def _price_badge_color(price_range: str) -> str:
    return {
        "$": "#2E7D32",
        "$$": "#D68910",
        "$$$": "#C0392B",
    }.get(price_range, "#7F8C8D")


def _fix_map_url(map_url: str | None) -> str | None:
    if not map_url:
        return None
    real_key = os.getenv("GOOGLE_MAPS_API_KEY", "")
    if "YOUR_API_KEY" in map_url and real_key:
        return map_url.replace("YOUR_API_KEY", real_key)
    return map_url


def _image_wrap(label: str, image_url: str | None, height: int) -> str:
    img = ""
    if image_url:
        safe_url = _escape(image_url)
        safe_label = _escape(label)
        img = (
            f'<img src="{safe_url}" alt="{safe_label}" loading="lazy" '
            'onerror="this.style.opacity=0">'
        )
    return (
        f'<div class="img-wrap" style="height:{height}px" data-label="{_escape(label)}">'
        f"{img}</div>"
    )


def _source_host(source_url: str | None) -> str:
    if not source_url:
        return ""
    host = urlparse(source_url).netloc.lower()
    return host[4:] if host.startswith("www.") else host


def _source_cta(source_url: str | None) -> str:
    if not source_url:
        return ""
    host = _source_host(source_url)
    host_line = f'<p class="source-host">{_escape(host)}</p>' if host else ""
    return (
        f'{host_line}'
        f'<a href="{_escape(source_url)}" class="button source-button" target="_blank" rel="noreferrer">Visit link →</a>'
    )


def _render_cover(result: CurationOutput) -> str:
    return f"""
    <section id="cover" class="cover">
      <div class="cover-inner">
        <p class="eyebrow">Travel Brief</p>
        <h1>{_escape(result.destination)}</h1>
        <p class="cover-meta">{_escape(result.dates)} · {_escape(result.trip_type.replace('_', ' '))} · {result.guests} guest(s)</p>
        <div class="vibe-pill">{_escape(result.destination_vibe)}</div>
      </div>
    </section>
    """


def _render_stays(result: CurationOutput) -> str:
    if result.stays is None or not result.stays.stays:
        return ""
    cards = []
    for stay in result.stays.stays:
        rating = f"★ {stay.rating:.2f}" if stay.rating is not None else "Rating unavailable"
        url = stay.url or "#"
        disabled = ' aria-disabled="true" class="button button-disabled"' if stay.url is None else ' class="button"'
        amenities = "".join(f'<span class="chip">{_escape(item)}</span>' for item in stay.amenities)
        cards.append(
            f"""
            <article class="card stay-card">
              {_image_wrap(stay.name, stay.image_urls[0] if stay.image_urls else None, 180)}
              <div class="card-body">
                <h3>{_escape(stay.name)}</h3>
                <p class="muted">{_escape(stay.location_description)}</p>
                <p class="rating">{_escape(rating)}</p>
                <div class="price-row">
                  <strong>{_escape(_format_money(stay.price_per_night))}<span>/night</span></strong>
                  <span>Total { _escape(_format_money(stay.total_price)) }</span>
                </div>
                <div class="chip-row">{amenities}</div>
                <a href="{_escape(url)}"{disabled} target="_blank" rel="noreferrer">Book on Airbnb →</a>
              </div>
            </article>
            """
        )
    return f"""
    <section id="stays" class="section">
      <div class="section-head">
        <p class="section-title">Stays</p>
        <h2>Shortlist</h2>
      </div>
      <div class="stay-row">{''.join(cards)}</div>
    </section>
    """


def _render_neighborhood(result: CurationOutput) -> str:
    if result.neighborhood is None:
        return ""
    notes = "".join(f"<li>{_escape(note)}</li>" for note in result.neighborhood.notable_notes)
    return f"""
    <section id="neighborhood" class="section">
      <div class="section-head">
        <p class="section-title">Neighborhood</p>
        <h2>Area Snapshot</h2>
      </div>
      <div class="grid three-up">
        <article class="card detail-card"><h3>Safety</h3><p>{_escape(result.neighborhood.safety_summary)}</p></article>
        <article class="card detail-card"><h3>Vibe</h3><p>{_escape(result.neighborhood.vibe)}</p></article>
        <article class="card detail-card"><h3>Walkability</h3><p>{_escape(result.neighborhood.walkability)}</p></article>
      </div>
      <ul class="notes">{notes}</ul>
    </section>
    """


def _render_weather(result: CurationOutput) -> str:
    if result.weather is None:
        return ""
    tips = "".join(f"<li>{_escape(tip)}</li>" for tip in result.weather.packing_tips)
    return f"""
    <section id="weather" class="section">
      <div class="section-head">
        <p class="section-title">Weather</p>
        <h2>What To Expect</h2>
      </div>
      <div class="grid weather-grid">
        <article class="card">
          <p>{_escape(result.weather.forecast_summary)}</p>
          <div class="temp-badge">{_escape(result.weather.temperature_range)}</div>
          <p class="muted">{_escape(result.weather.conditions)}</p>
        </article>
        <article class="card">
          <h3>Packing Tips</h3>
          <ul class="checklist">{tips}</ul>
        </article>
      </div>
    </section>
    """


def _render_activities(result: CurationOutput) -> str:
    if result.activities is None or not result.activities.activities:
        return ""
    cards = []
    for activity in result.activities.activities:
        cards.append(
            f"""
            <article class="card media-card">
              {_image_wrap(activity.name, activity.image_url, 200)}
              <div class="card-body">
                <span class="badge">{_escape(activity.category)}</span>
                <h3>{_escape(activity.name)}</h3>
                <p>{_escape(activity.description)}</p>
                {_source_cta(activity.source_url)}
              </div>
            </article>
            """
        )
    return f"""
    <section id="activities" class="section">
      <div class="section-head">
        <p class="section-title">Activities</p>
        <h2>Between Meetings</h2>
      </div>
      <div class="grid two-up">{''.join(cards)}</div>
    </section>
    """


def _render_food(result: CurationOutput) -> str:
    if result.food is None or not result.food.picks:
        return ""
    cards = []
    for pick in result.food.picks:
        price_color = _price_badge_color(pick.price_range)
        cards.append(
            f"""
            <article class="card media-card">
              {_image_wrap(pick.name, pick.image_url, 180)}
              <div class="card-body">
                <div class="food-header">
                  <h3>{_escape(pick.name)}</h3>
                  <span class="price-badge" style="background:{price_color}">{_escape(pick.price_range)}</span>
                </div>
                <p class="muted">{_escape(pick.cuisine_type)}</p>
                <p>{_escape(pick.description)}</p>
                {_source_cta(pick.source_url)}
              </div>
            </article>
            """
        )
    return f"""
    <section id="food" class="section">
      <div class="section-head">
        <p class="section-title">Food</p>
        <h2>Where To Eat</h2>
      </div>
      <div class="grid two-up">{''.join(cards)}</div>
    </section>
    """


def _render_flights(result: CurationOutput) -> str:
    if result.flights is None or not result.flights.options:
        return ""
    cheapest = result.flights.cheapest_price_usd
    rows = []
    for option in result.flights.options:
        cheapest_row = " cheapest-row" if cheapest is not None and option.price_usd == cheapest else ""
        rows.append(
            f"""
            <tr class="{cheapest_row.strip()}">
              <td>{_escape(option.airline)}</td>
              <td>{_escape(option.departure_time)}</td>
              <td>{_escape(option.arrival_time)}</td>
              <td>{_escape(_format_duration(option.duration_minutes))}</td>
              <td>{_escape(_format_stops(option.stops))}</td>
              <td>{_escape(option.seat_class)}</td>
              <td class="price-text">{_escape(_format_money(option.price_usd))}</td>
            </tr>
            """
        )
    badge = ""
    if cheapest is not None:
        badge = f'<div class="inline-badge">Best price from {_escape(_format_money(cheapest))}</div>'
    return f"""
    <section id="flights" class="section">
      <div class="section-head">
        <p class="section-title">Flights</p>
        <h2>Outbound Options</h2>
        {badge}
        <p class="muted">{_escape(result.flights.search_summary)}</p>
      </div>
      <div class="card table-card">
        <table>
          <thead><tr><th>Airline</th><th>Departs</th><th>Arrives</th><th>Duration</th><th>Stops</th><th>Class</th><th>Price</th></tr></thead>
          <tbody>{''.join(rows)}</tbody>
        </table>
      </div>
    </section>
    """


def _render_commute(result: CurationOutput) -> str:
    if result.commute is None or (not result.commute.options and not result.commute.map_url):
        return ""
    rows = []
    for option in result.commute.options:
        rows.append(
            f"""
            <tr>
              <td>{_escape(option.origin)}</td>
              <td>{_escape(option.destination)}</td>
              <td>{_escape(option.mode.title())}</td>
              <td>{_escape(_format_duration(option.duration_minutes))}</td>
            </tr>
            """
        )
    map_block = ""
    fixed_map_url = _fix_map_url(result.commute.map_url)
    if fixed_map_url:
        map_block = (
            f'<div class="map-card card">{_image_wrap("Commute Map", fixed_map_url, 280)}</div>'
        )
    summary_cards = "".join(
        f'<article class="card commute-summary"><h3>{_escape(option.destination)}</h3><p>{_escape(option.summary)}</p></article>'
        for option in result.commute.options
    )
    return f"""
    <section id="commute" class="section">
      <div class="section-head">
        <p class="section-title">Commute</p>
        <h2>Business-Day Routing</h2>
      </div>
      <div class="card table-card">
        <table>
          <thead><tr><th>From</th><th>To</th><th>Mode</th><th>Duration</th></tr></thead>
          <tbody>{''.join(rows)}</tbody>
        </table>
      </div>
      <div class="grid two-up">{summary_cards}</div>
      {map_block}
    </section>
    """


def _nav_items(result: CurationOutput) -> list[tuple[str, str]]:
    items: list[tuple[str, str]] = []
    if result.stays is not None and result.stays.stays:
        items.append(("stays", "Stays"))
    if result.neighborhood is not None:
        items.append(("neighborhood", "Neighborhood"))
    if result.weather is not None:
        items.append(("weather", "Weather"))
    if result.activities is not None and result.activities.activities:
        items.append(("activities", "Activities"))
    if result.food is not None and result.food.picks:
        items.append(("food", "Food"))
    if result.flights is not None and result.flights.options:
        items.append(("flights", "Flights"))
    if result.commute is not None and (result.commute.options or result.commute.map_url):
        items.append(("commute", "Commute"))
    return items


def _render_sidebar(items: list[tuple[str, str]]) -> str:
    links = "".join(
        f'<a href="#{_escape(section_id)}" data-target="{_escape(section_id)}">{_escape(label)}</a>'
        for section_id, label in items
    )
    return f'<nav id="sidebar"><div class="nav-shell">{links}</div></nav>'


async def generate_slides(result: CurationOutput) -> str:
    palette = _get_palette(result.destination_vibe)
    nav_items = _nav_items(result)
    sections = [
        _render_cover(result),
        _render_stays(result),
        _render_neighborhood(result),
        _render_weather(result),
        _render_activities(result),
        _render_food(result),
        _render_flights(result),
        _render_commute(result),
    ]

    html_output = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{_escape(result.destination)} Travel Book</title>
  <style>
    :root {{
      --primary: {palette["primary"]};
      --accent: {palette["accent"]};
      --bg: {palette["bg"]};
      --text: {palette["text"]};
      --card-bg: rgba(255,255,255,.88);
      --border: rgba(17,17,17,.08);
      --radius: 18px;
      --shadow: 0 24px 60px rgba(15,23,42,.12);
    }}
    * {{ box-sizing: border-box; }}
    html {{ scroll-behavior: smooth; }}
    body {{
      margin: 0;
      color: var(--text);
      background:
        radial-gradient(circle at top left, color-mix(in srgb, var(--accent) 18%, transparent), transparent 28%),
        linear-gradient(180deg, #ffffff 0%, var(--bg) 45%, #eef2f6 100%);
      font-family: "Iowan Old Style", "Palatino Linotype", "Book Antiqua", Georgia, serif;
    }}
    a {{ color: inherit; }}
    #sidebar {{
      position: fixed;
      inset: 0 auto 0 0;
      width: 188px;
      background: linear-gradient(180deg, var(--primary), color-mix(in srgb, var(--primary) 72%, black));
      color: #fff;
      padding: 40px 16px;
      z-index: 10;
    }}
    .nav-shell {{
      display: flex;
      flex-direction: column;
      gap: 10px;
      margin-top: 34px;
    }}
    #sidebar a {{
      display: block;
      text-decoration: none;
      padding: 12px 14px;
      border-left: 3px solid transparent;
      border-radius: 10px;
      opacity: .84;
      transition: background .2s ease, opacity .2s ease, border-color .2s ease;
    }}
    #sidebar a.active {{
      background: rgba(255,255,255,.14);
      border-left-color: var(--accent);
      opacity: 1;
    }}
    #content {{
      margin-left: 188px;
    }}
    .cover {{
      min-height: 100vh;
      display: grid;
      place-items: center;
      padding: 60px 40px;
      background:
        radial-gradient(circle at 20% 20%, rgba(255,255,255,.14), transparent 25%),
        linear-gradient(160deg, var(--primary) 0%, color-mix(in srgb, var(--accent) 80%, white) 100%);
      color: #fff;
    }}
    .cover-inner {{
      max-width: 900px;
      text-align: center;
    }}
    .eyebrow, .section-title {{
      text-transform: uppercase;
      letter-spacing: .28em;
      font-size: .8rem;
      margin: 0 0 14px;
      opacity: .8;
    }}
    .cover h1 {{
      margin: 0;
      font-size: clamp(3.5rem, 9vw, 6.3rem);
      line-height: .94;
      letter-spacing: -.04em;
    }}
    .cover-meta {{
      font-size: clamp(1rem, 2vw, 1.3rem);
      opacity: .9;
      margin: 22px 0;
    }}
    .vibe-pill, .inline-badge, .badge, .chip, .price-badge {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      border-radius: 999px;
      font-size: .78rem;
      letter-spacing: .06em;
      text-transform: uppercase;
    }}
    .vibe-pill {{
      background: rgba(255,255,255,.14);
      border: 1px solid rgba(255,255,255,.28);
      padding: 10px 16px;
    }}
    .section {{
      padding: 64px 40px;
    }}
    .section-head {{
      margin-bottom: 24px;
    }}
    .section-head h2 {{
      margin: 0;
      font-size: clamp(1.8rem, 3vw, 2.7rem);
      line-height: 1.05;
    }}
    .card {{
      background: var(--card-bg);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      box-shadow: var(--shadow);
      overflow: hidden;
      backdrop-filter: blur(12px);
    }}
    .card-body {{
      padding: 18px;
    }}
    .muted {{
      color: rgba(0,0,0,.64);
    }}
    .grid {{
      display: grid;
      gap: 20px;
    }}
    .three-up {{
      grid-template-columns: repeat(3, minmax(0, 1fr));
    }}
    .two-up {{
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }}
    .weather-grid {{
      grid-template-columns: 1.3fr .9fr;
    }}
    .stay-row {{
      display: flex;
      gap: 20px;
      overflow-x: auto;
      padding-bottom: 6px;
      scroll-snap-type: x proximity;
    }}
    .stay-card {{
      min-width: 290px;
      max-width: 300px;
      flex: 0 0 auto;
      scroll-snap-align: start;
    }}
    .stay-card h3,
    .media-card h3,
    .detail-card h3,
    .commute-summary h3 {{
      margin: 0 0 10px;
      font-size: 1.05rem;
    }}
    .detail-card {{
      border-top: 4px solid var(--accent);
      padding: 20px;
    }}
    .img-wrap {{
      position: relative;
      overflow: hidden;
      border-radius: var(--radius) var(--radius) 0 0;
      background: linear-gradient(135deg, var(--primary), var(--accent));
      display: flex;
      align-items: center;
      justify-content: center;
    }}
    .img-wrap img {{
      position: absolute;
      inset: 0;
      width: 100%;
      height: 100%;
      object-fit: cover;
      transition: opacity .3s ease;
    }}
    .img-wrap::after {{
      content: attr(data-label);
      position: absolute;
      left: 14px;
      right: 14px;
      bottom: 12px;
      color: rgba(255,255,255,.92);
      font-size: .82rem;
      font-weight: 700;
      text-shadow: 0 1px 6px rgba(0,0,0,.55);
    }}
    .rating {{
      color: var(--accent);
      font-weight: 700;
      margin: 12px 0 10px;
    }}
    .price-row {{
      display: flex;
      align-items: baseline;
      justify-content: space-between;
      gap: 10px;
      margin-bottom: 12px;
    }}
    .price-row strong {{
      font-size: 1.15rem;
    }}
    .price-row strong span {{
      font-size: .8rem;
      color: rgba(0,0,0,.55);
      margin-left: 4px;
    }}
    .chip-row {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-bottom: 16px;
    }}
    .chip {{
      background: rgba(15,23,42,.06);
      padding: 6px 10px;
    }}
    .button {{
      display: inline-flex;
      width: 100%;
      justify-content: center;
      align-items: center;
      padding: 12px 16px;
      border-radius: 12px;
      background: var(--accent);
      color: #fff;
      text-decoration: none;
      font-weight: 700;
    }}
    .source-button {{
      margin-top: 14px;
      width: auto;
    }}
    .button-disabled {{
      background: rgba(15,23,42,.18);
      pointer-events: none;
    }}
    .source-host {{
      margin: 14px 0 0;
      font-size: .8rem;
      letter-spacing: .04em;
      text-transform: uppercase;
      color: rgba(0,0,0,.52);
    }}
    .notes, .checklist {{
      margin: 22px 0 0;
      padding: 0;
      list-style: none;
    }}
    .notes li, .checklist li {{
      position: relative;
      padding-left: 18px;
      margin-bottom: 10px;
    }}
    .notes li::before {{
      content: "›";
      position: absolute;
      left: 0;
      color: var(--accent);
      font-weight: 700;
    }}
    .checklist li::before {{
      content: "✓";
      position: absolute;
      left: 0;
      color: var(--accent);
      font-weight: 700;
    }}
    .temp-badge, .inline-badge {{
      display: inline-flex;
      padding: 10px 14px;
      background: var(--primary);
      color: #fff;
      margin: 14px 0;
    }}
    .badge {{
      background: var(--accent);
      color: #fff;
      padding: 7px 10px;
      margin-bottom: 12px;
    }}
    .food-header {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
    }}
    .price-badge {{
      color: #fff;
      padding: 8px 10px;
      min-width: 52px;
    }}
    .table-card {{
      padding: 12px;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: .94rem;
    }}
    th, td {{
      padding: 14px 12px;
      text-align: left;
      border-bottom: 1px solid rgba(15,23,42,.08);
      vertical-align: top;
    }}
    thead th {{
      color: rgba(0,0,0,.62);
      font-size: .8rem;
      text-transform: uppercase;
      letter-spacing: .08em;
    }}
    tbody tr:nth-child(even) {{
      background: rgba(15,23,42,.03);
    }}
    .cheapest-row {{
      background: color-mix(in srgb, var(--accent) 14%, white) !important;
      font-weight: 700;
    }}
    .price-text {{
      color: var(--accent);
      font-weight: 700;
    }}
    .map-card {{
      margin-top: 20px;
    }}
    .commute-summary {{
      padding: 20px;
    }}
    @media (max-width: 960px) {{
      #sidebar {{
        position: sticky;
        inset: 0;
        width: 100%;
        padding: 12px 16px;
      }}
      .nav-shell {{
        margin-top: 0;
        flex-direction: row;
        overflow-x: auto;
      }}
      #content {{
        margin-left: 0;
      }}
      .three-up,
      .two-up,
      .weather-grid {{
        grid-template-columns: 1fr;
      }}
      .section {{
        padding: 42px 20px;
      }}
    }}
  </style>
</head>
<body>
  {_render_sidebar(nav_items)}
  <main id="content">
    {''.join(section for section in sections if section)}
  </main>
  <script>
    const links = Array.from(document.querySelectorAll('#sidebar a'));
    const sections = links
      .map((link) => document.getElementById(link.dataset.target))
      .filter(Boolean);
    if ('IntersectionObserver' in window && links.length) {{
      const observer = new IntersectionObserver((entries) => {{
        entries.forEach((entry) => {{
          if (!entry.isIntersecting) return;
          links.forEach((link) => {{
            link.classList.toggle('active', link.dataset.target === entry.target.id);
          }});
        }});
      }}, {{ rootMargin: '-40% 0px -45% 0px', threshold: 0 }});
      sections.forEach((section) => observer.observe(section));
    }}
  </script>
</body>
</html>
"""
    return html_output
