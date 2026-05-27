"""Bloomberg-terminal-inspired Streamlit CSS overrides.

Layered on top of the dark theme defined in .streamlit/config.toml. This
module injects a single <style> block via st.markdown that:

  - forces monospace font on every text element
  - re-colours metric cards with amber labels + green/red value coloring
  - tightens metric, table, and tab spacing
  - replaces rounded corners with sharp boxy edges
  - styles dataframes with monospace right-aligned cells + amber headers
  - replaces tab dividers with hairline rules in amber

The palette is documented in `style.py` (PRIMARY, ACCENT, etc.) so plotly
chart code can match.
"""

from __future__ import annotations

import streamlit as st

# Bloomberg-evocative palette (matches style.py)
BG = "#000000"
PANEL_BG = "#0a0a0a"
BORDER = "#1f1f1f"
GRID = "#161616"
AMBER = "#ff8000"
AMBER_DIM = "#cc6600"
WHITE = "#e0e0e0"
WHITE_DIM = "#8a8a8a"
GREEN = "#00d100"
RED = "#ff3030"
CYAN = "#22d3ee"

_CSS = f"""
<style>
/* ------------------------------------------------------------------ */
/* Global: monospace font + tighter line height + true-black bg       */
/* ------------------------------------------------------------------ */
html, body, [class*="st-"], .stApp, .main, .block-container,
.stMarkdown, .stMetric, .stDataFrame, .stPlotlyChart,
.stTextInput, .stSelectbox, .stSlider, .stSelectSlider, .stRadio,
.stButton, .stTabs, h1, h2, h3, h4, h5, h6, p, div, span, label, code, pre {{
    font-family: 'IBM Plex Mono', 'JetBrains Mono', 'Menlo', 'Monaco', 'Courier New', monospace !important;
    -webkit-font-smoothing: antialiased;
}}

body, .stApp {{
    background-color: {BG} !important;
    color: {WHITE} !important;
}}

/* Sidebar */
section[data-testid="stSidebar"] > div:first-child {{
    background-color: {PANEL_BG} !important;
    border-right: 1px solid {BORDER} !important;
}}

/* Main content padding tightened */
.main .block-container {{
    padding-top: 0.5rem;
    padding-bottom: 1rem;
    padding-left: 1.5rem;
    padding-right: 1.5rem;
    max-width: 100% !important;
}}

/* ------------------------------------------------------------------ */
/* Headings: amber, uppercase-feel via wider letter-spacing            */
/* ------------------------------------------------------------------ */
h1, h2, h3, .stMarkdown h1, .stMarkdown h2, .stMarkdown h3 {{
    color: {AMBER} !important;
    letter-spacing: 0.02em;
    margin-top: 0.5rem !important;
    margin-bottom: 0.5rem !important;
    text-transform: uppercase;
    font-weight: 600 !important;
}}

h4, h5, h6, .stMarkdown h4, .stMarkdown h5, .stMarkdown h6 {{
    color: {AMBER_DIM} !important;
    letter-spacing: 0.04em;
    margin-top: 0.4rem !important;
    margin-bottom: 0.2rem !important;
    text-transform: uppercase;
    font-weight: 600 !important;
    font-size: 0.85rem !important;
}}

.stMarkdown p, .stMarkdown li, .stMarkdown div {{
    color: {WHITE} !important;
    font-size: 0.85rem !important;
}}

.stCaption, [data-testid="stCaptionContainer"] {{
    color: {WHITE_DIM} !important;
    font-size: 0.78rem !important;
}}

/* ------------------------------------------------------------------ */
/* Metric cards: amber label, monospace value, green/red delta         */
/* ------------------------------------------------------------------ */
[data-testid="stMetric"] {{
    background-color: {PANEL_BG};
    border: 1px solid {BORDER};
    padding: 0.5rem 0.75rem;
    border-radius: 0 !important;
}}
[data-testid="stMetricLabel"] {{
    color: {AMBER} !important;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    font-size: 0.72rem !important;
    font-weight: 600 !important;
}}
[data-testid="stMetricValue"] {{
    color: {WHITE} !important;
    font-size: 1.4rem !important;
    font-weight: 600 !important;
    font-variant-numeric: tabular-nums;
}}
[data-testid="stMetricDelta"] {{
    color: {WHITE_DIM} !important;
    font-size: 0.78rem !important;
}}

/* ------------------------------------------------------------------ */
/* Tabs: amber underline on active, dim grey on hover                 */
/* ------------------------------------------------------------------ */
.stTabs [data-baseweb="tab-list"] {{
    border-bottom: 1px solid {BORDER};
    gap: 0;
}}
.stTabs [data-baseweb="tab"] {{
    background-color: transparent !important;
    color: {WHITE_DIM} !important;
    border-radius: 0 !important;
    border: none !important;
    padding: 0.4rem 1rem !important;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    font-size: 0.8rem !important;
    font-weight: 600 !important;
}}
.stTabs [aria-selected="true"] {{
    color: {AMBER} !important;
    border-bottom: 2px solid {AMBER} !important;
}}
.stTabs [data-baseweb="tab"]:hover {{
    color: {AMBER_DIM} !important;
}}

/* ------------------------------------------------------------------ */
/* DataFrames: monospace, dark bg, amber column headers               */
/* ------------------------------------------------------------------ */
[data-testid="stDataFrame"] {{
    background-color: {PANEL_BG};
    border: 1px solid {BORDER};
    border-radius: 0 !important;
}}
[data-testid="stDataFrame"] table {{
    color: {WHITE} !important;
    font-family: 'IBM Plex Mono', monospace !important;
    font-size: 0.8rem !important;
}}
[data-testid="stDataFrame"] th {{
    background-color: {BG} !important;
    color: {AMBER} !important;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    font-weight: 600 !important;
    border-bottom: 1px solid {AMBER_DIM} !important;
}}
[data-testid="stDataFrame"] td {{
    border-color: {BORDER} !important;
    font-variant-numeric: tabular-nums;
}}

/* ------------------------------------------------------------------ */
/* Buttons + selectbox: boxy, amber accents                           */
/* ------------------------------------------------------------------ */
.stButton button, .stDownloadButton button {{
    background-color: {PANEL_BG} !important;
    color: {AMBER} !important;
    border: 1px solid {AMBER_DIM} !important;
    border-radius: 0 !important;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    font-weight: 600 !important;
}}
.stButton button:hover, .stDownloadButton button:hover {{
    background-color: {AMBER_DIM} !important;
    color: {BG} !important;
}}

.stSelectbox [data-baseweb="select"], .stSelectbox div[role="button"] {{
    background-color: {PANEL_BG} !important;
    border: 1px solid {BORDER} !important;
    border-radius: 0 !important;
}}

/* Slider track */
.stSlider [data-baseweb="slider"] {{
    color: {AMBER} !important;
}}

/* ------------------------------------------------------------------ */
/* Dividers + horizontal rules                                         */
/* ------------------------------------------------------------------ */
hr, [data-testid="stMarkdownContainer"] hr {{
    border-color: {BORDER} !important;
    margin: 0.5rem 0 !important;
}}

/* ------------------------------------------------------------------ */
/* Top header bar (Bloomberg-style status line)                        */
/* !important is necessary because the .stMarkdown div generic rule    */
/* above has higher specificity than a single .bbg-header class.       */
/* ------------------------------------------------------------------ */
.stMarkdown .bbg-header, .bbg-header {{
    background: linear-gradient(90deg, {BG} 0%, {PANEL_BG} 100%) !important;
    border-bottom: 1px solid {AMBER_DIM} !important;
    color: {AMBER} !important;
    padding: 0.4rem 1rem !important;
    margin: -0.5rem -1.5rem 0.5rem -1.5rem !important;
    font-family: 'IBM Plex Mono', 'Menlo', monospace !important;
    font-size: 0.82rem !important;
    letter-spacing: 0.08em !important;
    text-transform: uppercase !important;
    display: flex !important;
    justify-content: space-between !important;
    align-items: center !important;
}}
.stMarkdown .bbg-header .bbg-title, .bbg-header .bbg-title {{
    color: {AMBER} !important;
    font-weight: 700 !important;
    font-size: 0.85rem !important;
}}
.stMarkdown .bbg-header .bbg-title .ticker, .bbg-header .bbg-title .ticker {{
    background: {AMBER} !important;
    color: {BG} !important;
    padding: 2px 8px !important;
    margin-right: 10px !important;
    font-weight: 700 !important;
    letter-spacing: 0.04em !important;
}}
.stMarkdown .bbg-header .bbg-status, .bbg-header .bbg-status {{
    color: {WHITE_DIM} !important;
    font-size: 0.78rem !important;
}}
.stMarkdown .bbg-header .bbg-status .green, .bbg-header .bbg-status .green {{
    color: {GREEN} !important;
    font-weight: 700 !important;
}}
.stMarkdown .bbg-header .bbg-status .amber, .bbg-header .bbg-status .amber {{
    color: {AMBER} !important;
    font-weight: 700 !important;
}}

/* ------------------------------------------------------------------ */
/* Utility: positive/negative number tags (for inline coloring)        */
/* ------------------------------------------------------------------ */
.bbg-pos {{
    color: {GREEN} !important;
    font-weight: 600;
    font-variant-numeric: tabular-nums;
}}
.bbg-neg {{
    color: {RED} !important;
    font-weight: 600;
    font-variant-numeric: tabular-nums;
}}
.bbg-num {{
    font-variant-numeric: tabular-nums;
    font-family: 'IBM Plex Mono', monospace;
}}

/* Plotly chart container framing */
.stPlotlyChart > div {{
    border: 1px solid {BORDER};
    background: {BG};
}}

/* Reduce huge default spacing between elements */
[data-testid="stVerticalBlock"] > div:has(> .element-container) {{
    gap: 0.5rem;
}}
</style>
"""


def inject_bloomberg_css() -> None:
    """Call once at the top of app.py (after st.set_page_config)."""
    st.markdown(_CSS, unsafe_allow_html=True)


def render_header(title: str = "STATARB-13", subtitle: str = "Systematic Commodities Research",
                  status: str = "OPERATIONAL") -> None:
    """Render the Bloomberg-style title bar at the very top of the page."""
    from datetime import datetime
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    status_class = "green" if status.upper() in ("OPERATIONAL", "LIVE", "OK") else "amber"
    st.markdown(
        f"""
        <div class="bbg-header">
          <div class="bbg-title">
            <span class="ticker">{title}</span>{subtitle} &nbsp;&lt;GO&gt;
          </div>
          <div class="bbg-status">
            STATUS <span class="{status_class}">{status}</span>
            &nbsp;|&nbsp; {ts}
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
