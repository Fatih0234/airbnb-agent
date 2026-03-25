from __future__ import annotations

import json

from ..schemas import CurationOutput
from .deck_spec import DeckSpec
from .formatters import escape
from .motion_patterns import render_motion_css, render_motion_js
from .render_sections import render_section
from .style_presets import StylePreset


def _nav_items(deck: DeckSpec) -> list[tuple[str, str]]:
    items: list[tuple[str, str]] = []
    for section in deck.sections:
        label = "Overview" if section.type == "hero" else section.heading
        items.append((section.id, label))
    return items


def _render_sidebar(deck: DeckSpec) -> str:
    links = "".join(
        f'<a href="#{escape(section_id)}" data-target="{escape(section_id)}" aria-current="false">{escape(label)}</a>'
        for section_id, label in _nav_items(deck)
    )
    return f'<nav id="sidebar"><div class="nav-shell">{links}</div></nav>'


def _has_stay_map(deck: DeckSpec) -> bool:
    return any(section.type == "stay_map" for section in deck.sections)


def _render_leaflet_assets(deck: DeckSpec) -> str:
    if not _has_stay_map(deck):
        return ""
    return """
    <link
      rel="stylesheet"
      href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"
      crossorigin=""
    >
    <script
      src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"
      crossorigin=""
    ></script>
    """


def _render_stay_map_bootstrap(deck: DeckSpec) -> str:
    if not _has_stay_map(deck):
        return ""

    marker_config = json.dumps(
        {
            "tileUrl": "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
            "tileAttribution": '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
            "singleZoom": 13,
            "fitBoundsPadding": [40, 40],
        },
        separators=(",", ":"),
    )
    return f"""
  <script>
    (() => {{
      const config = {marker_config};
      const sections = document.querySelectorAll("[data-stay-map='true']");
      if (!sections.length || typeof window.L === "undefined") {{
        return;
      }}

      const escapeHtml = (value) => String(value ?? "").replace(/[&<>\"']/g, (char) => ({{
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#39;",
      }})[char]);

      const formatMoney = (value) => {{
        if (typeof value !== "number" || Number.isNaN(value)) {{
          return "Nightly price unavailable";
        }}
        return Number.isInteger(value) ? `$${{value}}/night` : `$${{Math.round(value)}}/night`;
      }};

      sections.forEach((section) => {{
        const mapId = section.dataset.mapId;
        const dataId = section.dataset.mapDataId;
        const mapNode = document.getElementById(mapId);
        const dataNode = document.getElementById(dataId);
        if (!mapNode || !dataNode) {{
          return;
        }}

        let payload;
        try {{
          payload = JSON.parse(dataNode.textContent || "{{}}");
        }} catch {{
          return;
        }}

        const markers = Array.isArray(payload.markers)
          ? payload.markers.filter((marker) => typeof marker.latitude === "number" && typeof marker.longitude === "number")
          : [];
        if (!markers.length) {{
          return;
        }}

        const map = window.L.map(mapNode, {{
          scrollWheelZoom: false,
          zoomControl: true,
        }});

        window.L.tileLayer(config.tileUrl, {{
          maxZoom: 19,
          attribution: config.tileAttribution,
        }}).addTo(map);

        const points = [];
        markers.forEach((marker) => {{
          const latLng = [marker.latitude, marker.longitude];
          points.push(latLng);

          const icon = window.L.divIcon({{
            className: marker.is_recommended ? "stay-map-marker stay-map-marker--recommended" : "stay-map-marker",
            html: `<span>${{marker.is_recommended ? "★" : "•"}}</span>`,
            iconSize: [28, 28],
            iconAnchor: [14, 14],
            popupAnchor: [0, -14],
          }});

          const rating = typeof marker.rating === "number"
            ? `★ ${{marker.rating.toFixed(2)}}`
            : "Rating unavailable";
          const locationLine = marker.location_description
            ? `<p class="stay-map-popup-location">${{escapeHtml(marker.location_description)}}</p>`
            : "";
          const linkLine = marker.url
            ? `<a href="${{escapeHtml(marker.url)}}" target="_blank" rel="noreferrer">Open listing</a>`
            : "";
          const popupHtml = `
            <div class="stay-map-popup">
              <strong>${{escapeHtml(marker.name)}}</strong>
              <p>${{formatMoney(marker.price_per_night)}} · ${{rating}}</p>
              ${{locationLine}}
              ${{linkLine}}
            </div>
          `;

          window.L.marker(latLng, {{ icon }}).addTo(map).bindPopup(popupHtml);
        }});

        if (points.length === 1) {{
          map.setView(points[0], config.singleZoom);
        }} else {{
          map.fitBounds(points, {{ padding: config.fitBoundsPadding }});
        }}

        requestAnimationFrame(() => map.invalidateSize());
        window.setTimeout(() => map.invalidateSize(), 160);
      }});
    }})();
  </script>
    """


def _render_summary_rail(deck: DeckSpec, result: CurationOutput) -> str:
    from .formatters import format_money

    glance_rows: list[str] = []

    # Stay price
    if result.stays is not None and deck.recommended_stay_id is not None:
        for stay in result.stays.stays:
            if stay.id == deck.recommended_stay_id and stay.price_per_night is not None:
                glance_rows.append(
                    f'<div class="rail-metric">'
                    f'<span class="rail-metric-label">Stay</span>'
                    f'<span class="rail-metric-value">{escape(format_money(stay.price_per_night))}/night</span>'
                    f'</div>'
                )
                break

    # Flight price
    if result.flights is not None and result.flights.cheapest_price_usd is not None:
        glance_rows.append(
            f'<div class="rail-metric">'
            f'<span class="rail-metric-label">Flight</span>'
            f'<span class="rail-metric-value">{escape(format_money(result.flights.cheapest_price_usd))}</span>'
            f'</div>'
        )

    # Weather
    if result.weather is not None and result.weather.temperature_range:
        glance_rows.append(
            f'<div class="rail-metric">'
            f'<span class="rail-metric-label">Weather</span>'
            f'<span class="rail-metric-value">{escape(result.weather.temperature_range)}</span>'
            f'</div>'
        )

    # Dates
    if result.dates:
        glance_rows.append(
            f'<div class="rail-metric">'
            f'<span class="rail-metric-label">Dates</span>'
            f'<span class="rail-metric-value">{escape(result.dates)}</span>'
            f'</div>'
        )

    factors = "".join(f"<li>{escape(item)}</li>" for item in deck.top_decision_factors)
    warnings = "".join(f"<li>{escape(item)}</li>" for item in deck.warnings)
    return f"""
    <aside class="summary-rail">
      <div class="summary-rail-inner">
        <div class="rail-card card">
          <div class="card-body">
            <p class="section-title">Trip at a glance</p>
            {''.join(glance_rows) if glance_rows else '<p class="muted">Data still loading.</p>'}
          </div>
        </div>
        <div class="rail-card card">
          <div class="card-body">
            <p class="section-title">Decision factors</p>
            <ul class="notes compact-notes">{factors}</ul>
          </div>
        </div>
        <div class="rail-card card">
          <div class="card-body">
            <p class="section-title">Watchouts</p>
            <ul class="notes compact-notes">{warnings or '<li>No major watchouts in current data.</li>'}</ul>
          </div>
        </div>
      </div>
    </aside>
    """


def _render_head(deck: DeckSpec, style: StylePreset) -> str:
    colors = style.colors
    surface = colors.get("surfaceAlt", colors["surface"]) if style.name == "concierge_luxury" else colors["surface"]
    text = colors.get("textAlt", colors["text"]) if style.name == "concierge_luxury" else colors["text"]
    muted = colors.get("mutedAlt", colors["muted"]) if style.name == "concierge_luxury" else colors["muted"]
    border = colors.get("borderAlt", colors["border"]) if style.name == "concierge_luxury" else colors["border"]
    leaflet_assets = _render_leaflet_assets(deck)
    return f"""
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{escape(deck.title)} Travel Book</title>
    {leaflet_assets}
    <style>
      :root {{
        --primary: {colors["primary"]};
        --accent: {colors["accent"]};
        --bg: {colors["bg"]};
        --surface: {surface};
        --text: {text};
        --muted: {muted};
        --border: {border};
        --radius: {style.radius};
        --shadow: {style.shadow};
        --display-font: {style.fonts["display"]};
        --body-font: {style.fonts["body"]};
        --rail-width: 320px;
        --sidebar-width: 208px;
      }}
      * {{ box-sizing: border-box; }}
      html {{ scroll-behavior: smooth; }}
      body {{
        margin: 0;
        color: var(--text);
        background:
          radial-gradient(circle at top left, color-mix(in srgb, var(--accent) 18%, transparent), transparent 28%),
          linear-gradient(180deg, #ffffff 0%, var(--bg) 45%, #e8edf4 100%);
        font-family: var(--body-font);
      }}
      a {{ color: inherit; }}
      .progress-track {{
        position: fixed;
        top: 0;
        left: 0;
        right: 0;
        height: 4px;
        background: rgba(255,255,255,0.35);
        z-index: 30;
      }}
      #progress-bar {{
        display: block;
        width: 100%;
        height: 100%;
        background: linear-gradient(90deg, var(--accent), color-mix(in srgb, var(--accent) 55%, white));
        transform-origin: left center;
        transform: scaleX(0);
      }}
      #sidebar {{
        position: fixed;
        inset: 0 auto 0 0;
        width: var(--sidebar-width);
        background: linear-gradient(180deg, var(--primary), color-mix(in srgb, var(--primary) 76%, black));
        color: #fff;
        padding: 44px 16px 24px;
        z-index: 20;
      }}
      .nav-shell {{
        display: flex;
        flex-direction: column;
        gap: 10px;
        margin-top: 28px;
      }}
      #sidebar a {{
        display: block;
        text-decoration: none;
        padding: 12px 14px;
        border-left: 3px solid transparent;
        border-radius: 12px;
        white-space: nowrap;
        opacity: 0.84;
        transition: background .2s ease, opacity .2s ease, border-color .2s ease;
      }}
      #sidebar a.active {{
        background: rgba(255,255,255,.14);
        border-left-color: var(--accent);
        opacity: 1;
      }}
      #content {{
        margin-left: var(--sidebar-width);
      }}
      .brief-shell {{
        display: grid;
        grid-template-columns: minmax(0, 1fr) var(--rail-width);
        gap: 28px;
        padding: 24px;
        align-items: start;
      }}
      .brief-main {{
        min-width: 0;
      }}
      .summary-rail {{
        position: sticky;
        top: 28px;
      }}
      .summary-rail-inner {{
        display: grid;
        gap: 16px;
      }}
      .section {{
        padding: 44px 0;
      }}
      .hero-section {{
        display: flex;
        flex-direction: column;
        gap: 28px;
        padding-top: 52px;
      }}
      .hero-banner {{
        padding: clamp(32px, 5vw, 56px);
        border-radius: calc(var(--radius) + 8px);
        background:
          linear-gradient(160deg, color-mix(in srgb, var(--primary) 84%, black) 0%, color-mix(in srgb, var(--accent) 50%, white) 100%);
        color: #fff;
        box-shadow: var(--shadow);
      }}
      .hero-metrics-row {{
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
        gap: 16px;
      }}
      .metric-card {{
        padding: 18px;
        border-radius: var(--radius);
        background: var(--surface);
        border: 1px solid var(--border);
        box-shadow: var(--shadow);
      }}
      .metric-label, .eyebrow, .section-title {{
        text-transform: uppercase;
        letter-spacing: .22em;
        font-size: .76rem;
        margin: 0 0 10px;
        color: inherit;
        opacity: .78;
      }}
      h1, h2 {{
        font-family: var(--display-font);
      }}
      h1 {{
        margin: 0;
        font-size: clamp(3rem, 7vw, 5.8rem);
        line-height: .94;
        letter-spacing: -.05em;
      }}
      h2 {{
        margin: 0 0 8px;
        font-size: clamp(1.9rem, 3vw, 3rem);
        line-height: 1.02;
        letter-spacing: -.03em;
      }}
      h3 {{
        margin: 0 0 14px;
        font-size: 1.08rem;
      }}
      .section-kicker {{
        font-size: clamp(1rem, 1.8vw, 1.2rem);
        opacity: .88;
        margin: 18px 0 0;
      }}
      .hero-thesis {{
        font-size: clamp(1.08rem, 2vw, 1.38rem);
        line-height: 1.6;
        max-width: 42rem;
        margin: 22px 0 0;
      }}
      .card {{
        background: var(--surface);
        border: 1px solid var(--border);
        border-radius: var(--radius);
        box-shadow: var(--shadow);
        overflow: hidden;
        backdrop-filter: blur(12px);
      }}
      .card-body {{
        padding: 20px;
      }}
      .muted {{
        color: var(--muted);
      }}
      .hero-actions {{
        display: flex;
        flex-wrap: wrap;
        gap: 12px;
        margin-top: 22px;
      }}
      .button {{
        display: inline-flex;
        justify-content: center;
        align-items: center;
        min-height: 44px;
        padding: 12px 18px;
        border-radius: 999px;
        background: var(--accent);
        color: #fff;
        text-decoration: none;
        font-weight: 700;
        border: none;
      }}
      .secondary-button {{
        background: rgba(255,255,255,.14);
        border: 1px solid rgba(255,255,255,.24);
      }}
      .compact-button {{
        width: 100%;
      }}
      .source-button {{
        margin-top: 14px;
        width: auto;
      }}
      .section-head {{
        margin-bottom: 32px;
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
        grid-template-columns: 1.2fr 1fr;
      }}
      .feature-grid {{
        display: grid;
        grid-template-columns: minmax(0, 1.15fr) minmax(280px, .85fr);
        gap: 20px;
      }}
      .img-wrap {{
        position: relative;
        overflow: hidden;
        background: linear-gradient(135deg, var(--primary), var(--accent));
      }}
      .img-wrap img {{
        position: absolute;
        inset: 0;
        width: 100%;
        height: 100%;
        object-fit: cover;
      }}
      .img-wrap::after {{
        content: attr(data-label);
        position: absolute;
        left: 14px;
        right: 14px;
        bottom: 12px;
        color: rgba(255,255,255,.94);
        font-size: .82rem;
        font-weight: 700;
        text-shadow: 0 1px 6px rgba(0,0,0,.55);
      }}
      .premium-image::before {{
        content: "";
        position: absolute;
        inset: 0;
        background: linear-gradient(180deg, rgba(0,0,0,0) 45%, rgba(0,0,0,.35) 100%);
        z-index: 1;
      }}
      .premium-image img,
      .premium-image::after {{
        z-index: 2;
      }}
      .feature-header, .food-header, .price-row {{
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 12px;
      }}
      .price-row {{
        align-items: baseline;
        margin: 16px 0;
      }}
      .rating {{
        color: var(--accent);
        font-weight: 700;
      }}
      .vibe-pill, .inline-badge, .badge, .chip, .price-badge, .row-label {{
        display: inline-flex;
        align-items: center;
        justify-content: center;
        border-radius: 999px;
        font-size: .76rem;
        letter-spacing: .06em;
        text-transform: uppercase;
      }}
      .inline-badge, .badge {{
        padding: 8px 12px;
        background: var(--accent);
        color: #fff;
      }}
      .chip {{
        background: rgba(15,23,42,.06);
        padding: 6px 10px;
      }}
      .chip-row {{
        display: flex;
        flex-wrap: wrap;
        gap: 8px;
        margin-bottom: 18px;
      }}
      .price-badge {{
        color: #fff;
        padding: 8px 10px;
        min-width: 52px;
      }}
      .row-label {{
        margin-top: 10px;
        padding: 6px 10px;
        background: color-mix(in srgb, var(--accent) 18%, white);
        color: var(--text);
      }}
      .notes, .checklist, .comparison-notes {{
        margin: 18px 0 0;
        padding: 0;
        list-style: none;
      }}
      .compact-notes {{
        margin-top: 10px;
      }}
      .notes li, .checklist li, .comparison-notes li {{
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
      .comparison-notes li::before {{
        content: "•";
        position: absolute;
        left: 0;
        color: var(--accent);
        font-weight: 700;
      }}
      .temp-badge {{
        display: inline-flex;
        padding: 10px 14px;
        background: var(--primary);
        color: #fff;
        margin: 14px 0;
        border-radius: 999px;
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
        color: var(--muted);
        font-size: .78rem;
        text-transform: uppercase;
        letter-spacing: .08em;
      }}
      tbody tr:nth-child(even) {{
        background: rgba(15,23,42,.03);
      }}
      .winner-row {{
        background: color-mix(in srgb, var(--accent) 14%, white) !important;
      }}
      .cheapest-row {{
        background: color-mix(in srgb, var(--accent) 10%, white) !important;
        font-weight: 700;
      }}
      .price-text {{
        color: var(--accent);
        font-weight: 700;
      }}
      .table-stay strong {{
        display: block;
      }}
      .text-link {{
        color: var(--accent);
        font-weight: 700;
        text-decoration: none;
      }}
      .detail-card {{
        border-top: 4px solid var(--accent);
        padding: 20px;
      }}
      .logistics-brief {{
        padding: 20px;
      }}
      .flight-stats {{
        display: flex;
        gap: 24px;
        flex-wrap: wrap;
        margin-top: 12px;
      }}
      .flight-stat {{
        display: flex;
        flex-direction: column;
        align-items: center;
        text-align: center;
        gap: 6px;
        min-width: 90px;
        flex: 1;
      }}
      .flight-stat svg {{
        color: var(--accent);
      }}
      .stat-value {{
        font-size: 1.2rem;
        font-weight: 700;
      }}
      .stat-label {{
        font-size: .76rem;
        color: var(--muted);
        text-transform: uppercase;
        letter-spacing: .06em;
      }}
      .stay-card {{
        display: flex;
        flex-direction: column;
      }}
      .stay-card--recommended {{
        border-left: 4px solid var(--accent);
        background: color-mix(in srgb, var(--accent) 4%, var(--surface));
      }}
      .icon-inline {{
        display: inline-flex;
        vertical-align: middle;
        margin-right: 6px;
        color: var(--accent);
      }}
      .neighborhood-headline {{
        margin: 0 0 8px;
        line-height: 1.5;
      }}
      .neighborhood-details {{
        margin-top: 4px;
      }}
      .neighborhood-details summary {{
        cursor: pointer;
        color: var(--accent);
        font-weight: 600;
        font-size: .88rem;
      }}
      .neighborhood-details p {{
        margin: 8px 0 0;
        color: var(--muted);
        font-size: .92rem;
        line-height: 1.55;
      }}
      .rail-metric {{
        display: flex;
        justify-content: space-between;
        align-items: baseline;
        padding: 8px 0;
        border-bottom: 1px solid var(--border);
      }}
      .rail-metric:last-child {{
        border-bottom: none;
      }}
      .rail-metric-label {{
        font-size: .82rem;
        color: var(--muted);
      }}
      .rail-metric-value {{
        font-weight: 700;
        font-size: .94rem;
      }}
      .stay-map-card {{
        overflow: visible;
      }}
      .stay-map-canvas {{
        height: 440px;
        border-radius: calc(var(--radius) - 4px);
        overflow: hidden;
        margin-top: 16px;
        border: 1px solid var(--border);
      }}
      .stay-map-marker {{
        width: 28px;
        height: 28px;
        border-radius: 999px;
        background: var(--primary);
        color: #fff;
        display: grid;
        place-items: center;
        border: 2px solid #fff;
        box-shadow: 0 10px 24px rgba(15, 23, 42, .22);
        font-size: 1rem;
        font-weight: 800;
      }}
      .stay-map-marker--recommended {{
        background: var(--accent);
        transform: scale(1.08);
      }}
      .stay-map-popup {{
        min-width: 180px;
      }}
      .stay-map-popup strong {{
        display: block;
        margin-bottom: 6px;
      }}
      .stay-map-popup p {{
        margin: 0 0 8px;
        color: var(--muted);
      }}
      .stay-map-popup-location {{
        font-size: .88rem;
      }}
      .stay-map-popup a {{
        color: var(--accent);
        font-weight: 700;
        text-decoration: none;
      }}
      .expandable-grid {{
        grid-column: 1 / -1;
      }}
      .expandable-grid summary {{
        cursor: pointer;
        color: var(--accent);
        font-weight: 700;
        margin-top: 6px;
      }}
      .expanded-grid {{
        margin-top: 16px;
      }}
      .source-host {{
        margin: 14px 0 0;
        font-size: .8rem;
        letter-spacing: .04em;
        text-transform: uppercase;
        color: var(--muted);
      }}
      .tradeoff {{
        margin-top: 20px;
        padding-top: 14px;
        border-top: 1px solid var(--border);
        color: var(--muted);
      }}
      .closing-shell {{
        background: linear-gradient(140deg, color-mix(in srgb, var(--primary) 88%, black), var(--primary));
        color: #fff;
      }}
      .closing-shell .notes li::before {{
        color: var(--accent);
      }}
      {render_motion_css(style.motion_profile)}
      @media (max-width: 1220px) {{
        .brief-shell {{
          grid-template-columns: 1fr;
        }}
        .summary-rail {{
          position: static;
        }}
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
        .brief-shell {{
          padding: 12px 18px 24px;
        }}
        .hero-section,
        .feature-grid,
        .three-up,
        .two-up,
        .weather-grid {{
          grid-template-columns: 1fr;
        }}
      }}
      @media print {{
        #sidebar,
        .summary-rail,
        .progress-track {{
          display: none !important;
        }}
        #content {{
          margin-left: 0;
        }}
        .brief-shell {{
          display: block;
          padding: 0;
        }}
        .section {{
          break-inside: avoid;
        }}
      }}
    </style>
    """


def render_html(deck: DeckSpec, style: StylePreset, result: CurationOutput) -> str:
    sections_html = "".join(render_section(section, deck, style, result) for section in deck.sections)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>{_render_head(deck, style)}</head>
<body>
  <div class="progress-track"><span id="progress-bar"></span></div>
  {_render_sidebar(deck)}
  <main id="content">
    <div class="brief-shell">
      <div class="brief-main">{sections_html}</div>
      {_render_summary_rail(deck, result)}
    </div>
  </main>
  <script>{render_motion_js()}</script>
  {_render_stay_map_bootstrap(deck)}
</body>
</html>
"""
