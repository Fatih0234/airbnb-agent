import json
import os

from pydantic_ai import Agent
from pydantic_ai.settings import ModelSettings
import anthropic
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.providers.anthropic import AnthropicProvider

from ..config import MINIMAX_BASE_URL, get_minimax_api_key, get_model_name
from ..schemas import CurationOutput

# ---------------------------------------------------------------------------
# Vibe → colour palette
# ---------------------------------------------------------------------------

_PALETTES: dict[str, dict[str, str]] = {
    "historic":     {"primary": "#8B4513", "accent": "#D2691E", "bg": "#FFF8F0", "text": "#3D1C02"},
    "coastal":      {"primary": "#1E6B8C", "accent": "#4A9EBF", "bg": "#F0F7FA", "text": "#0D3347"},
    "urban":        {"primary": "#1A1A2E", "accent": "#4A90D9", "bg": "#F4F4F4", "text": "#111111"},
    "mountain":     {"primary": "#2D5016", "accent": "#6B8E23", "bg": "#F5F5F0", "text": "#1A2E0A"},
    "tropical":     {"primary": "#007A7A", "accent": "#FF6B6B", "bg": "#FFFDF0", "text": "#003D3D"},
    "cosmopolitan": {"primary": "#2C2C2C", "accent": "#C9A84C", "bg": "#FAFAFA", "text": "#111111"},
    "romantic":     {"primary": "#722F37", "accent": "#C8647A", "bg": "#FFF5F5", "text": "#3D0A10"},
}
_DEFAULT_PALETTE = {"primary": "#2C3E50", "accent": "#3498DB", "bg": "#F8F9FA", "text": "#1A252F"}


def _get_palette(vibe: str) -> dict[str, str]:
    key = vibe.lower().strip()
    for k, v in _PALETTES.items():
        if k in key or key in k:
            return v
    return _DEFAULT_PALETTE


def _fix_map_url(map_url: str | None) -> str | None:
    """Replace placeholder API key in map_url with the real key, if available."""
    if not map_url:
        return None
    real_key = os.getenv("GOOGLE_MAPS_API_KEY", "")
    if not real_key:
        return None
    if "YOUR_API_KEY" in map_url:
        map_url = map_url.replace("YOUR_API_KEY", real_key)
    # Drop if key is still missing or obviously fake
    if "YOUR_API_KEY" in map_url or "key=" not in map_url:
        return None
    return map_url


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
You are an expert front-end developer building a premium travel reference document. \
Turn the supplied trip JSON into a stunning, self-contained single-page HTML travel book.

══ OUTPUT RULES (follow precisely) ══
• Return ONLY raw HTML starting with <!DOCTYPE html>. No markdown, no code fences, no commentary.
• ALL CSS in one <style> block in <head>. ALL JS in one <script> block before </body>.
• Zero external resources — no CDN, no Google Fonts, no remote images beyond those in the data.
• Every <img> tag MUST have an onerror handler (see image pattern below).

══ CSS VARIABLES (use these names throughout) ══
:root {
  --primary: {PRIMARY};
  --accent:  {ACCENT};
  --bg:      {BG};
  --text:    {TEXT};
  --card-bg: #ffffff;
  --radius:  10px;
  --shadow:  0 2px 12px rgba(0,0,0,.10);
}

══ PAGE STRUCTURE ══
<body> has two children:
  1. <nav id="sidebar"> — fixed left, 170px wide, hidden below 768px
  2. <main id="content"> — margin-left: 170px on desktop, 0 on mobile

Sidebar:
• background: var(--primary); color: white; padding-top: 60px
• Nav links: one <a> per section, display:block, padding 12px 20px, no underline, white
• Active link: background rgba(255,255,255,.15); border-left: 3px solid var(--accent)
• Include a "Flights" nav link only if the flights section is rendered (non-null, non-empty options)
• Below 768px: sidebar becomes a sticky top bar, flex-row, overflow-x:auto

Smooth scroll: html { scroll-behavior: smooth }

Scroll-spy (JS): use IntersectionObserver on each section; when section enters viewport, \
add class "active" to matching sidebar link.

══ IMAGE PATTERN (use for every image slot) ══
Every image slot must be a wrapper div:

<div class="img-wrap" style="height:220px" data-label="PLACE NAME">
  <!-- Only include the <img> tag if a real URL is available; omit entirely when no URL -->
  <img src="URL" alt="PLACE NAME" loading="lazy"
       onerror="this.style.opacity=0">
</div>

CSS for .img-wrap:
  position:relative; overflow:hidden; border-radius:var(--radius) var(--radius) 0 0;
  background: linear-gradient(135deg, var(--primary) 0%, var(--accent) 100%);
  display:flex; align-items:center; justify-content:center;

CSS for .img-wrap img:
  position:absolute; inset:0; width:100%; height:100%;
  object-fit:cover; transition:opacity .3s;

CSS for .img-wrap::after:
  content: attr(data-label);
  position:absolute; bottom:12px; left:12px; right:12px;
  color:rgba(255,255,255,.9); font-size:.85rem; font-weight:600;
  text-shadow:0 1px 4px rgba(0,0,0,.6); pointer-events:none;

This way: real photos show when they load, gradient shows when they fail or are absent.

══ SECTIONS ══

──── 1. COVER (#cover) ────
Full-viewport-height hero. Background: linear-gradient(160deg, var(--primary) 60%, var(--accent)).
White text. Center-aligned content.
• Very large destination name (4–5rem, letter-spacing: -1px)
• Subtitle: dates · trip_type · N guests (1.2rem, opacity .85)
• Vibe pill badge: rounded, accent bg, white text, uppercase, letter-spacing 2px
No sidebar link for cover — sidebar starts at Stays.

──── 2. STAYS (#stays) ────
Horizontal-scroll card row (display:flex; overflow-x:auto; gap:20px; padding-bottom:12px).
Each stay card (min-width:280px; max-width:300px; flex-shrink:0):
  • img-wrap at top (height:180px); use FIRST url from image_urls array, or omit <img> if empty
  • Card body: name (bold, 1rem), rating as ★ stars (color:var(--accent)), price/night large + total small
  • Amenity chips: small rounded pills, background: #f0f0f0, font-size:.75rem, flex-wrap:wrap
  • "Book on Airbnb →" button at bottom: background var(--accent), white text, rounded, full-width
  • If url is null, button is disabled/muted
If stays array is empty: show a muted italic "No stays found" note.

──── 3. NEIGHBORHOOD (#neighborhood) ────
Three equal-width cards in a row (CSS grid, 3 cols, gap:16px) for Safety / Vibe / Walkability.
Each card: coloured top border (4px solid var(--accent)), padding 20px, title in var(--primary).
Below cards: Notable Notes as a styled list — each note prefixed with › , font-style normal.

──── 4. WEATHER (#weather) ────
Two-column grid (60%/40%).
Left: forecast_summary paragraph + big temperature badge (background var(--primary), white, rounded, 1.4rem).
Right: packing_tips as checklist — each item gets a ✓ prefix, accent colour, line separated.

──── 5. ACTIVITIES (#activities) ────
2-column CSS grid (gap:20px). Each card:
  • img-wrap (height:200px); use activity.image_url or omit <img> if null
  • Category badge: rounded pill, var(--accent) bg, white text, .7rem uppercase
  • Name: bold 1rem
  • Description: .9rem muted
If activities empty: muted note.

──── 6. FOOD (#food) ────
2-column CSS grid (gap:20px). Each card:
  • img-wrap (height:180px); use food.image_url or omit <img> if null
  • Name bold + cuisine italic + price badge ($ green, $$ amber, $$$ red — use inline bg colors)
  • Description: .9rem muted
If picks empty: muted note.

──── 7. FLIGHTS (#flights) ────
Only render this section if the JSON contains a "flights" key that is non-null AND has a
non-empty "options" array. If flights is null or options is empty, skip this section entirely
(no heading, no empty state — just omit it).

When rendering:
• Show search_summary as a muted subtitle below the section heading.
• Render a styled full-width table: columns Airline / Departs / Arrives / Duration / Stops / Class / Price.
• Highlight the cheapest row: background rgba(var(--accent-rgb, 74,158,191),.12); font-weight:600.
• Stops column: show "Non-stop" for 0, "1 stop" for 1, "N stops" for N>1.
• Duration column: convert duration_minutes to "Xh Ym" format.
• Price column: format as "$X" with accent colour.
• Also include cheapest_price_usd as a "Best price from $X" badge above the table.

──── 8. COMMUTE (#commute) ────
Table of options: columns From / To / Mode / Duration. Styled table, full-width, alternating rows.
If map_url is present and non-empty: render <img src="{map_url}" style="width:100%;border-radius:var(--radius);margin-top:16px" alt="Route map">.
If options empty: muted note.

══ GENERAL STYLE ══
• Section headings: .section-title — uppercase, letter-spacing:3px, font-size:.8rem,
  color:var(--primary); border-bottom:2px solid var(--accent); padding-bottom:8px; margin-bottom:24px
• Cards: background var(--card-bg); border-radius var(--radius); box-shadow var(--shadow);
  overflow:hidden; transition:transform .2s, box-shadow .2s
• Card hover: transform:translateY(-3px); box-shadow: 0 8px 24px rgba(0,0,0,.15)
• Section padding: 60px 40px on desktop; 32px 20px on mobile
• body: font-family: system-ui,-apple-system,sans-serif; font-size:15px;
  line-height:1.6; color:var(--text); background:var(--bg); margin:0
"""


def _build_prompt(result: CurationOutput) -> str:
    palette = _get_palette(result.destination_vibe)
    data = result.model_dump()

    # Replace placeholder keys in map_url so the model gets the real URL (or None)
    fixed_map_url = _fix_map_url(result.commute.map_url)
    data["commute"]["map_url"] = fixed_map_url

    prompt = SYSTEM_PROMPT
    prompt = prompt.replace("{PRIMARY}", palette["primary"])
    prompt = prompt.replace("{ACCENT}",  palette["accent"])
    prompt = prompt.replace("{BG}",      palette["bg"])
    prompt = prompt.replace("{TEXT}",    palette["text"])

    return (
        f"{prompt}\n\n"
        f"══ TRIP DATA ══\n"
        f"```json\n{json.dumps(data, indent=2, ensure_ascii=False)}\n```\n\n"
        "Generate the complete travel book HTML document now."
    )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

async def generate_slides(result: CurationOutput) -> str:
    model = AnthropicModel(
        get_model_name(),
        provider=AnthropicProvider(anthropic_client=anthropic.AsyncAnthropic(
            base_url=MINIMAX_BASE_URL, api_key=get_minimax_api_key()
        )),
    )
    agent = Agent(
        model,
        output_type=str,
        system_prompt=SYSTEM_PROMPT,
        retries=2,
    )
    r = await agent.run(_build_prompt(result), model_settings=ModelSettings(max_tokens=16000))
    html: str = r.output

    # Strip markdown fences if the model wrapped the output despite instructions
    if "```" in html:
        parts = html.split("```html", 1)
        if len(parts) == 2:
            html = parts[1].split("```")[0].strip()
        else:
            html = html.split("```", 1)[-1].rsplit("```", 1)[0].strip()

    return html
