"""
theme.py - "Lab Bench at Night" Design Language & CSS Injection
Instrument-grade ECE user interface styling for Streamlit.
"""

import textwrap
import urllib.parse
import streamlit as st

# Hardware Instrument Color Palette
COLORS = {
    "bg": "#070A0D",
    "panel": "#0E1419",
    "panel_border": "#1B2A33",
    "pcb_green": "#0B3D2E",
    "copper": "#C8742B",
    "phosphor_green": "#39FF88",
    "scope_amber": "#FFB000",
    "signal_cyan": "#35D0FF",
    "fail_red": "#FF4D5E",
    "text": "#D7E3EA",
    "muted": "#9FB3BE",  # High contrast muted text (>= 14px, #9FB3BE)
}

# Inline PCB Background Pattern (SVG data-URI, 4-6% opacity copper traces and vias)
PCB_SVG = (
    '<svg width="120" height="120" xmlns="http://www.w3.org/2000/svg">'
    '<g stroke="#C8742B" stroke-width="1.2" fill="none" stroke-linecap="round">'
    '<path d="M0,20 L40,20 L60,40 L100,40 L120,60" stroke-opacity="0.05"/>'
    '<path d="M20,120 L20,90 L50,60 L90,60 L120,30" stroke-opacity="0.05"/>'
    '<path d="M60,0 L60,30 L80,50 L80,100 L100,120" stroke-opacity="0.05"/>'
    '<path d="M0,80 L30,80 L50,100 L70,100" stroke-opacity="0.05"/>'
    '<circle cx="40" cy="20" r="3.5" stroke-opacity="0.06"/>'
    '<circle cx="40" cy="20" r="1.2" fill="#C8742B" fill-opacity="0.06"/>'
    '<circle cx="90" cy="60" r="3.5" stroke-opacity="0.06"/>'
    '<circle cx="90" cy="60" r="1.2" fill="#C8742B" fill-opacity="0.06"/>'
    '<circle cx="80" cy="100" r="3.5" stroke-opacity="0.06"/>'
    '<circle cx="80" cy="100" r="1.2" fill="#C8742B" fill-opacity="0.06"/>'
    '</g></svg>'
)
PCB_DATA_URI = f"data:image/svg+xml;utf8,{urllib.parse.quote(PCB_SVG)}"

# App Logo: Sine wave passing through resistor zigzag
LOGO_SVG = """
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 170 44" width="100%" height="44" fill="none">
  <!-- Sine wave input in signal cyan -->
  <path d="M 8 22 Q 18 8, 28 22 T 48 22 L 56 22" stroke="#35D0FF" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>
  <!-- Resistor zigzag in warm copper -->
  <path d="M 56 22 L 62 12 L 72 32 L 82 12 L 92 32 L 102 12 L 108 22" stroke="#C8742B" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>
  <!-- Output trace with probe node in phosphor green -->
  <path d="M 108 22 L 136 22" stroke="#39FF88" stroke-width="2.5" stroke-linecap="round"/>
  <circle cx="140" cy="22" r="4.5" fill="#39FF88"/>
  <circle cx="140" cy="22" r="8" stroke="#39FF88" stroke-width="1.2" stroke-opacity="0.5"/>
  <circle cx="8" cy="22" r="3" fill="#35D0FF"/>
</svg>
"""


def get_theme_css() -> str:
    """Return the complete CSS string for 'Lab Bench at Night' design language."""
    css = f"""
    <style>
    /* Google Fonts Import */
    @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:ital,wght@0,300;0,400;0,500;0,600;0,700;1,400&family=Share+Tech+Mono&family=Space+Grotesk:wght@400;500;600;700&display=swap');

    /* Design System CSS Variables */
    :root {{
        --bg-color: {COLORS['bg']};
        --panel-color: {COLORS['panel']};
        --panel-border: {COLORS['panel_border']};
        --pcb-green: {COLORS['pcb_green']};
        --copper: {COLORS['copper']};
        --phosphor-green: {COLORS['phosphor_green']};
        --scope-amber: {COLORS['scope_amber']};
        --signal-cyan: {COLORS['signal_cyan']};
        --fail-red: {COLORS['fail_red']};
        --text-color: {COLORS['text']};
        --muted-color: {COLORS['muted']};

        --font-main: 'Space Grotesk', -apple-system, BlinkMacSystemFont, sans-serif;
        --font-mono: 'JetBrains Mono', monospace;
        --font-readout: 'Share Tech Mono', monospace;
    }}

    /* Global Streamlit Reset & Hardware Aesthetic */
    html, body, [data-testid="stAppViewContainer"] {{
        background-color: var(--bg-color) !important;
        background-image: 
            radial-gradient(circle at 50% 10%, rgba(53, 208, 255, 0.03) 0%, transparent 60%),
            radial-gradient(circle at 90% 90%, rgba(200, 116, 43, 0.02) 0%, transparent 50%),
            url('{PCB_DATA_URI}') !important;
        background-repeat: repeat !important;
        color: var(--text-color) !important;
        font-family: var(--font-main) !important;
        font-size: 16px !important;
        line-height: 1.6 !important;
    }}

    /* Main Block Container (1200px max-width) */
    [data-testid="stMainBlockContainer"], .block-container {{
        max-width: 1200px !important;
        padding-top: 1.8rem !important;
        padding-bottom: 5rem !important;
        padding-left: 1.5rem !important;
        padding-right: 1.5rem !important;
        margin-left: auto !important;
        margin-right: auto !important;
    }}

    /* Hide default Streamlit chrome */
    #MainMenu, header, footer, div[data-testid="stDecoration"], div[data-testid="stStatusWidget"] {{
        visibility: hidden !important;
        height: 0px !important;
        display: none !important;
    }}

    /* Front Panel Sidebar */
    section[data-testid="stSidebar"] {{
        background-color: #0A0F14 !important;
        border-right: 1px solid var(--panel-border) !important;
        box-shadow: inset -1px 0 0 rgba(27, 42, 51, 0.8), 4px 0 24px rgba(0,0,0,0.6) !important;
    }}

    section[data-testid="stSidebar"] [data-testid="stVerticalBlock"] {{
        gap: 0.85rem !important;
    }}

    section[data-testid="stSidebar"] label,
    section[data-testid="stSidebar"] p,
    section[data-testid="stSidebar"] span,
    section[data-testid="stSidebar"] div {{
        font-size: 14px !important;
        color: var(--muted-color) !important;
    }}
    section[data-testid="stSidebar"] h1,
    section[data-testid="stSidebar"] h2,
    section[data-testid="stSidebar"] h3 {{
        color: var(--text-color) !important;
    }}

    /* Silkscreen Instrument Badges */
    .silkscreen-label {{
        font-family: var(--font-mono);
        font-size: 14px;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 1.5px;
        color: var(--muted-color);
        margin-bottom: 8px;
        display: flex;
        align-items: center;
        gap: 8px;
    }}
    .silkscreen-label::before {{
        content: "";
        display: inline-block;
        width: 8px;
        height: 8px;
        border-radius: 50%;
        background-color: var(--copper);
        box-shadow: 0 0 6px rgba(200, 116, 43, 0.6);
    }}

    /* Streamlit Border Containers styled as Instrument Panels */
    div[data-testid="stVerticalBlock"] > div[data-testid="stVerticalBlockBorderWrapper"],
    div[data-testid="stVerticalBlockBorderWrapper"] {{
        border: 1px solid var(--panel-border) !important;
        border-radius: 12px !important;
        background-color: var(--panel-color) !important;
        padding: 20px !important;
        margin-bottom: 24px !important;
        box-shadow: inset 0 0 20px rgba(7, 10, 13, 0.7), 0 4px 18px rgba(0,0,0,0.4) !important;
        position: relative !important;
    }}

    /* Hardware Panels fallback */
    .instrument-panel {{
        position: relative;
        background: var(--panel-color);
        border: 1px solid var(--panel-border);
        border-radius: 12px;
        padding: 20px;
        box-shadow: inset 0 0 20px rgba(7, 10, 13, 0.7), 0 4px 18px rgba(0,0,0,0.4);
        margin-bottom: 24px;
    }}

    /* LED Status Indicators */
    .led-indicator {{
        display: inline-flex;
        align-items: center;
        gap: 8px;
        font-family: var(--font-mono);
        font-size: 14px;
        font-weight: 600;
        letter-spacing: 0.5px;
        padding: 6px 12px;
        border-radius: 20px;
        border: 1px solid rgba(255,255,255,0.08);
        background: rgba(0,0,0,0.3);
    }}
    .led-dot {{
        width: 8px;
        height: 8px;
        border-radius: 50%;
        display: inline-block;
    }}
    .led-online, .led-pass {{
        background: var(--phosphor-green);
        box-shadow: 0 0 8px var(--phosphor-green);
    }}
    .led-offline, .led-neutral, .led-amber {{
        background: var(--scope-amber);
        box-shadow: 0 0 8px var(--scope-amber);
    }}
    .led-fail {{
        background: var(--fail-red);
        box-shadow: 0 0 8px var(--fail-red);
    }}
    .led-cyan {{
        background: var(--signal-cyan);
        box-shadow: 0 0 8px var(--signal-cyan);
        animation: pulseCyan 2s infinite ease-in-out;
    }}

    @keyframes pulseCyan {{
        0%, 100% {{ box-shadow: 0 0 4px var(--signal-cyan); opacity: 0.8; }}
        50% {{ box-shadow: 0 0 12px var(--signal-cyan); opacity: 1; }}
    }}

    /* Suggestion Chips as Rounded Component Pads (Requirement 4) */
    .stButton > button {{
        background: var(--panel-color) !important;
        color: var(--text-color) !important;
        border: 1px solid var(--panel-border) !important;
        border-radius: 8px !important;
        font-family: var(--font-mono) !important;
        font-size: 15px !important;
        font-weight: 500 !important;
        padding: 0.75rem 1rem !important;
        min-height: 48px !important;
        transition: all 0.2s cubic-bezier(0.2, 0.8, 0.2, 1) !important;
        box-shadow: 0 2px 6px rgba(0,0,0,0.5), inset 0 1px 0 rgba(255, 255, 255, 0.05) !important;
    }}
    .stButton > button:hover {{
        background: #14212A !important;
        border-color: var(--signal-cyan) !important;
        color: #FFFFFF !important;
        box-shadow: 0 0 16px rgba(53, 208, 255, 0.4), inset 0 0 6px rgba(53, 208, 255, 0.2) !important;
        transform: translateY(-2px) !important;
    }}
    .stButton > button:active {{
        transform: translateY(1.5px) !important;
        box-shadow: inset 0 2px 5px rgba(0,0,0,0.8) !important;
    }}
    .stButton > button p {{
        font-size: 15px !important;
        color: var(--text-color) !important;
        font-family: var(--font-mono) !important;
    }}
    .stButton > button:hover p {{
        color: #FFFFFF !important;
    }}

    /* Primary Accent Button */
    .stButton > button[kind="primary"] {{
        background: linear-gradient(180deg, #184A3B 0%, #0B3D2E 100%) !important;
        border: 1px solid var(--phosphor-green) !important;
        color: #FFFFFF !important;
        box-shadow: 0 0 14px rgba(57, 255, 136, 0.25) !important;
    }}
    .stButton > button[kind="primary"]:hover {{
        background: linear-gradient(180deg, #205E4C 0%, #0E4F3B 100%) !important;
        box-shadow: 0 0 22px rgba(57, 255, 136, 0.45) !important;
    }}

    /* Bottom Chat Bar Styling (Requirement 3) */
    div[data-testid="stBottom"],
    div[data-testid="stBottomBlockContainer"],
    footer[data-testid="stBottom"] {{
        background-color: var(--bg-color) !important;
        background-image: none !important;
        border-top: 1px solid var(--panel-border) !important;
    }}
    div[data-testid="stBottomBlockContainer"] {{
        max-width: 1200px !important;
        margin-left: auto !important;
        margin-right: auto !important;
        padding-top: 0.5rem !important;
        padding-bottom: 0.85rem !important;
        background-color: var(--bg-color) !important;
    }}

    /* Chat Input Styling with Prompt Glyph and Focus Glow */
    div[data-testid="stChatInput"] {{
        background-color: transparent !important;
    }}
    div[data-testid="stChatInput"] > div {{
        background-color: var(--panel-color) !important;
        border: 1px solid var(--panel-border) !important;
        border-radius: 8px !important;
        transition: all 0.2s ease !important;
    }}
    div[data-testid="stChatInput"] textarea {{
        background-color: var(--panel-color) !important;
        color: var(--text-color) !important;
        font-family: var(--font-mono) !important;
        font-size: 15px !important;
        padding-left: 2rem !important;
    }}
    div[data-testid="stChatInput"] textarea::placeholder {{
        color: var(--muted-color) !important;
    }}
    div[data-testid="stChatInput"]:focus-within > div,
    div[data-testid="stChatInput"] textarea:focus {{
        border-color: var(--signal-cyan) !important;
        box-shadow: 0 0 14px rgba(53, 208, 255, 0.4), inset 0 1px 3px rgba(0, 0, 0, 0.6) !important;
    }}
    div[data-testid="stChatInput"]::before {{
        content: ">";
        position: absolute;
        left: 14px;
        top: 14px;
        font-family: var(--font-readout);
        font-size: 18px;
        font-weight: bold;
        color: var(--signal-cyan);
        z-index: 10;
        pointer-events: none;
    }}

    /* Chat Messages: User vs Assistant */
    @keyframes fadeRise {{
        0% {{ opacity: 0; transform: translateY(8px); }}
        100% {{ opacity: 1; transform: translateY(0); }}
    }}
    div[data-testid="stChatMessage"] {{
        animation: fadeRise 250ms ease-out forwards;
        border-radius: 10px !important;
        padding: 1rem 1.25rem !important;
        margin-bottom: 0.8rem !important;
        border: 1px solid var(--panel-border) !important;
    }}
    div[data-testid="stChatMessage"]:has(div[data-testid="stChatMessageAvatarAssistant"]) {{
        background: #0B1218 !important;
        border-left: 3px solid var(--signal-cyan) !important;
        box-shadow: inset 0 0 16px rgba(53, 208, 255, 0.04) !important;
    }}
    div[data-testid="stChatMessage"]:has(div[data-testid="stChatMessageAvatarUser"]) {{
        background: #11171D !important;
        border-right: 3px solid var(--copper) !important;
        border-left: 1px solid var(--panel-border) !important;
    }}

    /* Expanders Styled as Instrument Chassis Compartments (Requirement 2) */
    div[data-testid="stExpander"] {{
        background-color: var(--panel-color) !important;
        border: 1px solid var(--panel-border) !important;
        border-radius: 12px !important;
        overflow: hidden !important;
        margin-bottom: 16px !important;
    }}
    div[data-testid="stExpander"] details {{
        background-color: var(--panel-color) !important;
        border: none !important;
    }}
    div[data-testid="stExpander"] details summary {{
        background-color: var(--panel-color) !important;
        color: var(--text-color) !important;
        font-family: var(--font-main) !important;
        font-size: 16px !important;
        font-weight: 500 !important;
        padding: 0.85rem 1.25rem !important;
        border: none !important;
        border-bottom: 1px solid transparent !important;
    }}
    div[data-testid="stExpander"] details[open] > summary {{
        background-color: var(--panel-color) !important;
        color: var(--text-color) !important;
        border-bottom: 1px solid var(--panel-border) !important;
    }}
    div[data-testid="stExpander"] details summary:hover,
    div[data-testid="stExpander"] details summary:focus,
    div[data-testid="stExpander"] details summary:active {{
        background-color: #121A22 !important;
        color: var(--signal-cyan) !important;
    }}
    div[data-testid="stExpander"] details summary p,
    div[data-testid="stExpander"] details summary span,
    div[data-testid="stExpander"] details summary div {{
        color: var(--text-color) !important;
        font-size: 16px !important;
    }}
    div[data-testid="stExpander"] details summary:hover p,
    div[data-testid="stExpander"] details summary:hover span {{
        color: var(--signal-cyan) !important;
    }}
    div[data-testid="stExpander"] details summary svg {{
        fill: var(--signal-cyan) !important;
        stroke: var(--signal-cyan) !important;
        color: var(--signal-cyan) !important;
    }}
    div[data-testid="stExpanderDetails"],
    div[data-testid="stExpander"] details > div:last-child {{
        background-color: #0A0E13 !important;
        padding: 1.25rem !important;
        color: var(--text-color) !important;
    }}

    /* Verdict Status Lamp Banners (Requirement 8) */
    .verdict-lamp {{
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 1rem 1.5rem;
        border-radius: 10px;
        margin: 0.5rem 0 1rem 0;
        border: 1px solid;
    }}
    @keyframes pulseVerdictFail {{
        0%, 100% {{
            box-shadow: 0 0 16px rgba(255, 77, 94, 0.25), inset 0 0 8px rgba(255, 77, 94, 0.1);
            border-color: rgba(255, 77, 94, 0.7);
        }}
        50% {{
            box-shadow: 0 0 28px rgba(255, 77, 94, 0.6), inset 0 0 16px rgba(255, 77, 94, 0.25);
            border-color: rgba(255, 77, 94, 1.0);
        }}
    }}
    .verdict-lamp-pass {{
        background: linear-gradient(90deg, rgba(57, 255, 136, 0.12) 0%, rgba(11, 61, 46, 0.4) 100%);
        border-color: var(--phosphor-green);
        box-shadow: 0 0 20px rgba(57, 255, 136, 0.2), inset 0 0 10px rgba(57, 255, 136, 0.1);
    }}
    .verdict-lamp-fail {{
        background: linear-gradient(90deg, rgba(255, 77, 94, 0.14) 0%, rgba(50, 10, 15, 0.45) 100%);
        border-color: var(--fail-red);
        animation: pulseVerdictFail 2s infinite ease-in-out;
    }}
    .verdict-lamp-amber {{
        background: linear-gradient(90deg, rgba(255, 176, 0, 0.12) 0%, rgba(60, 40, 10, 0.4) 100%);
        border-color: var(--scope-amber);
        box-shadow: 0 0 20px rgba(255, 176, 0, 0.2), inset 0 0 10px rgba(255, 176, 0, 0.1);
    }}

    /* Seven-Segment Readout Cards (Requirement 7) */
    .readout-card {{
        background: #090E13;
        border: 1px solid var(--panel-border);
        border-radius: 10px;
        padding: 1.1rem 1.25rem;
        box-shadow: inset 0 2px 6px rgba(0, 0, 0, 0.8), 0 0 10px rgba(0, 0, 0, 0.3);
        display: flex;
        flex-direction: column;
        justify-content: space-between;
        min-height: 125px;
    }}
    .readout-card-header {{
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 6px;
    }}
    .readout-card-label {{
        font-family: var(--font-mono);
        font-size: 14px;
        text-transform: uppercase;
        letter-spacing: 1px;
        color: var(--muted-color);
    }}
    .readout-card-value {{
        font-family: var(--font-readout);
        font-size: 32px;
        font-weight: bold;
        letter-spacing: 1px;
        margin: 4px 0;
    }}
    .readout-card-delta {{
        font-family: var(--font-mono);
        font-size: 14px;
        color: var(--muted-color);
    }}
    .readout-pass .readout-card-value {{
        color: var(--phosphor-green);
        text-shadow: 0 0 12px rgba(57, 255, 136, 0.35);
    }}
    .readout-fail .readout-card-value {{
        color: var(--fail-red);
        text-shadow: 0 0 12px rgba(255, 77, 94, 0.35);
    }}
    .readout-neutral .readout-card-value {{
        color: var(--scope-amber);
        text-shadow: 0 0 12px rgba(255, 176, 0, 0.35);
    }}

    /* Custom Themed HTML Tables (Requirement 6) */
    .custom-table-container {{
        width: 100%;
        overflow-x: auto;
        border: 1px solid var(--panel-border);
        border-radius: 8px;
        background: #0A0F14;
        margin: 12px 0 18px 0;
    }}
    .instrument-table {{
        width: 100%;
        border-collapse: collapse;
        font-family: var(--font-mono);
        font-size: 14px;
        color: var(--text-color);
    }}
    .instrument-table th {{
        background: #0E161D;
        color: var(--muted-color);
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 1px;
        padding: 12px 16px;
        border-bottom: 1px solid var(--panel-border);
        text-align: left;
    }}
    .instrument-table td {{
        padding: 11px 16px;
        border-bottom: 1px solid rgba(27, 42, 51, 0.6);
        background: #090E13;
    }}
    .instrument-table tr:nth-child(even) td {{
        background: #0C1218;
    }}
    .instrument-table tr:hover td {{
        background: #111B22;
    }}
    .status-pill {{
        display: inline-block;
        padding: 3px 10px;
        border-radius: 4px;
        font-family: var(--font-mono);
        font-size: 13px;
        font-weight: bold;
        letter-spacing: 0.5px;
    }}
    .status-pill.status-pass {{
        background: rgba(57, 255, 136, 0.15);
        color: var(--phosphor-green);
        border: 1px solid var(--phosphor-green);
        box-shadow: 0 0 8px rgba(57, 255, 136, 0.2);
    }}
    .status-pill.status-fail {{
        background: rgba(255, 77, 94, 0.15);
        color: var(--fail-red);
        border: 1px solid var(--fail-red);
        box-shadow: 0 0 8px rgba(255, 77, 94, 0.2);
    }}

    /* Pipeline Route Strip Styles */
    .route-container {{
        background: #090E13;
        border: 1px solid var(--panel-border);
        border-radius: 10px;
        padding: 12px 20px;
        box-shadow: inset 0 0 16px rgba(0,0,0,0.8);
        position: relative;
        width: 100%;
        margin-bottom: 8px;
    }}
    .stations-bar {{
        display: flex;
        align-items: center;
        justify-content: space-between;
        position: relative;
        margin-bottom: 8px;
    }}
    .trace-line {{
        position: absolute;
        top: 20px;
        left: 5%;
        right: 5%;
        height: 3px;
        background: #1F303B;
        z-index: 1;
    }}
    .trace-active-fill {{
        position: absolute;
        top: 20px;
        left: 5%;
        height: 3px;
        background: linear-gradient(90deg, #39FF88 0%, #C8742B 100%);
        z-index: 2;
        transition: width 0.4s ease;
    }}
    .station {{
        position: relative;
        z-index: 3;
        display: flex;
        flex-direction: column;
        align-items: center;
        gap: 6px;
    }}
    .station-chip {{
        width: 42px;
        height: 42px;
        border-radius: 8px;
        background: #0D161C;
        border: 2px solid var(--panel-border);
        display: flex;
        align-items: center;
        justify-content: center;
        box-shadow: 0 2px 6px rgba(0,0,0,0.6);
        transition: all 0.3s ease;
    }}
    .station-chip.active {{
        border-color: var(--phosphor-green);
        box-shadow: 0 0 14px rgba(57, 255, 136, 0.4), inset 0 0 8px rgba(57, 255, 136, 0.2);
    }}
    .station-chip.done {{
        border-color: var(--phosphor-green);
        background: rgba(11, 61, 46, 0.4);
    }}
    .station-icon {{
        font-size: 18px;
    }}
    .station-name {{
        font-family: var(--font-mono);
        font-size: 11px;
        font-weight: 700;
        letter-spacing: 1px;
        color: var(--muted-color);
        text-transform: uppercase;
    }}
    .station-name.active {{
        color: var(--phosphor-green);
        text-shadow: 0 0 8px rgba(57, 255, 136, 0.5);
    }}
    .station-led {{
        width: 6px;
        height: 6px;
        border-radius: 50%;
        background: var(--panel-border);
    }}
    .station-led.active {{
        background: var(--phosphor-green);
        box-shadow: 0 0 8px var(--phosphor-green);
    }}
    .station-led.done {{
        background: var(--phosphor-green);
    }}
    .caption-strip {{
        font-family: var(--font-mono);
        font-size: 14px;
        color: var(--text-color);
        text-align: center;
        margin-top: 6px;
        padding-top: 6px;
        border-top: 1px dashed rgba(27, 42, 51, 0.6);
        min-height: 22px;
    }}

    .stCaption, [data-testid="stCaptionContainer"] {{
        color: var(--muted-color) !important;
        font-size: 14px !important;
    }}

    /* Code & SPICE blocks */
    pre, code {{
        font-family: var(--font-mono) !important;
        background: #05080B !important;
        border: 1px solid #16242D !important;
        color: #A5C0D0 !important;
    }}

    /* Respect reduced motion preferences */
    @media (prefers-reduced-motion: reduce) {{
        *, ::before, ::after {{
            animation-duration: 0.01ms !important;
            animation-iteration-count: 1 !important;
            transition-duration: 0.01ms !important;
            scroll-behavior: auto !important;
        }}
    }}
    </style>
    """
    return textwrap.dedent(css).strip()


def inject_theme():
    """Inject instrument CSS styles into Streamlit once."""
    theme_code = get_theme_css()
    st.markdown(theme_code, unsafe_allow_html=True)


def render_logo():
    """Render the inline instrument front-panel SVG logo."""
    st.markdown(
        f'<div style="text-align: center; margin-bottom: 0.5rem;">{LOGO_SVG}</div>',
        unsafe_allow_html=True
    )


def get_app_logo_svg() -> str:
    """Return raw logo SVG string."""
    return LOGO_SVG.strip()


def render_status_chip(label: str, is_online: bool) -> str:
    """Return HTML markup for an online/offline LED status chip."""
    led_cls = "led-online" if is_online else "led-offline"
    return f'<div class="led-indicator"><span class="led-dot {led_cls}"></span> {label}</div>'


def render_verdict_lamp(
    status: str = "unverified",
    message: str = "",
    passed: bool = None,
    checked_by_spice: bool = None,
    **kwargs
):
    """
    Render the high-contrast verdict status lamp banner.
    status: 'verified', 'failed', or 'unverified' (also accepts boolean passed=True/False).
    message: optional descriptive string.
    checked_by_spice: displayed on 'verified' and 'failed' only by default.
    """
    if passed is not None:
        stat_key = "verified" if passed else "failed"
    elif isinstance(status, bool):
        stat_key = "verified" if status else "failed"
    else:
        stat_str = str(status or "").strip().lower()
        if stat_str in ("verified", "pass", "passed", "true", "1"):
            stat_key = "verified"
        elif stat_str in ("failed", "fail", "false", "0"):
            stat_key = "failed"
        elif stat_str in ("unverified_guess", "guess") or "unverified ai guess" in str(message or "").lower():
            stat_key = "unverified_guess"
        else:
            stat_key = "unverified"

    if stat_key == "verified":
        cls_name = "verdict-lamp-pass"
        status_icon = "🟢"
        status_title = "VERIFIED BY SIMULATION"
        title_color = COLORS["phosphor_green"]
        default_chip = True
    elif stat_key == "failed":
        cls_name = "verdict-lamp-fail"
        status_icon = "🔴"
        status_title = "SPEC NOT MET"
        title_color = COLORS["fail_red"]
        default_chip = True
    elif stat_key == "unverified_guess":
        cls_name = "verdict-lamp-amber"
        status_icon = "🟡"
        status_title = "UNVERIFIED AI GUESS"
        title_color = COLORS["scope_amber"]
        default_chip = True
    else:
        cls_name = "verdict-lamp-amber"
        status_icon = "🟡"
        status_title = "DESIGN NOT YET VERIFIED"
        title_color = COLORS["scope_amber"]
        default_chip = False

    show_chip = default_chip if checked_by_spice is None else bool(checked_by_spice)

    spice_chip = (
        '<span style="font-family: var(--font-mono); font-size: 13px; background: rgba(0,0,0,0.5); '
        'padding: 5px 10px; border-radius: 4px; border: 1px solid rgba(255,255,255,0.15); color: #D7E3EA;">'
        '✓ Checked by ngspice</span>'
    ) if show_chip else ""

    message_html = f'<div style="font-family: var(--font-main); font-size: 15px; color: #D7E3EA; margin-top: 4px;">{message}</div>' if message else ""

    html = f"""
    <div class="verdict-lamp {cls_name}">
        <div>
            <div style="font-family: var(--font-readout); font-size: 24px; font-weight: bold; letter-spacing: 1px; color: {title_color}; display: flex; align-items: center; gap: 8px;">
                <span>{status_icon}</span>
                <span>{status_title}</span>
            </div>
            {message_html}
        </div>
        <div>
            {spice_chip}
        </div>
    </div>
    """
    st.markdown(textwrap.dedent(html).strip(), unsafe_allow_html=True)


def render_seven_segment_card(
    title: str = "",
    value: str = "",
    delta: str = "",
    status: str = "neutral",
    unit: str = "",
    passed: bool = None,
    **kwargs
) -> str:
    """
    Render a 7-segment / Share Tech Mono instrument readout card.
    status can be 'neutral' (amber), 'pass' (phosphor green), or 'fail' (red).
    """
    if passed is not None:
        status_key = "pass" if passed else "fail"
    else:
        status_key = str(status).lower()

    if status_key == "pass":
        card_cls = "readout-pass"
        led_cls = "led-pass"
    elif status_key == "fail":
        card_cls = "readout-fail"
        led_cls = "led-fail"
    else:
        card_cls = "readout-neutral"
        led_cls = "led-neutral"

    unit_display = f'<span style="font-size: 18px; margin-left: 4px; color: var(--muted-color);">{unit}</span>' if unit else ""
    delta_display = f'<div class="readout-card-delta">{delta}</div>' if delta else ""

    html = f"""
    <div class="readout-card {card_cls}">
        <div class="readout-card-header">
            <span class="readout-card-label">{title}</span>
            <span class="led-dot {led_cls}"></span>
        </div>
        <div class="readout-card-value">
            {value}{unit_display}
        </div>
        {delta_display}
    </div>
    """
    return textwrap.dedent(html).strip()


def render_html_table(headers: list = None, rows: list = None, **kwargs) -> str:
    """Render a themed HTML table with mono numbers and PASS/FAIL badges."""
    headers = headers or []
    rows = rows or []
    th_cells = "".join(f"<th>{h}</th>" for h in headers)
    tr_rows = []
    for r in rows:
        tds = []
        for val in r:
            val_str = str(val)
            if "PASS" in val_str:
                tds.append('<td style="text-align: center;"><span class="status-pill status-pass">PASS</span></td>')
            elif "FAIL" in val_str:
                tds.append('<td style="text-align: center;"><span class="status-pill status-fail">FAIL</span></td>')
            else:
                tds.append(f"<td>{val_str}</td>")
        tr_rows.append(f"<tr>{''.join(tds)}</tr>")

    html = f"""
    <div class="custom-table-container">
        <table class="instrument-table">
            <thead><tr>{th_cells}</tr></thead>
            <tbody>{''.join(tr_rows)}</tbody>
        </table>
    </div>
    """
    return textwrap.dedent(html).strip()
