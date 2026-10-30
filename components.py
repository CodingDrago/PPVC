"""
components.py - Signature Instrument-Grade UI Components
Oscilloscope Bode View, Live Blueprint Schematic, PCB Pipeline Strip,
Signal Cleanup CRT, and System Boot Sequence.
Pure HTML5/Canvas/SVG/JS with zero external dependencies.
"""

import io
import json
import textwrap
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import schemdraw
import schemdraw.elements as elm
import streamlit as st
import streamlit.components.v1 as components

import spice
if not hasattr(spice, "format_value"):
    def _format_value(val: float, comp_type_or_name: str = "") -> str:
        t = "C" if (str(comp_type_or_name).startswith("C") or comp_type_or_name == "C") else ""
        return spice.format_eng(val, t)
    spice.format_value = _format_value



def render_oscilloscope_bode(
    freqs_broken: list = None,
    gain_broken: list = None,
    freqs_fixed: list = None,
    gain_fixed: list = None,
    target_freq: float = 1000.0,
    circuit_id: str = "sallen_key",
    readouts: dict = None,
    height: int = 440,
    **kwargs
):
    """
    Component A: Oscilloscope Bode View (Hero Element)
    CRT Canvas with 10x8 graticule, double-stroke phosphor glow,
    beam sweep animation, cursors, hover crosshairs, and digital readouts.
    Y-range from -80 dB to +20 dB without clamping data to the axis floor.
    """
    readouts = readouts or {}
    target_freq = float(target_freq) if target_freq is not None else 1000.0
    payload = {
        "freqs_broken": [float(f) for f in freqs_broken] if freqs_broken is not None else [],
        "gain_broken": [float(g) for g in gain_broken] if gain_broken is not None else [],
        "freqs_fixed": [float(f) for f in freqs_fixed] if freqs_fixed is not None else [],
        "gain_fixed": [float(g) for g in gain_fixed] if gain_fixed is not None else [],
        "target_freq": target_freq,
        "circuit_id": circuit_id or "sallen_key",
        "readouts": readouts
    }
    json_data = json.dumps(payload)

    html_code = f"""
    <!DOCTYPE html>
    <html>
    <head>
    <meta charset="utf-8">
    <style>
        @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600&family=Share+Tech+Mono&display=swap');
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            background: transparent;
            font-family: 'JetBrains Mono', monospace;
            color: #D7E3EA;
            overflow: hidden;
            width: 100%;
            display: block;
        }}
        .scope-bezel {{
            background: #0E1419;
            border: 2px solid #1B2A33;
            border-radius: 12px;
            padding: 14px;
            box-shadow: inset 0 2px 6px rgba(255,255,255,0.05), 0 8px 24px rgba(0,0,0,0.8);
            width: 100%;
            position: relative;
        }}
        .scope-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 8px;
            padding: 0 4px;
        }}
        .scope-title {{
            font-size: 13px;
            letter-spacing: 1.5px;
            text-transform: uppercase;
            color: #9FB3BE;
            display: flex;
            align-items: center;
            gap: 8px;
        }}
        .scope-title span.active-led {{
            width: 8px;
            height: 8px;
            border-radius: 50%;
            background: #39FF88;
            box-shadow: 0 0 8px #39FF88;
            display: inline-block;
        }}
        .scope-hud {{
            font-family: 'Share Tech Mono', monospace;
            font-size: 14px;
            color: #35D0FF;
            background: rgba(0,0,0,0.6);
            padding: 3px 10px;
            border-radius: 4px;
            border: 1px solid #1B2A33;
        }}
        .crt-container {{
            position: relative;
            background: #04070A;
            border-radius: 8px;
            border: 1px solid #14232C;
            overflow: hidden;
            box-shadow: inset 0 0 30px rgba(0,0,0,0.95);
        }}
        canvas {{
            display: block;
            width: 100%;
            height: 310px;
        }}
        .scanlines {{
            position: absolute;
            top: 0; left: 0; width: 100%; height: 100%;
            background: linear-gradient(rgba(18, 16, 16, 0) 50%, rgba(0, 0, 0, 0.25) 50%),
                        radial-gradient(circle, transparent 65%, rgba(0,0,0,0.6) 100%);
            background-size: 100% 3px, 100% 100%;
            pointer-events: none;
        }}
        .readout-strip {{
            display: flex;
            justify-content: space-between;
            gap: 12px;
            margin-top: 10px;
            padding-top: 8px;
            border-top: 1px solid #1B2A33;
        }}
        .readout-item {{
            background: #070B0E;
            border: 1px solid #182832;
            border-radius: 6px;
            padding: 8px 14px;
            flex: 1;
            display: flex;
            flex-direction: column;
            gap: 2px;
        }}
        .readout-label {{
            font-size: 12px;
            color: #9FB3BE;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }}
        .readout-val {{
            font-family: 'Share Tech Mono', monospace;
            font-size: 18px;
            color: #39FF88;
        }}
        .readout-val.amber {{
            color: #FFB000;
        }}
    </style>
    </head>
    <body>
    <div class="scope-bezel">
        <div class="scope-header">
            <div class="scope-title">
                <span class="active-led"></span>
                <span>CH1 BODE RESPONSE • 10 Hz — 1 MHz • 50 Ω INPUT</span>
            </div>
            <div class="scope-hud" id="cursorHud">TARGET fc: {int(target_freq)} Hz</div>
        </div>
        <div class="crt-container">
            <canvas id="bodeCanvas"></canvas>
            <div class="scanlines"></div>
        </div>
        <div class="readout-strip">
            <div class="readout-item">
                <span class="readout-label">Target Frequency</span>
                <span class="readout-val">{target_freq:.0f} Hz</span>
            </div>
            <div class="readout-item">
                <span class="readout-label">Initial State (Before)</span>
                <span class="readout-val amber" id="initReadout">—</span>
            </div>
            <div class="readout-item">
                <span class="readout-label">Verified State (After Fix)</span>
                <span class="readout-val" id="finalReadout">—</span>
            </div>
        </div>
    </div>

    <script>
    (function() {{
        try {{
            const data = {json_data};
            const canvas = document.getElementById('bodeCanvas');
            const ctx = canvas.getContext('2d');
            const cursorHud = document.getElementById('cursorHud');
            const initReadout = document.getElementById('initReadout');
            const finalReadout = document.getElementById('finalReadout');

            if (data.readouts) {{
                if (data.readouts.initial) initReadout.textContent = data.readouts.initial;
                if (data.readouts.final) finalReadout.textContent = data.readouts.final;
            }}

            const dpr = window.devicePixelRatio || 1;
            const rect = canvas.getBoundingClientRect();
            canvas.width = rect.width * dpr;
            canvas.height = rect.height * dpr;
            ctx.scale(dpr, dpr);

            const W = rect.width;
            const H = rect.height;
            const padL = 55, padR = 25, padT = 20, padB = 30;
            const plotW = W - padL - padR;
            const plotH = H - padT - padB;

            const minF = 10, maxF = 1000000;
            const logMin = Math.log10(minF);
            const logMax = Math.log10(maxF);

            // Instrument-grade Y range: -80 dB to +20 dB
            const minG = -80.0, maxG = 20.0;

            function fToX(f) {{
                const lf = Math.log10(Math.max(minF, f));
                return padL + ((lf - logMin) / (logMax - logMin)) * plotW;
            }}

            function xToF(x) {{
                const ratio = (x - padL) / plotW;
                return Math.pow(10, logMin + ratio * (logMax - logMin));
            }}

            // Unclamped gain-to-Y so steep roll-off curves are fully visible without floor clamping
            function gToY(g) {{
                return padT + (1 - (g - minG) / (maxG - minG)) * plotH;
            }}

            function yToG(y) {{
                const ratio = 1 - ((y - padT) / plotH);
                return minG + ratio * (maxG - minG);
            }}

            let startTime = performance.now();
            const sweepDuration = 1200; // ms

            function drawGraticule() {{
                ctx.save();
                ctx.strokeStyle = '#12222B';
                ctx.lineWidth = 1;

                // Vertical decade lines
                const decades = [10, 100, 1000, 10000, 100000, 1000000];
                const decLabels = ['10Hz', '100Hz', '1kHz', '10kHz', '100kHz', '1MHz'];
                decades.forEach((f, idx) => {{
                    const x = fToX(f);
                    ctx.beginPath();
                    ctx.moveTo(x, padT);
                    ctx.lineTo(x, padT + plotH);
                    ctx.stroke();

                    // Minor sub-decade ticks
                    if (idx < decades.length - 1) {{
                        for (let sub = 2; sub <= 9; sub++) {{
                            const subX = fToX(f * sub);
                            ctx.strokeStyle = 'rgba(18, 34, 43, 0.4)';
                            ctx.beginPath();
                            ctx.moveTo(subX, padT);
                            ctx.lineTo(subX, padT + plotH);
                            ctx.stroke();
                            ctx.strokeStyle = '#12222B';
                        }}
                    }}
                }});

                // Horizontal dB divisions: +20, 0, -20, -40, -60, -80 dB (5 divisions of 20 dB)
                for (let j = 0; j <= 5; j++) {{
                    const g = minG + (j / 5) * (maxG - minG);
                    const y = gToY(g);
                    ctx.beginPath();
                    ctx.moveTo(padL, y);
                    ctx.lineTo(padL + plotW, y);
                    ctx.stroke();
                }}

                // Axis Labels
                ctx.fillStyle = '#9FB3BE';
                ctx.font = '11px JetBrains Mono';
                ctx.textAlign = 'center';

                decades.forEach((f, idx) => {{
                    const x = fToX(f);
                    ctx.fillText(decLabels[idx], x, H - 10);
                }});

                ctx.textAlign = 'right';
                for (let j = 0; j <= 5; j++) {{
                    const g = minG + (j / 5) * (maxG - minG);
                    const y = gToY(g);
                    ctx.fillText(Math.round(g) + 'dB', padL - 8, y + 4);
                }}

                // 0dB baseline indicator
                const y0dB = gToY(0);
                if (y0dB >= padT && y0dB <= padT + plotH) {{
                    ctx.strokeStyle = 'rgba(57, 255, 136, 0.2)';
                    ctx.setLineDash([2, 4]);
                    ctx.beginPath();
                    ctx.moveTo(padL, y0dB);
                    ctx.lineTo(padL + plotW, y0dB);
                    ctx.stroke();
                    ctx.setLineDash([]);
                }}

                // -3dB Cutoff line
                const y3dB = gToY(-3);
                if (y3dB >= padT && y3dB <= padT + plotH) {{
                    ctx.strokeStyle = 'rgba(53, 208, 255, 0.3)';
                    ctx.setLineDash([4, 4]);
                    ctx.beginPath();
                    ctx.moveTo(padL, y3dB);
                    ctx.lineTo(padL + plotW, y3dB);
                    ctx.stroke();
                    ctx.setLineDash([]);
                }}

                // Target fc Cursor
                const targetX = fToX(data.target_freq);
                if (targetX >= padL && targetX <= padL + plotW) {{
                    ctx.strokeStyle = '#35D0FF';
                    ctx.setLineDash([5, 5]);
                    ctx.beginPath();
                    ctx.moveTo(targetX, padT);
                    ctx.lineTo(targetX, padT + plotH);
                    ctx.stroke();
                    ctx.setLineDash([]);

                    ctx.fillStyle = '#35D0FF';
                    ctx.textAlign = 'left';
                    ctx.fillText('TARGET fc', targetX + 5, padT + 14);
                }}

                ctx.restore();
            }}

            function drawTrace(freqs, gains, color, progress, alpha) {{
                if (!freqs || freqs.length < 2) return;
                const totalPoints = freqs.length;
                const pointsToDraw = Math.min(totalPoints, Math.floor(totalPoints * progress));
                if (pointsToDraw < 2) return;

                ctx.save();
                // Clip rendering to CRT plot box so curves roll off cleanly below -80 dB without leaking into margins
                ctx.beginPath();
                ctx.rect(padL, padT, plotW, plotH);
                ctx.clip();

                ctx.beginPath();
                for (let i = 0; i < pointsToDraw; i++) {{
                    const x = fToX(freqs[i]);
                    const y = gToY(gains[i]);
                    if (i === 0) ctx.moveTo(x, y);
                    else ctx.lineTo(x, y);
                }}

                // Pass 1: Phosphor glow blur
                ctx.strokeStyle = color;
                ctx.lineWidth = 5;
                ctx.globalAlpha = alpha * 0.28;
                ctx.shadowBlur = 10;
                ctx.shadowColor = color;
                ctx.stroke();

                // Pass 2: Crisp core line
                ctx.lineWidth = 2.0;
                ctx.globalAlpha = alpha;
                ctx.shadowBlur = 0;
                ctx.stroke();
                ctx.restore();
            }}

            let mouseX = -1, mouseY = -1;
            canvas.addEventListener('mousemove', (e) => {{
                const r = canvas.getBoundingClientRect();
                mouseX = e.clientX - r.left;
                mouseY = e.clientY - r.top;
                if (mouseX >= padL && mouseX <= padL + plotW) {{
                    const curF = xToF(mouseX);
                    const curG = yToG(mouseY);
                    const fStr = curF >= 1000 ? (curF / 1000).toFixed(2) + ' kHz' : Math.round(curF) + ' Hz';
                    cursorHud.textContent = `CURSOR: ${{fStr}} | ${{curG.toFixed(1)}} dB`;
                }}
            }});

            canvas.addEventListener('mouseleave', () => {{
                mouseX = -1;
                mouseY = -1;
                cursorHud.textContent = `TARGET fc: ${{Math.round(data.target_freq)}} Hz`;
            }});

            function render(now) {{
                const elapsed = now - startTime;
                const progressBroken = Math.min(1.0, elapsed / sweepDuration);
                const hasFixed = data.freqs_fixed && data.freqs_fixed.length > 0;
                let progressFixed = 0;
                if (hasFixed) {{
                    const delay = 400;
                    progressFixed = Math.max(0, Math.min(1.0, (elapsed - delay) / sweepDuration));
                }}

                ctx.clearRect(0, 0, W, H);
                drawGraticule();

                // Broken curve (Amber/Red)
                const brokenAlpha = hasFixed && progressFixed > 0.6 ? 0.35 : 0.95;
                drawTrace(data.freqs_broken, data.gain_broken, '#FFB000', progressBroken, brokenAlpha);

                // Fixed curve (Phosphor Green)
                if (hasFixed && progressFixed > 0) {{
                    drawTrace(data.freqs_fixed, data.gain_fixed, '#39FF88', progressFixed, 1.0);
                }}

                // Interactive Crosshairs
                if (mouseX >= padL && mouseX <= padL + plotW && mouseY >= padT && mouseY <= padT + plotH) {{
                    ctx.save();
                    ctx.strokeStyle = 'rgba(53, 208, 255, 0.5)';
                    ctx.setLineDash([2, 2]);
                    ctx.lineWidth = 1;
                    ctx.beginPath();
                    ctx.moveTo(padL, mouseY);
                    ctx.lineTo(padL + plotW, mouseY);
                    ctx.stroke();

                    ctx.beginPath();
                    ctx.moveTo(mouseX, padT);
                    ctx.lineTo(mouseX, padT + plotH);
                    ctx.stroke();
                    ctx.restore();
                }}

                if (progressBroken < 1.0 || (hasFixed && progressFixed < 1.0) || mouseX !== -1) {{
                    requestAnimationFrame(render);
                }}
            }}

            requestAnimationFrame(render);
        }} catch (err) {{
            console.error("CRT Scope error:", err);
        }}
    }})();
    </script>
    </body>
    </html>
    """
    components.html(html_code, height=height, scrolling=False)


@st.cache_data
def get_schematic_png(
    circuit_id: str,
    components_tuple: tuple,
    label: str = "",
    changed_names_tuple: tuple = (),
    old_components_tuple: tuple = ()
) -> bytes:
    """
    Generate and cache PNG bytes for the circuit schematic.
    Uses identical fixed figsize, xlim, and ylim for BEFORE and AFTER states.
    No axis frame or tick numbers.
    """
    comps = dict(components_tuple) if components_tuple else {}
    old_comps = dict(old_components_tuple) if old_components_tuple else {}
    changed_names = set(changed_names_tuple) if changed_names_tuple else set()
    is_after = "AFTER" in (label or "").upper()

    scope_amber = "#FFB000"
    dim_amber = "#B8742B"
    default_color = "#D7E3EA"

    def get_comp_style(name: str, default_val: float):
        val = comps.get(name, default_val)
        val_str = spice.format_value(val, name)
        is_changed = name in changed_names

        if is_after:
            if is_changed:
                old_val = old_comps.get(name, val)
                old_str = spice.format_value(old_val, name)
                lbl = f"{name}\n{val_str}\nwas {old_str}"
                return scope_amber, lbl
            else:
                return default_color, f"{name}\n{val_str}"
        else:
            if is_changed:
                return dim_amber, f"{name}\n{val_str}"
            else:
                return default_color, f"{name}\n{val_str}"

    fig = plt.figure(figsize=(6.0, 3.8), facecolor="#0E1419")
    ax = fig.gca()
    ax.set_facecolor("#0E1419")

    d = schemdraw.Drawing(canvas=ax)
    d.config(fontsize=9, unit=2.2, color="#D7E3EA", lw=1.8, font="monospace")

    if circuit_id == "sallen_key":
        c_r1, lbl_r1 = get_comp_style("R1", 7.5e3)
        c_r2, lbl_r2 = get_comp_style("R2", 7.5e3)
        c_c1, lbl_c1 = get_comp_style("C1", 68e-9)
        c_c2, lbl_c2 = get_comp_style("C2", 6.8e-9)

        # Input
        d += elm.Dot().label("Vin", loc="left", color="#35D0FF")
        d += elm.Resistor().right().label(lbl_r1, loc="top", color=c_r1).color(c_r1)
        d += (n1 := elm.Dot())

        # R2
        d += elm.Resistor().right().label(lbl_r2, loc="top", color=c_r2).color(c_r2)
        d += (n_plus := elm.Dot())

        # C2 branch down to ground (schemdraw places label left of plates without loc)
        d.push()
        d += elm.Capacitor().down().label(lbl_c2, color=c_c2).color(c_c2)
        d += elm.Ground().color(default_color)
        d.pop()

        # Op-amp pointing right, anchored at in2 (+) aligned horizontally with n_plus
        op = elm.Opamp(sign=True, leads=True).right().at((n_plus.center[0] + 1.2, n_plus.center[1])).anchor("in2")
        d += op

        # Direct horizontal wire from n_plus to in2 (+)
        d += elm.Line().at(n_plus.center).to(op.in2)

        # Output lead and node
        d += elm.Line().at(op.out).right().length(1.2)
        d += (out_dot := elm.Dot())
        d += elm.Line().at(out_dot.center).right().length(0.8).label("Vout", loc="right", color="#39FF88")

        # Negative feedback: from out_dot to INVERTING (-) input op.in1
        d += elm.Line().at(out_dot.center).up().length(1.5)
        d += elm.Line().left().tox(op.in1)
        d += elm.Line().toy(op.in1)

        # Upper C1 branch: from n1 up, across to out_dot
        d += elm.Line().at(n1.center).up().length(3.0)
        d += elm.Capacitor().tox(out_dot.center[0]).label(lbl_c1, loc="top", color=c_c1).color(c_c1)
        d += elm.Line().toy(out_dot.center[1])

        d.draw(show=False)
        ax.set_xlim(-1.2, 12.0)
        ax.set_ylim(-3.5, 4.8)
        ax.axis("off")

    elif circuit_id == "non_inverting_amp":
        c_rf, lbl_rf = get_comp_style("Rf", 100e3)
        c_rg, lbl_rg = get_comp_style("Rg", 2.2e3)

        d += elm.Dot().label("Vin", loc="left", color="#35D0FF")
        d += elm.Line().right().length(1.2)
        op = elm.Opamp(sign=True, leads=True).right().anchor("in2")
        d += op

        # Output lead and node
        d += elm.Line().at(op.out).right().length(1.2)
        d += (out_dot := elm.Dot())
        d += elm.Line().at(out_dot.center).right().length(0.8).label("Vout", loc="right", color="#39FF88")

        # Feedback loop through Rf to inverting node
        d += elm.Line().at(out_dot.center).up().length(2.0)
        d += elm.Resistor().left().tox(op.in1[0] - 0.8).label(lbl_rf, loc="top", color=c_rf).color(c_rf)
        d += (inv_node := elm.Dot())

        # Connection down to inverting input in1 (-)
        d += elm.Line().toy(op.in1)
        d += elm.Line().to(op.in1)

        # Rg resistor to ground from inv_node
        d += elm.Resistor().at(inv_node.center).left().length(2.0).label(lbl_rg, loc="top", color=c_rg).color(c_rg)
        d += elm.Ground().color(default_color)

        d.draw(show=False)
        ax.set_xlim(-3.8, 7.8)
        ax.set_ylim(-2.0, 4.4)
        ax.axis("off")

    else:
        d += elm.Dot().label("Vin", loc="left")
        d += elm.Line().right().length(2).label(f"Circuit: {circuit_id}")
        d += elm.Dot().label("Vout", loc="right")
        d.draw(show=False)
        ax.set_xlim(-1, 5)
        ax.set_ylim(-2, 2)
        ax.axis("off")

    buf = io.BytesIO()
    fig.savefig(buf, format="png", facecolor="#0E1419", dpi=150)
    plt.close(fig)
    return buf.getvalue()


def render_live_schematic(
    components: dict = None,
    label: str = "",
    changed_names: set = None,
    circuit_id: str = "sallen_key",
    old_components: dict = None,
    **kwargs
):
    """
    Component B: Live Schematic rendered via schemdraw and cached via st.cache_data.
    Accepts components, label string ("BEFORE (broken)" or "AFTER (verified)"),
    and optional changed_names set.
    """
    if isinstance(components, str):
        circuit_id = components
        components = kwargs.get("components") or {}
    if "circuit_id" in kwargs:
        circuit_id = kwargs["circuit_id"]
    if components is None:
        components = kwargs.get("final_components") or kwargs.get("initial_components") or {}
    if old_components is None:
        old_components = kwargs.get("initial_components") or {}
    if changed_names is None:
        changed_names = kwargs.get("changed_names") or set()
    if not isinstance(changed_names, (set, list, tuple)):
        changed_names = set()
    else:
        changed_names = set(changed_names)

    comp_tuple = tuple(sorted((str(k), float(v)) for k, v in components.items()))
    old_comp_tuple = tuple(sorted((str(k), float(v)) for k, v in old_components.items()))
    changed_tuple = tuple(sorted(str(k) for k in changed_names))

    png_bytes = get_schematic_png(
        circuit_id=circuit_id,
        components_tuple=comp_tuple,
        label=label,
        changed_names_tuple=changed_tuple,
        old_components_tuple=old_comp_tuple
    )

    try:
        st.image(png_bytes, width="stretch")
    except TypeError:
        st.image(png_bytes, use_container_width=True)



def render_pipeline_strip(current_step: int = 1, active_caption: str = "", height: int = 140, **kwargs):
    """
    Component C: Pipeline Strip
    4 stations rendered like a PCB trace route with state LEDs.
    Builds HTML without leading spaces so it never parses as a Markdown code block.
    """
    current_step = max(1, min(4, int(current_step or 1)))
    fill_pct = (current_step - 1) * 33.33

    stations = [
        {"num": 1, "icon": "💡", "name": "1. UNDERSTAND"},
        {"num": 2, "icon": "📐", "name": "2. ROUGH DESIGN"},
        {"num": 3, "icon": "🔍", "name": "3. SIMULATE & TEST"},
        {"num": 4, "icon": "🛠️", "name": "4. FIX & VERIFY"}
    ]

    stations_html_parts = []
    for s in stations:
        if s["num"] < current_step:
            chip_cls = "station-chip done"
            led_cls = "station-led done"
            name_cls = "station-name active"
        elif s["num"] == current_step:
            chip_cls = "station-chip active"
            led_cls = "station-led active"
            name_cls = "station-name active"
        else:
            chip_cls = "station-chip"
            led_cls = "station-led"
            name_cls = "station-name"

        stations_html_parts.append(
            f'<div class="station" id="st{s["num"]}">'
            f'<div class="{chip_cls}"><span class="station-icon">{s["icon"]}</span></div>'
            f'<span class="{name_cls}">{s["name"]}</span>'
            f'<span class="{led_cls}"></span>'
            f'</div>'
        )

    stations_inner = "".join(stations_html_parts)
    caption_txt = active_caption or "Ready"

    html = textwrap.dedent(f"""
<div class="route-container">
<div class="stations-bar">
<div class="trace-line"></div>
<div class="trace-active-fill" style="width: {fill_pct:.1f}%;"></div>
{stations_inner}
</div>
<div class="caption-strip">{caption_txt}</div>
</div>
""").strip()

    st.markdown(html, unsafe_allow_html=True)


def render_signal_cleanup_view(
    t: list = None,
    v_in: list = None,
    v_broken: list = None,
    v_fixed: list = None,
    height: int = 420,
    **kwargs
):
    """
    Component D: Signal Cleanup View (Transient mini scopes)
    Three stacked CRT traces: "What goes in", "Before fix", "After fix".
    Full width of container column.
    """
    # Accept alternative parameter names gracefully if passed
    t_val = t if t is not None else kwargs.get("time_arr", kwargs.get("time"))
    v_in_val = v_in if v_in is not None else kwargs.get("vin_arr")
    v_broken_val = v_broken if v_broken is not None else kwargs.get("v_broken_arr")
    v_fixed_val = v_fixed if v_fixed is not None else kwargs.get("v_fixed_arr")

    payload = {
        "t": [float(x) for x in t_val] if t_val is not None else [],
        "v_in": [float(x) for x in v_in_val] if v_in_val is not None else [],
        "v_broken": [float(x) for x in v_broken_val] if v_broken_val is not None else [],
        "v_fixed": [float(x) for x in v_fixed_val] if v_fixed_val is not None else []
    }
    json_data = json.dumps(payload)

    html_code = f"""
    <!DOCTYPE html>
    <html>
    <head>
    <meta charset="utf-8">
    <style>
        @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600&family=Share+Tech+Mono&display=swap');
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            background: transparent;
            font-family: 'JetBrains Mono', monospace;
            color: #D7E3EA;
            overflow: hidden;
            width: 100%;
            display: block;
        }}
        .scope-stack {{
            background: #0A0F14;
            border: 2px solid #1B2A33;
            border-radius: 12px;
            padding: 14px;
            width: 100%;
            display: flex;
            flex-direction: column;
            gap: 10px;
            box-shadow: inset 0 0 20px rgba(0,0,0,0.8);
        }}
        .mini-scope {{
            background: #04070A;
            border: 1px solid #14232C;
            border-radius: 6px;
            position: relative;
            padding: 8px 12px;
            overflow: hidden;
        }}
        .mini-header {{
            display: flex;
            justify-content: space-between;
            font-size: 12px;
            text-transform: uppercase;
            letter-spacing: 1px;
            margin-bottom: 4px;
            font-weight: 600;
        }}
        canvas {{
            display: block;
            width: 100%;
            height: 82px;
        }}
    </style>
    </head>
    <body>
    <div class="scope-stack">
        <div class="mini-scope">
            <div class="mini-header">
                <span style="color: #9FB3BE;">CH1: WHAT GOES IN (INPUT SIGNAL)</span>
                <span style="color: #9FB3BE;">TRANSIENT SWEEP</span>
            </div>
            <canvas id="cIn"></canvas>
        </div>
        <div class="mini-scope">
            <div class="mini-header">
                <span style="color: #FFB000;">CH2: BEFORE FIX (DISTORTED / NOISY)</span>
                <span style="color: #FFB000;">FAIL PRESET</span>
            </div>
            <canvas id="cBroken"></canvas>
        </div>
        <div class="mini-scope">
            <div class="mini-header">
                <span style="color: #39FF88;">CH3: AFTER FIX (VERIFIED CLEAN OUTPUT)</span>
                <span style="color: #39FF88;">PASS SPEC</span>
            </div>
            <canvas id="cFixed"></canvas>
        </div>
    </div>

    <script>
    (function() {{
        try {{
            const data = {json_data};
            function drawTrace(canvasId, yVals, strokeColor) {{
                const canvas = document.getElementById(canvasId);
                if (!canvas || !yVals || yVals.length < 2) return;
                const ctx = canvas.getContext('2d');
                const dpr = window.devicePixelRatio || 1;
                const rect = canvas.getBoundingClientRect();
                canvas.width = rect.width * dpr;
                canvas.height = rect.height * dpr;
                ctx.scale(dpr, dpr);

                const W = rect.width, H = rect.height;
                ctx.strokeStyle = '#0E1C24';
                ctx.lineWidth = 1;
                for (let i = 0; i <= 6; i++) {{
                    ctx.beginPath();
                    ctx.moveTo((i / 6) * W, 0);
                    ctx.lineTo((i / 6) * W, H);
                    ctx.stroke();
                }}
                ctx.beginPath();
                ctx.moveTo(0, H / 2);
                ctx.lineTo(W, H / 2);
                ctx.stroke();

                let minV = Infinity, maxV = -Infinity;
                for (let i = 0; i < yVals.length; i++) {{
                    if (yVals[i] < minV) minV = yVals[i];
                    if (yVals[i] > maxV) maxV = yVals[i];
                }}
                if (!isFinite(minV) || !isFinite(maxV)) {{ minV = -1; maxV = 1; }}
                if (Math.abs(maxV - minV) < 1e-4) {{ minV -= 1; maxV += 1; }}

                ctx.beginPath();
                for (let i = 0; i < yVals.length; i++) {{
                    const x = (i / (yVals.length - 1)) * W;
                    const y = H - ((yVals[i] - minV) / (maxV - minV)) * (H - 12) - 6;
                    if (i === 0) ctx.moveTo(x, y);
                    else ctx.lineTo(x, y);
                }}

                ctx.strokeStyle = strokeColor;
                ctx.lineWidth = 4;
                ctx.globalAlpha = 0.25;
                ctx.stroke();

                ctx.lineWidth = 1.8;
                ctx.globalAlpha = 0.95;
                ctx.stroke();
            }}

            drawTrace('cIn', data.v_in, '#9FB3BE');
            drawTrace('cBroken', data.v_broken, '#FFB000');
            drawTrace('cFixed', data.v_fixed, '#39FF88');
        }} catch(e) {{
            console.error("Signal cleanup view error:", e);
        }}
    }})();
    </script>
    </body>
    </html>
    """
    components.html(html_code, height=height, scrolling=False)


def render_boot_sequence(ai_online: bool = False, height: int = 240, **kwargs):
    """
    Component E: Boot Sequence (Empty state only)
    Terminal typeout with idling phosphor sine wave and subsystem self-tests (<2s).
    Full width of container column.
    """
    ai_status_str = "Gemini Online [Cloud Accelerated]" if ai_online else "Offline Demo Mode [Heuristic Core]"
    ai_color = "#39FF88" if ai_online else "#FFB000"

    html_code = f"""
    <!DOCTYPE html>
    <html>
    <head>
    <meta charset="utf-8">
    <style>
        @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600&family=Share+Tech+Mono&display=swap');
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            background: transparent;
            font-family: 'Share Tech Mono', monospace;
            color: #D7E3EA;
            overflow: hidden;
            width: 100%;
            display: block;
        }}
        .boot-console {{
            background: #060A0D;
            border: 1px solid #1B2A33;
            border-radius: 12px;
            padding: 18px 24px;
            width: 100%;
            box-shadow: inset 0 0 30px rgba(0,0,0,0.9), 0 4px 20px rgba(0,0,0,0.5);
            display: flex;
            gap: 24px;
            align-items: center;
        }}
        .idle-scope {{
            width: 190px;
            height: 125px;
            background: #030608;
            border: 1px solid #1B2A33;
            border-radius: 8px;
            overflow: hidden;
            flex-shrink: 0;
            position: relative;
        }}
        canvas {{
            display: block;
            width: 100%;
            height: 100%;
        }}
        .term-lines {{
            flex: 1;
            font-size: 15px;
            line-height: 1.6;
            color: #A5C0D0;
        }}
        .ok-tag {{
            color: #39FF88;
            font-weight: bold;
        }}
        .cursor-blink {{
            display: inline-block;
            width: 8px;
            height: 16px;
            background: #35D0FF;
            vertical-align: middle;
            animation: blink 0.8s infinite;
        }}
        @keyframes blink {{
            0%, 50% {{ opacity: 1; }}
            51%, 100% {{ opacity: 0; }}
        }}
    </style>
    </head>
    <body>
    <div class="boot-console">
        <div class="idle-scope">
            <canvas id="idleCanvas"></canvas>
        </div>
        <div class="term-lines">
            <div style="color: #35D0FF; font-weight: bold; letter-spacing: 1px;">>>> CIRCUIT ASSISTANT FIRMWARE v2.5</div>
            <div>ngspice physical simulator .......... <span class="ok-tag">[ OK ]</span></div>
            <div>Nelder-Mead SPICE loop ............ <span class="ok-tag">[ CALIBRATED ]</span></div>
            <div>AI Reasoning Engine ................ <span style="color: {ai_color}; font-weight: bold;">[ {ai_status_str} ]</span></div>
            <div style="margin-top: 4px; color: #D7E3EA;">READY. Select a preset or type below <span class="cursor-blink"></span></div>
        </div>
    </div>

    <script>
    (function() {{
        try {{
            const canvas = document.getElementById('idleCanvas');
            const ctx = canvas.getContext('2d');
            const dpr = window.devicePixelRatio || 1;
            const rect = canvas.getBoundingClientRect();
            canvas.width = rect.width * dpr;
            canvas.height = rect.height * dpr;
            ctx.scale(dpr, dpr);

            const W = rect.width, H = rect.height;
            let t = 0;

            function animate() {{
                ctx.clearRect(0, 0, W, H);
                ctx.strokeStyle = '#0E1C24';
                ctx.lineWidth = 1;
                ctx.beginPath();
                ctx.moveTo(0, H/2);
                ctx.lineTo(W, H/2);
                ctx.moveTo(W/2, 0);
                ctx.lineTo(W/2, H);
                ctx.stroke();

                ctx.beginPath();
                for (let x = 0; x < W; x++) {{
                    const y = H/2 + Math.sin((x * 0.05) - t) * 22;
                    if (x === 0) ctx.moveTo(x, y);
                    else ctx.lineTo(x, y);
                }}
                ctx.strokeStyle = '#39FF88';
                ctx.lineWidth = 3;
                ctx.globalAlpha = 0.25;
                ctx.stroke();

                ctx.lineWidth = 1.5;
                ctx.globalAlpha = 0.95;
                ctx.stroke();

                t += 0.06;
                requestAnimationFrame(animate);
            }}
            requestAnimationFrame(animate);
        }} catch(e) {{
            console.error("Boot sequence error:", e);
        }}
    }})();
    </script>
    </body>
    </html>
    """
    components.html(html_code, height=height, scrolling=False)
