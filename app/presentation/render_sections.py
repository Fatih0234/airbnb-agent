from __future__ import annotations

import json

from ..schemas import CurationOutput
from .deck_spec import DeckSection, DeckSpec
from .formatters import (
    escape,
    format_duration,
    format_money,
    format_stops,
    image_wrap,
    inline_svg_icon,
    price_badge_color,
    source_cta,
    truncate_to_headline,
)
from .layout_rules import (
    ACTIVITY_VISIBLE_CARDS,
    CARD_IMAGE_HEIGHT,
    FOOD_VISIBLE_CARDS,
    MAP_IMAGE_HEIGHT,
    NEIGHBORHOOD_MAX_NOTES,
    NEIGHBORHOOD_TRUNCATE_WORDS,
    STAY_IMAGE_HEIGHT,
    split_visible,
)
from .style_presets import StylePreset


def _stay_lookup(result: CurationOutput) -> dict[str, object]:
    stays = result.stays.stays if result.stays is not None else []
    return {stay.id: stay for stay in stays}


def _render_expandable_cards(cards: list[str], hidden_cards: list[str], summary_label: str) -> str:
    visible = "".join(cards)
    if not hidden_cards:
        return visible
    return (
        f"{visible}"
        '<details class="expandable-grid">'
        f'<summary>{escape(summary_label)}</summary>'
        f'<div class="grid two-up expanded-grid">{"".join(hidden_cards)}</div>'
        "</details>"
    )


def render_section(section: DeckSection, deck: DeckSpec, style: StylePreset, result: CurationOutput) -> str:
    if section.type == "hero":
        return render_hero(section, deck)
    if section.type == "recommendation":
        return render_recommendation(section, deck, result)
    if section.type == "stay_map":
        return render_stay_map(section)
    if section.type == "comparison":
        return render_comparison(section)
    if section.type == "neighborhood":
        return render_neighborhood(section, result)
    if section.type == "logistics":
        return render_logistics(section, result)
    if section.type == "weather":
        return render_weather(section, result)
    if section.type == "activities":
        return render_activities(section, result)
    if section.type == "food":
        return render_food(section, result)
    if section.type == "flights":
        return render_flights(section, result)
    if section.type == "closing":
        return render_closing(section, deck, result)
    return ""


def render_hero(section: DeckSection, deck: DeckSpec) -> str:
    metrics = "".join(
        f"""
        <article class="metric-card">
          <p class="metric-label">{escape(metric.label)}</p>
          <p class="metric-value emphasis-{escape(metric.emphasis)}">{escape(metric.value)}</p>
        </article>
        """
        for metric in deck.key_metrics
    )
    factors = "".join(f"<li>{escape(item)}</li>" for item in deck.top_decision_factors)
    return f"""
    <section id="{escape(section.id)}" class="section hero-section reveal">
      <div class="hero-banner">
        <p class="eyebrow">Decision-ready travel brief</p>
        <h1>{escape(deck.title)}</h1>
        <p class="section-kicker">{escape(deck.subtitle)}</p>
        <p class="hero-thesis">{escape(deck.trip_thesis)}</p>
        <div class="hero-actions">
          <a class="button" href="#comparison">Jump to booking options</a>
          <a class="button secondary-button" href="#closing">See decision summary</a>
        </div>
      </div>
      <div class="hero-metrics-row">{metrics}</div>
      <div class="hero-factors card">
        <div class="card-body">
          <p class="section-title">Top decision factors</p>
          <ul class="notes compact-notes">{factors}</ul>
        </div>
      </div>
    </section>
    """


def render_recommendation(section: DeckSection, deck: DeckSpec, result: CurationOutput) -> str:
    stays = _stay_lookup(result)
    recommended = stays.get(section.content.get("recommended_stay_id"))
    if recommended is None:
        return ""

    reasons = "".join(f"<li>{escape(reason)}</li>" for reason in section.content.get("reasons", []))
    tradeoff = section.content.get("tradeoff")
    price_line = f"{format_money(recommended.price_per_night)}/night" if recommended.price_per_night is not None else "Nightly price unavailable"
    total_line = f"Total {format_money(recommended.total_price)}" if recommended.total_price is not None else "Total unavailable"
    rating_line = f"★ {recommended.rating:.2f}" if recommended.rating is not None else "Rating unavailable"
    location_line = recommended.location_description or "Location summary unavailable"
    image_url = recommended.image_urls[0] if recommended.image_urls else None
    cta_href = section.content.get("cta_href") or "#comparison"
    cta_label = section.content.get("cta_label") or "Open booking option"

    return f"""
    <section id="{escape(section.id)}" class="section reveal">
      <div class="section-head">
        <p class="section-title">{escape(section.heading)}</p>
        <h2>{escape(section.subheading)}</h2>
      </div>
      <div class="feature-grid">
        <article class="card featured-stay">
          {image_wrap(recommended.name, image_url, STAY_IMAGE_HEIGHT, class_name="img-wrap premium-image")}
          <div class="card-body">
            <div class="feature-header">
              <span class="inline-badge badge-pulse">Recommended</span>
              <span class="rating">{escape(rating_line)}</span>
            </div>
            <h3>{escape(recommended.name)}</h3>
            <p class="muted">{escape(location_line)}</p>
            <div class="price-row">
              <strong>{escape(price_line)}</strong>
              <span>{escape(total_line)}</span>
            </div>
            <div class="chip-row">
              <span class="chip">Lead option</span>
              <span class="chip">Best overall fit</span>
            </div>
            <a href="{escape(cta_href)}" class="button" target="_blank" rel="noreferrer">{escape(cta_label)}</a>
          </div>
        </article>
        <article class="card recommendation-notes">
          <div class="card-body">
            <p class="section-title">Why it wins</p>
            <ul class="notes">{reasons}</ul>
            {f'<p class="tradeoff">{escape(tradeoff)}</p>' if tradeoff else ''}
          </div>
        </article>
      </div>
    </section>
    """


def render_comparison(section: DeckSection) -> str:
    rows = section.content.get("rows", [])
    if not rows:
        return ""

    cards: list[str] = []
    for row in rows:
        label = row.get("label")
        is_recommended = label == "Recommended"
        card_cls = "card stay-card stay-card--recommended" if is_recommended else "card stay-card"
        badge = '<span class="inline-badge badge-pulse">Recommended</span>' if is_recommended else ""
        if not is_recommended and label:
            badge = f'<span class="inline-badge">{escape(label)}</span>'

        highlights = "".join(f"<li>{escape(item)}</li>" for item in row.get("highlights", []))
        amenities = "".join(f'<span class="chip">{escape(a)}</span>' for a in row.get("amenities", []))
        rating_str = f"\u2605 {escape(row['rating'])}" if row.get("rating") and row["rating"] != "N/A" else "Rating N/A"
        cta = (
            f'<a href="{escape(row["url"])}" class="button source-button" target="_blank" rel="noreferrer">View listing</a>'
            if row.get("url")
            else ""
        )

        cards.append(
            f"""
            <article class="{card_cls}">
              {image_wrap(row["name"], row.get("image_url"), STAY_IMAGE_HEIGHT, class_name="img-wrap premium-image")}
              <div class="card-body">
                <div class="feature-header">
                  {badge}
                  <span class="rating">{rating_str}</span>
                </div>
                <h3>{escape(row['name'])}</h3>
                <p class="muted">{escape(row.get('location_description', ''))}</p>
                <div class="price-row">
                  <strong>{escape(row['nightly'])}/night</strong>
                  <span>Total {escape(row['total'])}</span>
                </div>
                {f'<div class="chip-row">{amenities}</div>' if amenities else ''}
                <ul class="comparison-notes">{highlights}</ul>
                {cta}
              </div>
            </article>
            """
        )

    return f"""
    <section id="{escape(section.id)}" class="section reveal">
      <div class="section-head">
        <p class="section-title">{escape(section.heading)}</p>
        <h2>{escape(section.subheading)}</h2>
      </div>
      <div class="grid two-up">{''.join(cards)}</div>
    </section>
    """


def render_stay_map(section: DeckSection) -> str:
    markers = section.content.get("markers", [])
    if not markers:
        return ""

    map_id = f"{section.id}-leaflet"
    data_id = f"{section.id}-leaflet-data"
    payload = json.dumps(
        {
            "markers": markers,
            "fallback_center": section.content.get("fallback_center"),
        },
        ensure_ascii=True,
    ).replace("</", "<\\/")

    return f"""
    <section id="{escape(section.id)}" class="section reveal stay-map-section" data-stay-map="true" data-map-id="{escape(map_id)}" data-map-data-id="{escape(data_id)}">
      <div class="section-head">
        <p class="section-title">{escape(section.heading)}</p>
        <h2>{escape(section.subheading)}</h2>
        <div class="inline-badge">{escape(section.content.get('summary_badge'))}</div>
      </div>
      <div class="card stay-map-card">
        <div class="card-body">
          <p class="muted">Map markers show the Airbnb shortlist only. The recommended stay is highlighted.</p>
          <div id="{escape(map_id)}" class="stay-map-canvas" aria-label="Stay map"></div>
        </div>
      </div>
      <script id="{escape(data_id)}" type="application/json">{payload}</script>
    </section>
    """


def _neighborhood_card(icon_name: str, title: str, text: str) -> str:
    icon = inline_svg_icon(icon_name)
    headline, remainder = truncate_to_headline(text, NEIGHBORHOOD_TRUNCATE_WORDS)
    detail_html = ""
    if remainder:
        detail_html = (
            '<details class="neighborhood-details">'
            '<summary>Read more</summary>'
            f'<p>{escape(remainder)}</p>'
            '</details>'
        )
    return (
        f'<article class="card detail-card">'
        f'<h3><span class="icon-inline">{icon}</span> {escape(title)}</h3>'
        f'<p class="neighborhood-headline"><strong>{escape(headline)}</strong></p>'
        f'{detail_html}'
        f'</article>'
    )


def render_neighborhood(section: DeckSection, result: CurationOutput) -> str:
    if result.neighborhood is None:
        return ""
    notes = "".join(f"<li>{escape(note)}</li>" for note in result.neighborhood.notable_notes[:NEIGHBORHOOD_MAX_NOTES])
    return f"""
    <section id="{escape(section.id)}" class="section reveal">
      <div class="section-head">
        <p class="section-title">{escape(section.heading)}</p>
        <h2>{escape(section.subheading)}</h2>
      </div>
      <div class="grid three-up">
        {_neighborhood_card("shield", "Safety", result.neighborhood.safety_summary)}
        {_neighborhood_card("sparkles", "Vibe", result.neighborhood.vibe)}
        {_neighborhood_card("walking", "Walkability", result.neighborhood.walkability)}
      </div>
      <ul class="notes">{notes}</ul>
    </section>
    """


def render_logistics(section: DeckSection, result: CurationOutput) -> str:
    rows = section.content.get("rows", [])
    rendered_rows = "".join(
        f"""
        <tr>
          <td>{escape(row['origin'])}</td>
          <td>{escape(row['destination'])}</td>
          <td>{escape(row['mode'])}</td>
          <td>{escape(row['duration'])}</td>
        </tr>
        """
        for row in rows
    )

    flight_stats = ""
    price = section.content.get("flight_price")
    airline = section.content.get("cheapest_airline")
    stops = section.content.get("cheapest_stops")
    duration = section.content.get("cheapest_duration")

    if price or airline:
        stat_items: list[str] = []
        if price:
            stat_items.append(
                f'<div class="flight-stat">'
                f'{inline_svg_icon("dollar")}'
                f'<span class="stat-value">{escape(price)}</span>'
                f'<span class="stat-label">Cheapest fare</span>'
                f'</div>'
            )
        if airline:
            stat_items.append(
                f'<div class="flight-stat">'
                f'{inline_svg_icon("plane")}'
                f'<span class="stat-value">{escape(airline)}</span>'
                f'<span class="stat-label">Airline</span>'
                f'</div>'
            )
        if stops is not None:
            stat_items.append(
                f'<div class="flight-stat">'
                f'{inline_svg_icon("layers")}'
                f'<span class="stat-value">{escape(format_stops(stops))}</span>'
                f'<span class="stat-label">Stops</span>'
                f'</div>'
            )
        if duration:
            stat_items.append(
                f'<div class="flight-stat">'
                f'{inline_svg_icon("layers")}'
                f'<span class="stat-value">{escape(duration)}</span>'
                f'<span class="stat-label">Duration</span>'
                f'</div>'
            )

        flight_stats = (
            '<article class="card logistics-brief">'
            '<p class="section-title">Flight snapshot</p>'
            f'<div class="flight-stats">{"".join(stat_items)}</div>'
            '</article>'
        )

    return f"""
    <section id="{escape(section.id)}" class="section reveal">
      <div class="section-head">
        <p class="section-title">{escape(section.heading)}</p>
        <h2>{escape(section.subheading)}</h2>
        <div class="inline-badge">{escape(section.content.get('summary_badge'))}</div>
      </div>
      {f'<div class="card table-card"><table><thead><tr><th>From</th><th>To</th><th>Mode</th><th>Duration</th></tr></thead><tbody>{rendered_rows}</tbody></table></div>' if rows else ''}
      {flight_stats}
    </section>
    """


def render_weather(section: DeckSection, result: CurationOutput) -> str:
    if result.weather is None:
        return ""
    tips = "".join(f"<li>{escape(tip)}</li>" for tip in result.weather.packing_tips)
    return f"""
    <section id="{escape(section.id)}" class="section reveal">
      <div class="section-head">
        <p class="section-title">{escape(section.heading)}</p>
        <h2>{escape(section.subheading)}</h2>
      </div>
      <div class="grid weather-grid">
        <article class="card">
          <div class="card-body">
            <p>{escape(result.weather.forecast_summary)}</p>
            <div class="temp-badge">{escape(result.weather.temperature_range)}</div>
            <p class="muted">{escape(result.weather.conditions)}</p>
          </div>
        </article>
        <article class="card">
          <div class="card-body">
            <h3>Packing tips</h3>
            <ul class="checklist">{tips}</ul>
          </div>
        </article>
      </div>
    </section>
    """


def render_activities(section: DeckSection, result: CurationOutput) -> str:
    if result.activities is None or not result.activities.activities:
        return ""
    visible, hidden = split_visible(result.activities.activities, ACTIVITY_VISIBLE_CARDS)
    visible_cards = [
        f"""
        <article class="card media-card">
          {image_wrap(activity.name, activity.image_url, CARD_IMAGE_HEIGHT)}
          <div class="card-body">
            <span class="badge">{escape(activity.category)}</span>
            <h3>{escape(activity.name)}</h3>
            <p>{escape(activity.description)}</p>
            {source_cta(activity.source_url)}
          </div>
        </article>
        """
        for activity in visible
    ]
    hidden_cards = [
        f"""
        <article class="card media-card">
          {image_wrap(activity.name, activity.image_url, CARD_IMAGE_HEIGHT)}
          <div class="card-body">
            <span class="badge">{escape(activity.category)}</span>
            <h3>{escape(activity.name)}</h3>
            <p>{escape(activity.description)}</p>
            {source_cta(activity.source_url)}
          </div>
        </article>
        """
        for activity in hidden
    ]
    return f"""
    <section id="{escape(section.id)}" class="section reveal">
      <div class="section-head">
        <p class="section-title">{escape(section.heading)}</p>
        <h2>{escape(section.subheading)}</h2>
      </div>
      <div class="grid two-up">
        {_render_expandable_cards(visible_cards, hidden_cards, f"Show {len(hidden_cards)} more activities")}
      </div>
    </section>
    """


def render_food(section: DeckSection, result: CurationOutput) -> str:
    if result.food is None or not result.food.picks:
        return ""
    visible, hidden = split_visible(result.food.picks, FOOD_VISIBLE_CARDS)

    def render_card(pick: object) -> str:
        price_color = price_badge_color(pick.price_range)
        return f"""
        <article class="card media-card">
          {image_wrap(pick.name, pick.image_url, CARD_IMAGE_HEIGHT)}
          <div class="card-body">
            <div class="food-header">
              <h3>{escape(pick.name)}</h3>
              <span class="price-badge" style="background:{price_color}">{escape(pick.price_range)}</span>
            </div>
            <p class="muted">{escape(pick.cuisine_type)}</p>
            <p>{escape(pick.description)}</p>
            {source_cta(pick.source_url)}
          </div>
        </article>
        """

    visible_cards = [render_card(pick) for pick in visible]
    hidden_cards = [render_card(pick) for pick in hidden]
    return f"""
    <section id="{escape(section.id)}" class="section reveal">
      <div class="section-head">
        <p class="section-title">{escape(section.heading)}</p>
        <h2>{escape(section.subheading)}</h2>
      </div>
      <div class="grid two-up">
        {_render_expandable_cards(visible_cards, hidden_cards, f"Show {len(hidden_cards)} more food picks")}
      </div>
    </section>
    """


def render_flights(section: DeckSection, result: CurationOutput) -> str:
    if result.flights is None or not result.flights.options:
        return ""
    cheapest = result.flights.cheapest_price_usd
    rows = []
    for option in result.flights.options:
        cheapest_row = " cheapest-row" if cheapest is not None and option.price_usd == cheapest else ""
        rows.append(
            f"""
            <tr class="{cheapest_row.strip()}">
              <td>{escape(option.airline)}</td>
              <td>{escape(option.departure_time)}</td>
              <td>{escape(option.arrival_time)}</td>
              <td>{escape(format_duration(option.duration_minutes))}</td>
              <td>{escape(format_stops(option.stops))}</td>
              <td class="price-text">{escape(format_money(option.price_usd))}</td>
            </tr>
            """
        )
    badge = f'<div class="inline-badge">Best price from {escape(format_money(cheapest))}</div>' if cheapest is not None else ""
    return f"""
    <section id="{escape(section.id)}" class="section reveal">
      <div class="section-head">
        <p class="section-title">{escape(section.heading)}</p>
        <h2>{escape(section.subheading)}</h2>
        {badge}
        <p class="muted">{escape(result.flights.search_summary)}</p>
      </div>
      <div class="card table-card">
        <table>
          <thead><tr><th>Airline</th><th>Departs</th><th>Arrives</th><th>Duration</th><th>Stops</th><th>Price</th></tr></thead>
          <tbody>{''.join(rows)}</tbody>
        </table>
      </div>
    </section>
    """


def render_closing(section: DeckSection, deck: DeckSpec, result: CurationOutput) -> str:
    stays = _stay_lookup(result)
    recommended = stays.get(section.content.get("recommended_stay_id"))
    next_steps = "".join(f"<li>{escape(step)}</li>" for step in section.content.get("next_steps", []))
    warnings = "".join(f"<li>{escape(item)}</li>" for item in deck.warnings)
    lead_name = recommended.name if recommended is not None else "No lead stay available"
    lead_href = recommended.url if recommended is not None else "#hero"
    return f"""
    <section id="{escape(section.id)}" class="section reveal">
      <div class="closing-shell card">
        <div class="card-body">
          <p class="section-title">{escape(section.heading)}</p>
          <h2>{escape(lead_name)}</h2>
          <p>{escape(deck.trip_thesis)}</p>
          <div class="hero-actions">
            <a class="button" href="{escape(lead_href)}" {'target="_blank" rel="noreferrer"' if recommended is not None else ''}>Jump to booking options</a>
          </div>
          <div class="grid two-up">
            <div>
              <h3>Next steps</h3>
              <ul class="notes">{next_steps}</ul>
            </div>
            <div>
              <h3>Watchouts</h3>
              <ul class="notes">{warnings or '<li>No special watchouts in the current data.</li>'}</ul>
            </div>
          </div>
        </div>
      </div>
    </section>
    """
