"""
Visual interface for offline-study-bridge, in Streamlit.

Consumes the existing FastAPI API (app/main.py) over HTTP -- doesn't
duplicate any agent logic, just presents the result in a visual,
intuitive way.

To run: needs the API running in parallel (another terminal):
    uvicorn app.main:app --reload
And then, in this terminal:
    streamlit run streamlit_app.py
"""

import csv
import html as html_module
import io
import json
import os
from datetime import datetime

import requests
import streamlit as st
import streamlit.components.v1 as components

API_URL = "http://localhost:8000"

# The card-type -> emoji map lives in app/graph/state.py and is used by
# the generated offline HTML (respond_node). The interactive deck below
# uses inline SVG icons instead -- see TYPE_ICONS_SVG.

# Inline outline (stroke) SVG icons for the INTERACTIVE DECK ONLY. No
# external requests -- the whole markup is embedded, so it works offline.
# viewBox 0 0 24 24, stroke=currentColor so each icon takes the colour of
# the text beside it (navy on the front face, purple on the back face,
# tinted on the mini-board tiles). Small and flat, no fill, no effects.
# Paths are Feather-icon style (MIT), reproduced inline.
_SVG_ATTRS = (
    'xmlns="http://www.w3.org/2000/svg" width="16" height="16" '
    'viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
    'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"'
)
TYPE_ICONS_SVG = {
    # lamp / lightbulb (outline)
    "CONCEPT": (
        f"<svg {_SVG_ATTRS}>"
        '<path d="M9 18h6"/><path d="M10 22h4"/>'
        '<path d="M15.09 14c.18-.98.65-1.74 1.41-2.5A4.65 4.65 0 0 0 18 8'
        ' 6 6 0 0 0 6 8c0 1 .23 2.23 1.5 3.5A4.6 4.6 0 0 1 8.91 14"/>'
        "</svg>"
    ),
    # target / crosshair (outline)
    "USE_CASE": (
        f"<svg {_SVG_ATTRS}>"
        '<circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="6"/>'
        '<circle cx="12" cy="12" r="2"/>'
        "</svg>"
    ),
    # warning triangle (outline)
    "PITFALL": (
        f"<svg {_SVG_ATTRS}>"
        '<path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3'
        'L13.71 3.86a2 2 0 0 0-3.42 0z"/>'
        '<line x1="12" y1="9" x2="12" y2="13"/>'
        '<line x1="12" y1="17" x2="12.01" y2="17"/>'
        "</svg>"
    ),
    # question mark in a circle (outline)
    "QA": (
        f"<svg {_SVG_ATTRS}>"
        '<circle cx="12" cy="12" r="10"/>'
        '<path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"/>'
        '<line x1="12" y1="17" x2="12.01" y2="17"/>'
        "</svg>"
    ),
    # list / summary (outline)
    "SUMMARY": (
        f"<svg {_SVG_ATTRS}>"
        '<line x1="8" y1="6" x2="21" y2="6"/>'
        '<line x1="8" y1="12" x2="21" y2="12"/>'
        '<line x1="8" y1="18" x2="21" y2="18"/>'
        '<line x1="3" y1="6" x2="3.01" y2="6"/>'
        '<line x1="3" y1="12" x2="3.01" y2="12"/>'
        '<line x1="3" y1="18" x2="3.01" y2="18"/>'
        "</svg>"
    ),
}


def _type_svg(card_type: str) -> str:
    """Inline SVG for a card type, falling back to the QA icon."""
    return TYPE_ICONS_SVG.get(card_type, TYPE_ICONS_SVG["QA"])
HISTORY_FILE = os.path.join(os.path.dirname(__file__), "history.json")


def build_anki_csv(flashcards: list) -> str:
    """
    Renders the flashcards as Anki-importable CSV text: one row per card,
    two columns (front, back), no header row -- the exact shape Anki
    reads via File > Import. csv.writer quotes/escapes any field that
    contains a comma, quote or newline.
    """
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    for fc in flashcards:
        writer.writerow([fc.get("front", ""), fc.get("back", "")])
    return buffer.getvalue()

st.set_page_config(
    page_title="Attune",
    #page_icon="📚",
    layout="wide",
)

# --- Custom styling: same palette as before, used with more contrast and hierarchy ---
st.markdown(
    """
    <style>
    header[data-testid="stHeader"] { display: none; }
    html, body { scroll-behavior: smooth; }
    body { overflow-x: hidden; }
   .block-container { padding-top: 1rem; padding-bottom: 2rem; background-color: #F5F3FE; }
    /* consistent vertical rhythm (steps of 0.25rem / 0.5rem) */
    [data-testid="stVerticalBlock"] { gap: 0.75rem; }
    [data-testid="stHeading"] { margin-top: 0.5rem; margin-bottom: 0.25rem; }
    hr { margin: 0.75rem 0 !important; }

    /* section headings: one consistent size / weight / colour */
    [data-testid="stHeading"] h2, [data-testid="stHeading"] h3 {
        color: #0B2E7C; font-weight: 700; font-size: 1.2rem; letter-spacing: -0.005em; }
    [data-testid="stCaptionContainer"] { color: #4A4F6A; }

    /* alerts / info boxes share the card corner radius */
    [data-testid="stAlert"] { border-radius: 14px; }

    /* hero: a dark band behind the title only; the page itself stays light */
    .hero {
        background: #0B2E7C; border-radius: 0 0 16px 16px;
        margin: -0.5rem 0 1.5rem 0; padding: 1.75rem 1.75rem 1.5rem 1.75rem;
        box-shadow: 0 12px 30px rgba(11,15,25,0.18);
    }
    .main-header { color: #FCFCFD; font-size: 2.6rem; font-weight: 700; margin: 0;
                   letter-spacing: -0.01em; line-height: 1.15; }
    .sub-header { color: #C7CBE0; font-size: 1.05rem; margin: 0.5rem 0 0 0; line-height: 1.5; }
    .sub-header strong { color: #FFFFFF; }

    /* --- responsive: stack columns, shrink the hero, keep text inside the viewport --- */
    @media (max-width: 768px) {
        .block-container { padding-left: 0.9rem; padding-right: 0.9rem; }
        [data-testid="stHorizontalBlock"] { flex-wrap: wrap; gap: 0.75rem; }
        [data-testid="stHorizontalBlock"] > [data-testid="column"],
        [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {
            min-width: 100% !important; flex: 1 1 100% !important;
        }
        .hero { margin: -0.5rem 0 1.25rem 0; padding: 1.35rem 1.15rem 1.15rem 1.15rem;
                border-radius: 0 0 14px 14px; }
        .main-header { font-size: 2rem; }
        .sub-header { font-size: 0.95rem; }
    }
    p, li, .sub-header { overflow-wrap: anywhere; }

    /* spring easing -- a slight overshoot before settling, Duolingo-style */
    .stButton>button, [data-testid="stDownloadButton"] button {
        background-color: #0B2E7C; color: white; font-weight: 600;
        border-radius: 10px; padding: 0.6rem 1.5rem; border: none;
        box-shadow: 0 2px 8px rgba(11,46,124,0.18);
        transition: background-color 0.2s ease,
                    transform 0.24s cubic-bezier(0.34, 1.56, 0.64, 1),
                    box-shadow 0.2s ease; }
    .stButton>button:hover, [data-testid="stDownloadButton"] button:hover {
        background-color: #14409E; color: white;
        transform: translateY(-2px) scale(1.02);
        box-shadow: 0 8px 20px rgba(11,46,124,0.28); }
    .stButton>button:active, [data-testid="stDownloadButton"] button:active {
        transform: translateY(1px) scale(0.96);
        box-shadow: 0 1px 4px rgba(11,46,124,0.18);
        transition: transform 0.08s ease, box-shadow 0.08s ease; }
    button:focus-visible, [role="tab"]:focus-visible, summary:focus-visible {
        outline: 2px solid #3D2B7C; outline-offset: 2px; }

    .source-badge-real, .source-badge-suggested, .status-badge {
        display: inline-block; padding: 0.35rem 0.85rem; border-radius: 999px;
        font-size: 0.85rem; font-weight: 700; line-height: 1.2; }
    .source-badge-real { background: #DEE0FB; color: #0B2E7C; }
    .source-badge-suggested { background: #EDEBFE; color: #3D2B7C;
                              border: 1px solid rgba(61,43,124,0.35); }
    .status-badge.ok { background: #16A34A; color: #ffffff; animation: okPulse 0.9s ease 1; }
    .status-badge.warn { background: #F59E0B; color: #3A2A00; }

    /* result sections ease in on (re)render */
    [data-testid="stHeading"], [data-testid="stMetric"], [data-testid="stIFrame"],
    .status-badge, .source-badge-real, .source-badge-suggested {
        animation: fadeInUp 0.45s cubic-bezier(0.34, 1.4, 0.64, 1) both; }
    @keyframes fadeInUp { from { opacity: 0; transform: translateY(12px); }
                          to { opacity: 1; transform: translateY(0); } }
    @keyframes okPulse { 0% { box-shadow: 0 0 0 0 rgba(22,163,74,0.55); }
                         100% { box-shadow: 0 0 0 16px rgba(22,163,74,0); } }

    /* expander + tab hover/focus states (they are clickable but had none) */
    [data-testid="stExpanderDetails"] { transition: opacity 0.25s ease; }
    [data-testid="stExpander"] summary,
    details > summary { border-radius: 10px;
        transition: background-color 0.15s ease, color 0.15s ease; }
    [data-testid="stExpander"] summary:hover,
    details > summary:hover { background-color: #EDEBFE; color: #0B2E7C; }
    [role="tablist"] button[role="tab"] {
        transition: color 0.15s ease, border-color 0.15s ease; }
    [role="tablist"] button[role="tab"]:hover { color: #0B2E7C; }

    /* inputs adopt the navy accent on focus, to match the buttons */
    [data-baseweb="input"]:focus-within, [data-baseweb="textarea"]:focus-within,
    [data-baseweb="select"]:focus-within, [data-baseweb="base-input"]:focus-within {
        border-color: #0B2E7C !important; }

    .fade-in-section { animation: fadeInUp 0.4s cubic-bezier(0.34, 1.4, 0.64, 1) both; }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    '<div class="hero">'
    '<p class="main-header"> Attune </p>'
    '<p class="sub-header">Two things at once: a spaced repetition schedule and '
    "flashcards <strong>built around your real life</strong> — your work, your "
    "interests, your region — and, once downloaded, both work "
    "<strong>without internet</strong>, wherever you actually study.</p>"
    "</div>",
    unsafe_allow_html=True,
)

PIPELINE_DIAGRAM_SVG = """
<svg viewBox="0 0 980 260" xmlns="http://www.w3.org/2000/svg" style="width:100%; height:auto; font-family: -apple-system, sans-serif;">
  <defs>
    <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
      <path d="M0,0 L10,5 L0,10 z" fill="#0B2E7C"/>
    </marker>
    <marker id="arrowRetry" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
      <path d="M0,0 L10,5 L0,10 z" fill="#7C6FD1"/>
    </marker>
  </defs>

  <g font-size="13" font-weight="600">
    <rect x="10"  y="90" width="150" height="60" rx="12" fill="#0B2E7C"/>
    <text x="85"  y="115" fill="#FCFCFD" text-anchor="middle">parse_profile</text>
    <text x="85"  y="133" fill="#D9EBFE" text-anchor="middle" font-size="10" font-weight="400">questionnaire → profile</text>

    <rect x="195" y="90" width="150" height="60" rx="12" fill="#0B2E7C"/>
    <text x="270" y="115" fill="#FCFCFD" text-anchor="middle">extract_topics</text>
    <text x="270" y="133" fill="#D9EBFE" text-anchor="middle" font-size="10" font-weight="400">syllabus or goal → topics</text>

    <rect x="380" y="90" width="150" height="60" rx="12" fill="#0B2E7C"/>
    <text x="455" y="115" fill="#FCFCFD" text-anchor="middle">build_schedule</text>
    <text x="455" y="133" fill="#D9EBFE" text-anchor="middle" font-size="10" font-weight="400">spaced repetition → .ics</text>

    <rect x="565" y="90" width="160" height="60" rx="12" fill="#0B2E7C"/>
    <text x="645" y="115" fill="#FCFCFD" text-anchor="middle">generate_flashcards</text>
    <text x="645" y="133" fill="#D9EBFE" text-anchor="middle" font-size="10" font-weight="400">Freire-style contextualizing</text>

    <rect x="760" y="60" width="130" height="60" rx="12" fill="#3D2B7C"/>
    <text x="825" y="85"  fill="#FCFCFD" text-anchor="middle">validate</text>
    <text x="825" y="103" fill="#DEE0FB" text-anchor="middle" font-size="10" font-weight="400">verification</text>

    <rect x="760" y="170" width="130" height="60" rx="12" fill="#0B2E7C"/>
    <text x="825" y="195" fill="#FCFCFD" text-anchor="middle">respond</text>
    <text x="825" y="213" fill="#D9EBFE" text-anchor="middle" font-size="10" font-weight="400">.ics + HTML flashcards</text>
  </g>

  <g stroke="#0B2E7C" stroke-width="2" fill="none" marker-end="url(#arrow)">
    <path d="M160,120 L195,120"/>
    <path d="M345,120 L380,120"/>
    <path d="M530,120 L565,120"/>
    <path d="M725,110 L760,95"/>
  </g>

  <g stroke="#0B2E7C" stroke-width="2" fill="none" marker-end="url(#arrow)">
    <path d="M825,120 L825,170"/>
  </g>
  <text x="838" y="148" fill="#0B2E7C" font-size="10" font-weight="600">approved</text>

  <g stroke="#7C6FD1" stroke-width="2" fill="none" stroke-dasharray="5,4" marker-end="url(#arrowRetry)">
    <path d="M760,75 C 690,20 645,20 645,88"/>
  </g>
  <text x="700" y="35" fill="#5B4EA0" font-size="10" font-weight="700" text-anchor="middle">issues found → retry (max 3 attempts)</text>

  <g font-size="10" fill="#4A4F6A">
    <rect x="10" y="225" width="12" height="12" rx="3" fill="#0B2E7C"/>
    <text x="28" y="235">pipeline step</text>
    <rect x="140" y="225" width="12" height="12" rx="3" fill="#3D2B7C"/>
    <text x="158" y="235">verification (self-correcting)</text>
    <line x1="330" y1="231" x2="355" y2="231" stroke="#7C6FD1" stroke-width="2" stroke-dasharray="5,4"/>
    <text x="362" y="235">retry edge</text>
  </g>
</svg>
"""

with st.expander(" How the agent works (architecture)", expanded=False):
    components.html(PIPELINE_DIAGRAM_SVG, height=280, scrolling=False)
    st.caption(
        "The `validate` step is what makes this a *self-correcting* pipeline, "
        "not just a linear one: when it finds a problem (a forced analogy, a "
        "conceptual error), the graph loops back to regenerate the flashcards "
        "with that specific feedback — up to 3 attempts — instead of just "
        "flagging the issue and moving on."
    )

if "result" not in st.session_state:
    st.session_state.result = None


def load_history() -> list:
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def save_to_history(payload: dict, result: dict) -> None:
    history = load_history()
    label = (
        payload.get("free_form_goal")
        or (payload.get("syllabus_text") or "").splitlines()[0]
        or "Untitled study path"
    )
    entry = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "label": label[:80],
        "result": result,
    }
    history.insert(0, entry)
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


def build_flashcard_deck_html(flashcards: list) -> str:
    cards_for_js = [
        {
            "topic": fc.get("topic", "General"),
            "type": fc.get("type", "QA"),
            "icon_svg": _type_svg(fc.get("type", "QA")),
            "front": fc.get("front", ""),
            "back": fc.get("back", ""),
            "difficulty": fc.get("difficulty", "medium"),
            "used_interest": fc.get("used_interest", ""),
        }
        for fc in flashcards
    ]
    cards_json = json.dumps(cards_for_js, ensure_ascii=False).replace("</", "<\\/")

    mini_tiles = "".join(
        f'<div class="mini-card" onclick="jump({i})" title="{html_module.escape(fc.get("topic", ""))}">'
        f'<span class="mini-icon">{_type_svg(fc.get("type", "QA"))}</span>'
        f'<span class="mini-label">{i + 1}</span>'
        f'</div>'
        for i, fc in enumerate(flashcards)
    )

    return f"""
<style>
  * {{ box-sizing: border-box; font-family: -apple-system, "Segoe UI", sans-serif; }}
  .deck-wrap {{ width: 100%; padding: 0.5rem; }}
  .flip-scene {{ perspective: 1200px; width: 100%; }}
  .flip-card {{
    position: relative; width: 100%; height: 340px; cursor: pointer;
    transform-style: preserve-3d;
    transition: transform 0.55s cubic-bezier(0.34, 1.3, 0.55, 1);
  }}
  .flip-card.flipped {{ transform: rotateY(180deg); }}
  .flip-card.exit-left {{ transform: translateX(-30px) rotate(-2.5deg); opacity: 0;
                          transition: transform 0.16s ease, opacity 0.16s ease; }}
  .flip-card.exit-right {{ transform: translateX(30px) rotate(2.5deg); opacity: 0;
                           transition: transform 0.16s ease, opacity 0.16s ease; }}
  .flip-card.enter {{ transition: transform 0.32s cubic-bezier(0.34, 1.4, 0.64, 1),
                                  opacity 0.22s ease; }}
  .flip-face {{
    position: absolute; inset: 0; backface-visibility: hidden; border-radius: 16px;
    display: flex; flex-direction: column; align-items: center; justify-content: center;
    padding: 2rem; text-align: center; box-shadow: 0 8px 24px rgba(11,15,25,0.16);
    overflow-y: auto;
    transition: box-shadow 0.2s ease, transform 0.24s cubic-bezier(0.34, 1.4, 0.64, 1);
  }}
  .flip-card:hover .flip-face {{ box-shadow: 0 16px 40px rgba(11,15,25,0.30); }}
  .face-inner {{ width: 100%; max-height: 100%; display: flex; flex-direction: column; align-items: center; justify-content: center; }}
  .face-text pre {{
    text-align: left; background: rgba(0,0,0,0.2); border-radius: 10px; padding: 0.8rem 1rem;
    font-size: 0.85rem; overflow-x: auto; margin: 0.6rem 0; white-space: pre-wrap; word-break: break-word;
  }}
  .flip-back .face-text pre {{ background: rgba(11,46,124,0.1); }}
  .face-text code {{ font-family: "SFMono-Regular", Consolas, monospace; }}
  .flip-front {{ background: linear-gradient(135deg, #0B2E7C, #14409E); color: #FFFFFF !important; }}
  .flip-back {{ background: linear-gradient(135deg, #DEE0FB, #EDEBFE); color: #0B2E7C !important;
                transform: rotateY(180deg); }}
  .face-label {{ font-size: 0.78rem; font-weight: 700; letter-spacing: 0.08em;
                 margin-bottom: 1rem; opacity: 0.9; text-transform: uppercase; }}
  .face-label svg {{ width: 16px; height: 16px; vertical-align: -0.14em; margin-right: 0.15em; }}
  .flip-front .face-label {{ color: #D9EBFE !important; }}
  .flip-back .face-label {{ color: #3D2B7C !important; }}
  .face-text {{ font-size: 1.25rem; font-weight: 600; line-height: 1.5; word-wrap: break-word; width: 100%; }}
  .used-interest {{
    display: inline-flex; align-items: center; gap: 0.35rem;
    margin-top: 0.9rem; padding: 0.28rem 0.7rem; border-radius: 999px;
    background: rgba(61,43,124,0.12); color: #3D2B7C;
    font-size: 0.72rem; font-weight: 700; letter-spacing: 0.02em;
    max-width: 100%; overflow-wrap: anywhere;
  }}
  .used-interest.hidden {{ display: none; }}
  .nav-row {{ display: flex; gap: 0.6rem; margin-top: 1rem; }}
  .nav-btn {{
    flex: 1; min-width: 0; background: #0B2E7C; color: #fff; border: none; border-radius: 10px;
    padding: 0.6rem 0.75rem; font-weight: 600; font-size: 0.9rem; cursor: pointer;
    white-space: nowrap; box-shadow: 0 2px 8px rgba(11,46,124,0.18);
    transition: background-color 0.2s ease,
                transform 0.24s cubic-bezier(0.34, 1.56, 0.64, 1),
                box-shadow 0.2s ease;
  }}
  .nav-btn:hover {{ background: #14409E; transform: translateY(-2px) scale(1.02);
                    box-shadow: 0 8px 18px rgba(11,46,124,0.28); }}
  .nav-btn:active {{ transform: translateY(1px) scale(0.95);
                     box-shadow: 0 1px 4px rgba(11,46,124,0.18);
                     transition: transform 0.08s ease, box-shadow 0.08s ease; }}
  .nav-btn:focus-visible {{ outline: 2px solid #3D2B7C; outline-offset: 2px; }}
  .nav-btn.flip-btn {{ flex: 1.4; background: #3D2B7C; }}
  .nav-btn.flip-btn:hover {{ background: #4E3A99; }}
  .deck-hint {{ text-align: center; font-size: 0.75rem; color: #4A4F6A; margin-top: 0.55rem; }}
  .progress {{ text-align: center; font-size: 0.8rem; color: #4A4F6A; margin-top: 0.6rem; }}
  .mini-board {{
    display: flex; gap: 0.5rem; overflow-x: auto; overflow-y: hidden;
    margin-top: 1rem; padding-bottom: 0.5rem;
    scroll-behavior: smooth; -webkit-overflow-scrolling: touch;
    scrollbar-width: thin; scrollbar-color: #C7CBE0 transparent;
  }}
  .mini-board::-webkit-scrollbar {{ height: 6px; }}
  .mini-board::-webkit-scrollbar-thumb {{ background: #C7CBE0; border-radius: 999px; }}
  .mini-card {{
    flex: 0 0 auto; width: 52px; height: 52px; border-radius: 10px; background: #EDEBFE;
    color: #0B2E7C; display: flex; flex-direction: column; align-items: center;
    justify-content: center; cursor: pointer; border: 2px solid transparent;
    font-size: 0.65rem; font-weight: 700;
    transition: transform 0.2s cubic-bezier(0.34, 1.56, 0.64, 1),
                background-color 0.15s ease, border-color 0.15s ease;
  }}
  .mini-card:hover {{ background: #DEE0FB; transform: translateY(-2px) scale(1.05); }}
  .mini-card:active {{ transform: scale(0.94); transition: transform 0.08s ease; }}
  .mini-card.active {{ border-color: #3D2B7C; background: #DEE0FB; }}
  .mini-card.knew {{ background: #DCFCE7; color: #14532D; }}
  .mini-card.missed {{ background: #FEF3C7; color: #7C2D12; }}
  .mini-icon {{ display: flex; align-items: center; justify-content: center; }}
  .mini-icon svg {{ width: 18px; height: 18px; }}
  .assess-row {{ display: flex; gap: 0.6rem; margin-top: 1rem; justify-content: center; flex-wrap: wrap; }}
  .assess-btn {{
    border: 1px solid #0B2E7C; background: #FCFCFD; color: #0B2E7C; border-radius: 10px;
    padding: 0.45rem 1rem; font-size: 0.85rem; font-weight: 600; cursor: pointer;
    transition: transform 0.2s cubic-bezier(0.34, 1.56, 0.64, 1),
                background 0.15s ease, box-shadow 0.15s ease, color 0.15s ease;
  }}
  .assess-btn:hover {{ transform: translateY(-2px); box-shadow: 0 6px 14px rgba(11,46,124,0.18); }}
  .assess-btn:active {{ transform: translateY(1px) scale(0.95); transition: transform 0.08s ease; }}
  .assess-btn:focus-visible {{ outline: 2px solid #3D2B7C; outline-offset: 2px; }}
  .assess-btn.knew.chosen {{ background: #16A34A; color: #ffffff; border-color: #16A34A; }}
  .assess-btn.missed.chosen {{ background: #F59E0B; color: #3A2A00; border-color: #F59E0B; }}
  .assess-btn.pulse-knew {{ animation: assessPulseKnew 0.42s cubic-bezier(0.34, 1.56, 0.64, 1); }}
  .assess-btn.pulse-missed {{ animation: assessPulseMissed 0.42s cubic-bezier(0.34, 1.56, 0.64, 1); }}
  @keyframes assessPulseKnew {{
    0% {{ transform: scale(1); box-shadow: 0 0 0 0 rgba(22,163,74,0); }}
    40% {{ transform: scale(1.13); box-shadow: 0 0 0 7px rgba(22,163,74,0.30); }}
    100% {{ transform: scale(1); box-shadow: 0 0 0 0 rgba(22,163,74,0); }}
  }}
  @keyframes assessPulseMissed {{
    0% {{ transform: scale(1); box-shadow: 0 0 0 0 rgba(245,158,11,0); }}
    40% {{ transform: scale(1.10); box-shadow: 0 0 0 6px rgba(245,158,11,0.28); }}
    100% {{ transform: scale(1); box-shadow: 0 0 0 0 rgba(245,158,11,0); }}
  }}
  .score {{ text-align: center; font-size: 0.95rem; font-weight: 700; color: #3D2B7C;
            margin-top: 0.5rem; display: none; }}
  .score.show {{ display: block; animation: scorePop 0.5s cubic-bezier(0.34, 1.56, 0.64, 1); }}
  .score.good {{ color: #0F7A32; font-size: 1.02rem; }}
  @keyframes scorePop {{
    0% {{ transform: scale(0.6); opacity: 0; }}
    55% {{ transform: scale(1.12); opacity: 1; }}
    100% {{ transform: scale(1); opacity: 1; }}
  }}
  @media (max-width: 480px) {{
    .deck-wrap {{ padding: 0.25rem; }}
    .flip-card {{ height: 300px; }}
    .flip-face {{ padding: 1.3rem; }}
    .face-text {{ font-size: 1.05rem; }}
    .face-label {{ font-size: 0.72rem; margin-bottom: 0.75rem; }}
    .nav-btn {{ padding: 0.55rem 0.4rem; font-size: 0.8rem; }}
    .nav-row {{ gap: 0.4rem; }}
    .mini-card {{ width: 46px; height: 46px; }}
  }}
</style>

<div class="deck-wrap">
  <div class="flip-scene">
    <div class="flip-card" id="flipCard">
      <div class="flip-face flip-front">
        <div class="face-inner">
          <div class="face-label" id="frontLabel"></div>
          <div class="face-text" id="frontText"></div>
        </div>
      </div>
      <div class="flip-face flip-back">
        <div class="face-inner">
          <div class="face-label" id="backLabel"></div>
          <div class="face-text" id="backText"></div>
          <div class="used-interest hidden" id="usedInterest"></div>
          <div class="assess-row" id="assessRow">
            <button type="button" class="assess-btn knew" onclick="assess('knew', event)">👍 I knew it</button>
            <button type="button" class="assess-btn missed" onclick="assess('missed', event)">👎 I didn't</button>
          </div>
        </div>
      </div>
    </div>
  </div>

  <div class="nav-row">
    <button class="nav-btn" onclick="go(-1)">⬅️ Previous</button>
    <button class="nav-btn flip-btn" onclick="flipCard()">🔄 Flip</button>
    <button class="nav-btn" onclick="go(1)">Next ➡️</button>
  </div>
  <div class="deck-hint">Tap the card or press Flip to see the answer</div>
  <div class="progress" id="progressLabel"></div>
  <div class="score" id="scoreLabel"></div>

  <div class="mini-board" id="miniBoard">
    {mini_tiles}
  </div>
</div>

<script>
  const cards = {cards_json};
  let idx = 0;
  let flipped = false;
  let scoreShown = false;
  const seen = {{}};
  const assessments = {{}};

  function esc(s) {{
    if (!s) return '';
    const d = document.createElement('div');
    d.innerText = s;
    return d.innerHTML;
  }}

  function formatText(raw) {{
    if (!raw) return '';
    if (!raw.includes('```')) {{
      return esc(raw).replace(/\\n/g, '<br>');
    }}
    const parts = raw.split(/```(\\w*)\\n?([\\s\\S]*?)```/g);
    let out = '';
    for (let i = 0; i < parts.length; i++) {{
      if (i % 3 === 0) {{
        out += esc(parts[i]).replace(/\\n/g, '<br>');
      }} else if (i % 3 === 2) {{
        out += '<pre><code>' + esc(parts[i].trim()) + '</code></pre>';
      }}
    }}
    return out;
  }}

  function renderMini() {{
    document.querySelectorAll('.mini-card').forEach((el, i) => {{
      el.classList.toggle('active', i === idx);
      el.classList.toggle('knew', assessments[i] === 'knew');
      el.classList.toggle('missed', assessments[i] === 'missed');
    }});
  }}

  function renderAssessState() {{
    const row = document.getElementById('assessRow');
    if (!row) return;
    const btns = row.getElementsByTagName('button');
    btns[0].classList.toggle('chosen', assessments[idx] === 'knew');
    btns[1].classList.toggle('chosen', assessments[idx] === 'missed');
  }}

  function updateScore() {{
    const el = document.getElementById('scoreLabel');
    if (!el) return;
    if (!cards.length || Object.keys(seen).length < cards.length) {{
      el.classList.remove('show', 'good');
      el.style.display = 'none';
      return;
    }}
    let knew = 0;
    for (const k in assessments) {{ if (assessments[k] === 'knew') knew++; }}
    el.innerText = 'You knew ' + knew + ' of ' + cards.length + ' cards';
    el.classList.toggle('good', knew / cards.length > 0.7);
    if (!scoreShown) {{
      scoreShown = true;
      el.classList.remove('show');
      void el.offsetWidth;
      el.classList.add('show');
    }} else {{
      el.style.display = 'block';
    }}
  }}

  function assess(kind, e) {{
    if (e && e.stopPropagation) e.stopPropagation();
    assessments[idx] = kind;
    renderAssessState();
    renderMini();
    updateScore();
    const row = document.getElementById('assessRow');
    if (row) {{
      const btns = row.getElementsByTagName('button');
      const btn = kind === 'knew' ? btns[0] : btns[1];
      const cls = kind === 'knew' ? 'pulse-knew' : 'pulse-missed';
      btn.classList.remove(cls);
      void btn.offsetWidth;
      btn.classList.add(cls);
    }}
  }}

  function render() {{
    const c = cards[idx];
    if (!c) return;
    document.getElementById('frontLabel').innerHTML =
      (c.icon_svg || '') + ' ' + esc((c.type || 'QA') + ' · ' + (c.topic || '').toUpperCase() + ' · ' + (c.difficulty || '').toUpperCase() + ' · QUESTION');
    document.getElementById('frontText').innerHTML = formatText(c.front);
    document.getElementById('backLabel').innerHTML =
      (c.icon_svg || '') + ' ' + esc((c.type || 'QA') + ' · ' + (c.topic || '').toUpperCase() + ' · ' + (c.difficulty || '').toUpperCase() + ' · ANSWER');
    document.getElementById('backText').innerHTML = formatText(c.back);
    const ui = document.getElementById('usedInterest');
    if (ui) {{
      if (c.used_interest) {{
        ui.innerText = ' 🎯personalized using: ' + c.used_interest;
        ui.classList.remove('hidden');
      }} else {{
        ui.innerText = '';
        ui.classList.add('hidden');
      }}
    }}
    document.getElementById('progressLabel').innerText = 'Card ' + (idx + 1) + ' of ' + cards.length;
    seen[idx] = true;
    renderMini();
    renderAssessState();
    updateScore();
    document.getElementById('flipCard').classList.remove('flipped');
    flipped = false;
  }}

  function flipCard() {{
    flipped = !flipped;
    document.getElementById('flipCard').classList.toggle('flipped', flipped);
  }}

  function go(delta) {{
    const card = document.getElementById('flipCard');
    const exitCls = delta > 0 ? 'exit-left' : 'exit-right';
    card.classList.add(exitCls);
    setTimeout(() => {{
      idx = (idx + delta + cards.length) % cards.length;
      card.classList.remove(exitCls);
      card.classList.add('enter');
      render();
      setTimeout(() => card.classList.remove('enter'), 340);
    }}, 160);
  }}

  function jump(i) {{
    idx = i;
    render();
  }}

  document.getElementById('flipCard').addEventListener('click', flipCard);
  render();
</script>
"""


def render_result(result: dict, key_prefix: str = "main") -> None:
    st.markdown('<div class="fade-in-section">', unsafe_allow_html=True)
    st.divider()

    col_a, col_b, col_c = st.columns(3)
    col_a.metric("Topics", len(result["topics"]))
    col_b.metric("Flashcards", result.get("num_flashcards", "-"))
    with col_c:
        st.caption("Verification status")
        if result["approved"]:
            st.markdown(
                '<span class="status-badge ok">✅ Approved</span>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                '<span class="status-badge warn">⚠️ Has issues</span>',
                unsafe_allow_html=True,
            )

    if result.get("topics_source") == "general_suggestion":
        st.markdown(
            '<span class="source-badge-suggested"> Topics suggested by the agent '
            "(no syllabus provided) — worth checking if they cover what you need</span>",
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            '<span class="source-badge-real">Topics extracted from your syllabus</span>',
            unsafe_allow_html=True,
        )

    removed_cards = result.get("removed_flashcards", [])
    if removed_cards:
        st.info(
            f"🔒 {len(removed_cards)} flashcard(s) were withheld from this set: "
            "verification flagged a problem and the automatic retry could not fix "
            "it, so they are not shown here — veracity over completeness."
        )
    if not result["approved"] and result.get("issues_found"):
        with st.expander(
            " Verification notes (technical detail)",
            expanded=False,
            key=f"{key_prefix}_issues_expander",
        ):
            if removed_cards:
                st.caption("Withheld cards (not shown to the student):")
                for fc in removed_cards:
                    st.write(
                        f"- [{fc.get('type', '?')}] *{fc.get('topic', '')}* — {fc.get('front', '')}"
                    )
            st.caption("Raw verification findings:")
            for p in result["issues_found"]:
                st.write(f"- **[{p['issue_type']}]** {p['description']}")

    st.subheader("📋 Your identified profile")
    st.caption(
        "This is used to make your flashcards concrete and personal — look for "
        "the 🎯 tag on cards that used one of your interests as the example."
    )
    profile = result["student_profile"]
    st.write(
        f"**Work:** {profile['works']} · "
        f"**Region:** {profile['region']} · "
        f"**Interests:** {', '.join(profile['interests']) or 'not identified'}"
    )

    st.subheader("🗂️ Topics in your path")
    st.write(" → ".join(result["topics"]))

    explanations = result.get("topic_explanations", {}) or {}
    study_guide = [
        (topic, explanations.get(topic, ""))
        for topic in result["topics"]
        if (explanations.get(topic) or "").strip()
    ]
    if study_guide:
        st.subheader("Study guide — read this first")
        st.caption(
            "Click each topic below to open a short overview — read it before "
            "you start practicing with the flashcards."
        )
        for topic, text in study_guide:
            with st.expander(f"📖 {topic}"):
                st.write(text)

    st.subheader("Your flashcards")

    flashcards = result.get("flashcards", [])
    if flashcards:
        deck_html = build_flashcard_deck_html(flashcards)
        components.html(deck_html, height=560, scrolling=False)
    else:
        components.html(result["flashcards_html"], height=500, scrolling=True)

    st.subheader("⬇️ Download for offline use")
    dl_col1, dl_col2, dl_col3 = st.columns(3)
    with dl_col1:
        st.download_button(
            "📅 Download calendar (.ics)",
            data=result["ics_content"],
            file_name="study_path.ics",
            mime="text/calendar",
            use_container_width=True,
            key=f"{key_prefix}_ics_download",
        )
    with dl_col2:
        st.download_button(
            "🃏 Download flashcards (.html)",
            data=result["flashcards_html"],
            file_name="flashcards.html",
            mime="text/html",
            use_container_width=True,
            key=f"{key_prefix}_html_download",
        )
    with dl_col3:
        st.download_button(
            "📇 Download flashcards (Anki CSV)",
            data=build_anki_csv(result.get("flashcards", [])),
            file_name="flashcards_anki.csv",
            mime="text/csv",
            use_container_width=True,
            key=f"{key_prefix}_csv_download",
        )

    st.caption(
        "💡 All three files work **without internet** once downloaded: import "
        "the `.ics` into any calendar app, open the `.html` directly in a "
        "browser, or import the `.csv` into Anki (File → Import)."
    )
    st.markdown("</div>", unsafe_allow_html=True)


tab_generate, tab_history = st.tabs(["📚 Generate", "📜 Saved History"])

with tab_generate:
    with st.form("path_form"):
        st.markdown(
            '<div style="background: #D9EBFE; border-radius: 14px; padding: 1rem 1.25rem; '
            'margin-bottom: 1.25rem; color: #0B2E7C; font-size: 0.9rem; line-height: 1.5;">'
            '💡 Your answers below aren\'t just for a report — they shape the '
            'actual flashcards and schedule you get: examples from your real '
            'work, interests and region, AND a pace that matches how much '
            'time you actually have, instead of a one-size-fits-all plan.'
            '</div>',
            unsafe_allow_html=True,
        )
        col1, col2 = st.columns(2)

        with col1:
            questionnaire_answers = st.text_area(
                "Tell us a bit about yourself",
                placeholder="E.g.: I work at a farm supply store, I like soccer and "
                "music, I study in an area with unreliable internet.",
                height=120,
            )
            study_time = st.selectbox(
                "How much time can you realistically study per day?",
                options=[
                    "Less than 30 minutes (I work/have little free time)",
                    "30 to 90 minutes",
                    "More than 90 minutes (I don't work / study full time)",
                ],
            )
            start_date = st.date_input("Study start date")

        with col2:
            mode = st.radio(
                "Do you have a defined syllabus/curriculum?",
                options=["Yes, I'll paste the syllabus", "No, I only know what I want to learn"],
                horizontal=False,
            )

            if mode == "Yes, I'll paste the syllabus":
                syllabus_text = st.text_area(
                    "Paste the course syllabus here",
                    placeholder="1. Fractions\n2. Percentages\n3. Rule of three",
                    height=120,
                )
                free_form_goal = None
            else:
                free_form_goal = st.text_area(
                    "What's the main topic or final learning goal you're working toward?",
                    placeholder="E.g.: I want to pass the ENEM math section, focusing "
                    "on algebra and geometry. Or: I want to learn Python for data "
                    "analysis, starting from scratch.",
                    height=90,
                    help="Be specific about the subject AND the end goal (an exam, "
                    "a certification, a skill) -- this directly shapes which topics "
                    "get extracted and how the flashcards are written.",
                )
                syllabus_text = None

        submitted = st.form_submit_button("✨ Generate my study path")

    if submitted:
        if not questionnaire_answers.strip():
            st.error("Tell us a bit about yourself before continuing.")
        elif mode == "Yes, I'll paste the syllabus" and not (syllabus_text and syllabus_text.strip()):
            st.error("Paste the syllabus text, or choose the option without syllabus.")
        elif mode != "Yes, I'll paste the syllabus" and not (free_form_goal and free_form_goal.strip()):
            st.error("Describe your learning topic/goal.")
        else:
            full_questionnaire = (
                f"{questionnaire_answers.strip()} Available study time per day: {study_time}."
            )
            payload = {
                "questionnaire_answers": full_questionnaire,
                "syllabus_text": syllabus_text,
                "free_form_goal": free_form_goal,
                "start_date": start_date.strftime("%Y-%m-%d"),
            }
            with st.spinner(
                "Generating your personalized path... (this usually takes up to a minute or two)"
            ):
                try:
                    resp = requests.post(f"{API_URL}/generate-path", json=payload, timeout=300)
                    resp.raise_for_status()
                    new_result = resp.json()
                    st.session_state.result = new_result
                    save_to_history(payload, new_result)
                except requests.exceptions.ConnectionError:
                    st.error(
                        "Couldn't connect to the API. Make sure it's running "
                        "in another terminal: `uvicorn app.main:app --reload`"
                    )
                except requests.exceptions.Timeout:
                    st.error(
                        "The request timed out — the model took too long to respond. "
                        "Try again in a moment."
                    )
                except Exception as e:
                    st.error(
                        "Something went wrong while generating your study path. "
                        "This is often a temporary API issue — try again in a moment."
                    )
                    st.caption(f"Technical detail: {e}")

    if st.session_state.result:
        render_result(st.session_state.result, key_prefix="generate")
    else:
        st.info(
            "👇 Fill in the form and click **Generate my study path** — your "
            "schedule, study guide and flashcards will show up here."
        )

with tab_history:
    st.subheader("📜 Saved study paths")
    st.caption(
        "Every generated path is saved locally to `history.json`, so it "
        "survives a page reload (F5) — reopen any of them below without "
        "calling the API again."
    )

    history = load_history()
    if not history:
        st.info("No saved study paths yet. Generate one in the **Generate** tab first.")
    else:
        for i, entry in enumerate(history):
            with st.expander(f"🗓️ {entry['timestamp']} — {entry['label']}"):
                num_cards = entry["result"].get("num_flashcards", "-")
                num_topics = len(entry["result"].get("topics", []))
                st.write(f"{num_topics} topics · {num_cards} flashcards")
                if st.button("📂 Load this path", key=f"load_history_{i}"):
                    st.session_state.result = entry["result"]
                    st.rerun()

    if st.session_state.result:
        render_result(st.session_state.result, key_prefix="history")