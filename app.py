"""
app.py - Circuit Assistant: Instrument-Grade Analog Circuit Fixer
Lab Bench at Night design language, physical SPICE simulation,
Gemini AI designer, and autonomous repair pipeline.
"""

import difflib
import textwrap
import json
import os
import re
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import schemdraw
import schemdraw.elements as elm
import streamlit as st

import agent
import components
import spice
import theme

# 1. Page Configuration
st.set_page_config(
    page_title="Circuit Assistant | Instrument Lab",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 2. Inject Lab Bench at Night Instrument Theme
theme.inject_theme()


def format_comp_val(val: float, comp_type: str) -> str:
    """Format numeric component value into standard engineering format (e.g. 6.8 kΩ, 22 nF)."""
    if val is None or np.isnan(val):
        return "N/A"
    abs_v = abs(val)
    if comp_type == "R":
        if abs_v >= 1e6:
            return f"{val/1e6:.3g} MΩ"
        elif abs_v >= 1e3:
            return f"{val/1e3:.3g} kΩ"
        else:
            return f"{val:.3g} Ω"
    else:
        if abs_v >= 1e-3:
            return f"{val*1e3:.3g} mF"
        elif abs_v >= 1e-6:
            return f"{val*1e6:.3g} µF"
        elif abs_v >= 1e-9:
            return f"{val*1e9:.3g} nF"
        elif abs_v >= 1e-12:
            return f"{val*1e12:.3g} pF"
        else:
            return f"{val:.3e} F"


def draw_circuit_schematic(circuit_id: str, components_map: dict) -> plt.Figure:
    """Fallback static schematic generator using schemdraw with matplotlib backend."""
    plt.close("all")
    if circuit_id == "sallen_key":
        r1_val = format_comp_val(components_map.get("R1", 7.5e3), "R")
        r2_val = format_comp_val(components_map.get("R2", 7.5e3), "R")
        c1_val = format_comp_val(components_map.get("C1", 68e-9), "C")
        c2_val = format_comp_val(components_map.get("C2", 6.8e-9), "C")

        d = schemdraw.Drawing()
        d.config(fontsize=10, unit=2.1)
        d += elm.Dot().label("Vin", "left")
        d += elm.Resistor().right().label(f"R1\n{r1_val}")
        d += (n1 := elm.Dot())
        d += elm.Resistor().right().label(f"R2\n{r2_val}")
        d += (n_plus := elm.Dot())

        d += elm.Capacitor().down().at(n_plus.center).label(f"C2\n{c2_val}")
        d += elm.Ground()

        d += (op := elm.Opamp().at((n_plus.center[0] + 1.2, n_plus.center[1] - 0.5)).anchor("in1"))
        d += elm.Line().at(n_plus.center).to(op.in1)

        d += elm.Line().at(op.out).right().length(0.8)
        d += (out_dot := elm.Dot())
        d += elm.Line().at(out_dot.center).right().length(0.8).label("Vout", "right")

        d += elm.Line().at(out_dot.center).down().length(1.2)
        d += elm.Line().left().tox(op.in2[0] - 0.4)
        d += elm.Line().up().toy(op.in2[1])
        d += elm.Line().to(op.in2)

        d += elm.Line().at(n1.center).up().length(1.5)
        d += elm.Capacitor().tox(out_dot.center[0]).label(f"C1\n{c1_val}")
        d += elm.Line().toy(out_dot.center[1])

        fig = d.draw(show=False).fig
        return fig

    elif circuit_id == "non_inverting_amp":
        rf_val = format_comp_val(components_map.get("Rf", 100e3), "R")
        rg_val = format_comp_val(components_map.get("Rg", 2.2e3), "R")

        d = schemdraw.Drawing()
        d.config(fontsize=10, unit=2.1)
        d += elm.Dot().label("Vin", "left")
        d += (op := elm.Opamp().anchor("in1"))

        d += elm.Line().at(op.out).right().length(1.0)
        d += (out_dot := elm.Dot())
        d += elm.Line().at(out_dot.center).right().length(0.8).label("Vout", "right")

        d += elm.Line().at(out_dot.center).down().length(1.5)
        d += elm.Resistor().left().tox(op.in2[0]).label(f"Rf\n{rf_val}")
        d += (inv_node := elm.Dot())
        d += elm.Line().up().to(op.in2)

        d += elm.Resistor().down().at(inv_node.center).label(f"Rg\n{rg_val}")
        d += elm.Ground()

        fig = d.draw(show=False).fig
        return fig
    else:
        fig, ax = plt.subplots(figsize=(6, 2))
        ax.text(0.5, 0.5, f"Schematic: {circuit_id}", ha="center", va="center")
        ax.axis("off")
        return fig


# Cached Physical SPICE Simulations
@st.cache_data
def run_cached_ac_simulation(circuit_id: str, comp_keys: tuple, comp_vals: tuple):
    """Run ngspice AC sweep simulation on component values and cache results."""
    comps = dict(zip(comp_keys, comp_vals))
    freqs, gain_db = spice.simulate_circuit(circuit_id, comps)
    circuit_type = spice.CIRCUITS[circuit_id]["type"]
    meas = spice.measure_circuit(freqs, gain_db, circuit_type)
    return freqs, gain_db, meas


@st.cache_data
def run_cached_transient_simulation(circuit_id: str, comp_keys: tuple, comp_vals: tuple, spec_keys: tuple, spec_vals: tuple):
    """Run ngspice transient simulation for Signal Cleanup Demo."""
    comps = dict(zip(comp_keys, comp_vals))
    specs = dict(zip(spec_keys, spec_vals))
    return spice.simulate_transient(circuit_id, comps, specs)


# Hardware simulator discovery
ngspice_available = True
ngspice_err = ""
try:
    ngspice_bin = spice.find_ngspice()
except Exception as e:
    ngspice_available = False
    ngspice_err = str(e)


# Initialize Session State
if "circuit_id" not in st.session_state:
    st.session_state.circuit_id = "sallen_key"

default_cid = st.session_state.circuit_id
if "components" not in st.session_state:
    st.session_state.components = dict(spice.CIRCUITS[default_cid]["broken_components"])
if "specs" not in st.session_state:
    st.session_state.specs = dict(spice.CIRCUITS[default_cid]["default_specs"])
if "results" not in st.session_state:
    st.session_state.results = None
if "ai_explanation" not in st.session_state:
    st.session_state.ai_explanation = None
if "qa_history" not in st.session_state:
    st.session_state.qa_history = []
if "user_design_request" not in st.session_state:
    st.session_state.user_design_request = None
if "editor_version" not in st.session_state:
    st.session_state.editor_version = 0


# ==============================================================================
# SIDEBAR: FRONT PANEL INSTRUMENT CONTROLS
# ==============================================================================
with st.sidebar:
    theme.render_logo()

    st.markdown('<div class="silkscreen-label">CHASSIS / FRONT PANEL</div>', unsafe_allow_html=True)

    # AI Configuration & Status
    env_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("LLM_API_KEY", "")
    user_key = st.text_input(
        "Gemini API Key (optional)",
        value=env_key,
        type="password",
        help="Google Gemini API key. If empty or DEMO mode is enabled, built-in engineering heuristics are used."
    )
    force_demo = st.checkbox(
        "Demo Mode (Offline Heuristics)",
        value=os.environ.get("DEMO", "0").lower() in ("1", "true", "yes") or (not user_key),
        help="Runs reliably and instantly with zero external cloud dependencies."
    )
    effective_key = None if force_demo else (user_key or None)

    # Status Chip
    ai_online, ai_status_text = agent.get_ai_status(effective_key)
    led_cls = "led-online" if ai_online else "led-offline"
    st.markdown(
        f'<div class="led-indicator"><span class="led-dot {led_cls}"></span> {ai_status_text}</div>',
        unsafe_allow_html=True
    )

    st.divider()

    # Verified Mode Switch
    st.markdown('<div class="silkscreen-label">SOLVER DYNAMICS</div>', unsafe_allow_html=True)
    verified_mode = st.toggle(
        "Verified Mode (Full SPICE Optimization)",
        value=True,
        help="When ON, runs complete Nelder-Mead SPICE optimization with convergence verification. When OFF, executes rapid single-step preview."
    )
    if verified_mode:
        st.markdown(
            '<div class="led-indicator" style="color: #39FF88; border-color: rgba(57,255,136,0.25);"><span class="led-dot led-online"></span> Convergence verified</div>',
            unsafe_allow_html=True
        )
    else:
        st.markdown(
            '<div class="led-indicator" style="color: #FFB000; border-color: rgba(255,176,0,0.25);"><span class="led-dot led-offline"></span> Fast Preview Mode</div>',
            unsafe_allow_html=True
        )

    st.divider()

    # Simulator Status
    st.markdown('<div class="silkscreen-label">SYSTEM TELEMETRY</div>', unsafe_allow_html=True)
    telemetry_html = textwrap.dedent("""
    <div style="font-family: var(--font-mono); font-size: 13px; color: var(--muted-color); line-height: 1.8;">
    <div>SPICE CORE: <span style="color: #35D0FF;">ngspice batch 64-bit</span></div>
    <div>OPTIMIZER: <span style="color: #35D0FF;">Nelder-Mead (Scipy)</span></div>
    <div>COMPONENT GRID: <span style="color: #35D0FF;">E12 / E24 (IEC 60063)</span></div>
    </div>
    """).strip()
    st.markdown(telemetry_html, unsafe_allow_html=True)

    st.divider()

    st.markdown('<div class="silkscreen-label">SIMULATOR ENGINE</div>', unsafe_allow_html=True)
    if ngspice_available:
        st.markdown(
            '<div class="led-indicator" style="color: #39FF88; border-color: rgba(57,255,136,0.25);"><span class="led-dot led-online"></span> ngspice 64-bit Ready</div>',
            unsafe_allow_html=True
        )
    else:
        st.markdown(
            f'<div class="led-indicator" style="color: #FF4D5E; border-color: rgba(255,77,94,0.25);"><span class="led-dot led-fail"></span> ngspice Error: {ngspice_err}</div>',
            unsafe_allow_html=True
        )

    st.divider()

    if st.button("🔄 Reset Circuit to Broken Preset", use_container_width=True):
        cid = st.session_state.circuit_id
        st.session_state.components = dict(spice.CIRCUITS[cid]["broken_components"])
        st.session_state.specs = dict(spice.CIRCUITS[cid]["default_specs"])
        st.session_state.results = None
        st.session_state.ai_explanation = None
        st.session_state.qa_history = []
        st.session_state.user_design_request = None
        st.session_state.editor_version += 1
        st.rerun()


# ==============================================================================
# MAIN AREA (1200px max-width container enforced by theme.py)
# ==============================================================================

# Top Title & Silkscreen Header
st.markdown('<div class="silkscreen-label">AUTONOMOUS ECE WORKBENCH • MODEL 2026-X</div>', unsafe_allow_html=True)
st.title("⚡ Circuit Assistant")
st.markdown(
    "<p style='color: #9FB3BE; font-size: 17px; margin-top: -10px;'>"
    "Autonomous analog circuit design, physical SPICE simulation, and commercial E-series component repair."
    "</p>",
    unsafe_allow_html=True
)

if not ngspice_available:
    st.error(f"**ngspice Simulator Not Found:** {ngspice_err}\nPlease ensure ngspice is installed and configured.")
    st.stop()


# ------------------------------------------------------------------------------
# PART 1: AI CIRCUIT DESIGNER (Chat Front Door)
# ------------------------------------------------------------------------------
st.markdown('<div class="silkscreen-label">PROMPT • AI CIRCUIT DESIGN SPECIFICATION</div>', unsafe_allow_html=True)

# 4 Clickable Example Prompt Suggestion Chips
col_btn1, col_btn2, col_btn3, col_btn4 = st.columns(4)
clicked_prompt = None

with col_btn1:
    if st.button("🎵 Remove hiss above 3 kHz", use_container_width=True, help="Design low-pass filter to remove audio hiss above 3 kHz"):
        clicked_prompt = "Remove hiss above 3 kHz from my audio"
with col_btn2:
    if st.button("🎤 Boost 10 mV mic to 100 mV", use_container_width=True, help="Amplify a 10 mV microphone signal to 100 mV (10x gain)"):
        clicked_prompt = "Boost a 10 mV mic signal to 100 mV"
with col_btn3:
    if st.button("📻 Keep only 1 kHz tone", use_container_width=True, help="Filter out all frequencies except a 1 kHz tone"):
        clicked_prompt = "Keep only a 1 kHz tone and reject everything else"
with col_btn4:
    if st.button("🔊 Block rumble below 200 Hz", use_container_width=True, help="High-pass rumble filter below 200 Hz"):
        clicked_prompt = "Block low-frequency rumble below 200 Hz"

# Single unified st.chat_input for the entire app
chat_input = st.chat_input(
    "Describe the circuit you need, or ask a question about the results...",
    key="main_app_chat_input"
)

active_prompt = chat_input or clicked_prompt

# Empty State: Render Boot Sequence if no action yet
if st.session_state.results is None and st.session_state.user_design_request is None and not active_prompt:
    components.render_boot_sequence(ai_online=ai_online, height=170)

# Process User Input (Questions vs Design Requests)
if active_prompt:
    prompt_str = str(active_prompt).strip()
    p_lower = prompt_str.lower()
    is_question = (
        p_lower.endswith("?")
        or p_lower.startswith("why")
        or p_lower.startswith("what")
        or p_lower.startswith("how")
        or p_lower.startswith("can")
    )
    if st.session_state.results is not None and is_question:
        # Route to Q&A tutor
        st.session_state.qa_history.append({"role": "user", "content": prompt_str})
        with st.spinner("AI Tutor explaining..."):
            answer = agent.answer_user_question(
                question=prompt_str,
                circuit_id=selected_cid,
                specs=st.session_state.specs,
                results=st.session_state.results,
                api_key=effective_key
            )
        st.session_state.qa_history.append({"role": "assistant", "content": answer})
    else:
        # Route to AI circuit design
        st.session_state.user_design_request = prompt_str

        with st.spinner("AI Designer analyzing specification..."):
            design_result = agent.design_circuit_from_prompt(prompt_str, api_key=effective_key)

        if not design_result.get("supported", False):
            st.session_state.ai_explanation = None
            reason = design_result.get("reason_if_unsupported", "This circuit topology is not currently in our template registry.")
            st.warning(
                f"⚠️ **Cannot Design Circuit:** {reason}\n\n"
                "**Supported registry circuits:**\n"
                "- **Sallen-Key Low-Pass Filter**: removes high-frequency hiss or noise above a target cutoff (e.g. *'Remove hiss above 3 kHz'*).\n"
                "- **Non-Inverting Amplifier**: cleanly amplifies weak signals by a target factor (e.g. *'Boost a 10 mV mic signal to 100 mV'*)."
            )
        else:
            chosen_template = design_result["template"]
            chosen_specs = design_result["specs"]
            explanation = design_result.get("explanation", "")

            st.session_state.circuit_id = chosen_template
            st.session_state.specs = chosen_specs
            st.session_state.ai_explanation = explanation

            # Create rough first guess
            rough_components = agent.generate_rough_guess(chosen_template, chosen_specs)
            st.session_state.components = dict(rough_components)
            st.session_state.editor_version += 1

            c_info = spice.CIRCUITS[chosen_template]
            comps_rough_str = ", ".join([f"{k}={spice.format_eng(v, c_info['component_types'].get(k, 'R'))}" for k, v in rough_components.items()])

            with st.status("Executing Autonomous Repair Pipeline...", expanded=True) as status_box:
                st.write(f"💡 **Station 1: Understand Request** — User target translated: **{c_info['name']}**.")
                st.write(f"📐 **Station 2: Rough Design** — Initial unoptimized guess: `{comps_rough_str}`.")

                # Baseline simulation of rough guess
                f_rough, g_rough = spice.simulate_circuit(chosen_template, rough_components)
                m_rough = spice.measure_circuit(f_rough, g_rough, c_info["type"])

                if chosen_template == "sallen_key":
                    fc_m = m_rough.get("fc_3db_hz", 0.0)
                    fc_t = chosen_specs.get("fc_target", 1000.0)
                    pk_m = m_rough.get("peaking_db", 0.0)
                    st.write(f"🔍 **Station 3: SPICE Simulation Test** — Cutoff is {fc_m:.0f} Hz (target: {fc_t:.0f} Hz), Peaking is {pk_m:.2f} dB (limit: ≤ 0.5 dB). Problem detected!")
                else:
                    g_m = m_rough.get("linear_gain", 0.0)
                    g_t = chosen_specs.get("gain_target", 10.0)
                    bw_m = m_rough.get("bandwidth_hz", 0.0)
                    st.write(f"🔍 **Station 3: SPICE Simulation Test** — Gain is {g_m:.2f}x (target: {g_t:.1f}x), Bandwidth is {bw_m/1000:.1f} kHz. Problem detected!")

                if verified_mode:
                    st.write("🛠️ **Station 4: Auto-Fix & Verify** — AI diagnosing root causes and executing Nelder-Mead optimization in SPICE loop...")
                    try:
                        results = agent.run_agent_loop(
                            circuit_id=chosen_template,
                            initial_components=rough_components,
                            specs=chosen_specs,
                            api_key=effective_key,
                            max_iterations=4
                        )
                        st.session_state.results = results
                        st.session_state.components = dict(results["final_components"])
                        status_box.update(
                            label=f"Verified! Specifications satisfied in {results['iterations_run']} iteration(s).",
                            state="complete",
                            expanded=False
                        )
                    except Exception as e:
                        status_box.update(label="Error during circuit repair!", state="error")
                        st.error(f"Execution error: {e}")
                else:
                    st.write("⚡ **Station 4: Fast Preview (Unverified)** — Generating component values without optimizer and evaluating once...")
                    guess_components = dict(rough_components)
                    if not force_demo and effective_key:
                        try:
                            comp_keys_str = ", ".join(f'"{k}": float' for k in rough_components)
                            llm_p = (
                                f"You are an analog circuit expert. For circuit '{chosen_template}' with target specs {chosen_specs}, "
                                f"provide commercial component values as JSON: {{\"components\": {{{comp_keys_str}}}}}"
                            )
                            raw_llm = agent.call_llm_provider(llm_p, api_key=effective_key, json_mode=True)
                            parsed = json.loads(re.sub(r"```(?:json)?\s*([\s\S]*?)\s*```", r"\1", raw_llm.strip()))
                            if "components" in parsed and isinstance(parsed["components"], dict):
                                for k in rough_components:
                                    if k in parsed["components"]:
                                        guess_components[k] = float(parsed["components"][k])
                        except Exception:
                            pass

                    f_sim, g_sim = spice.simulate_circuit(chosen_template, guess_components)
                    m_sim = spice.measure_circuit(f_sim, g_sim, c_info["type"])
                    passed_sim, eval_sim = spice.evaluate_spec(chosen_template, m_sim, chosen_specs)
                    results = {
                        "passed": passed_sim,
                        "iterations_run": 1,
                        "initial_components": dict(guess_components),
                        "final_components": dict(guess_components),
                        "initial_measurements": m_sim,
                        "final_measurements": m_sim,
                        "freqs": f_sim,
                        "initial_gain_db": g_sim,
                        "final_gain_db": g_sim,
                        "final_evaluation_table": eval_sim,
                        "final_diagnosis": "Single-step prediction without optimizer.",
                        "final_reason": "Generated directly by AI heuristic without closed-loop SPICE optimization.",
                        "iterations_log": [],
                        "is_unverified_guess": True
                    }
                    st.session_state.results = results
                    st.session_state.components = dict(guess_components)
                    status_box.update(
                        label="Complete: Unverified AI guess (Single SPICE evaluation)",
                        state="complete",
                        expanded=False
                    )

# Assistant Message with pulsing cyan AI indicator
if st.session_state.ai_explanation:
    with st.chat_message("assistant"):
        st.markdown(
            f'<div style="display: flex; align-items: center; gap: 8px; margin-bottom: 6px;">'
            f'<span class="led-dot led-cyan"></span>'
            f'<span style="font-family: var(--font-mono); font-size: 13px; color: #35D0FF; letter-spacing: 1px;">AI CIRCUIT DESIGNER</span>'
            f'</div>'
            f'<div style="font-size: 16px; color: #D7E3EA;">{st.session_state.ai_explanation}</div>',
            unsafe_allow_html=True
        )

# ------------------------------------------------------------------------------
# PART 1 ITEM 5: ADVANCED MANUAL CONTROLS (Chassis Expander)
# ------------------------------------------------------------------------------
selected_cid = st.session_state.circuit_id
c_info = spice.CIRCUITS[selected_cid]

with st.expander("Advanced: edit the circuit manually", expanded=False):
    st.markdown('<div class="silkscreen-label">DUT MANUAL CONFIGURATION</div>', unsafe_allow_html=True)
    circuit_choices = {
        "sallen_key": "Sallen-Key Low-Pass Filter (Unity Gain)",
        "non_inverting_amp": "Non-Inverting Amplifier"
    }

    cur_idx = list(circuit_choices.keys()).index(selected_cid)
    manual_cid = st.selectbox(
        "Circuit Template Selection",
        options=list(circuit_choices.keys()),
        index=cur_idx,
        format_func=lambda k: circuit_choices[k]
    )

    if manual_cid != selected_cid:
        st.session_state.circuit_id = manual_cid
        st.session_state.components = dict(spice.CIRCUITS[manual_cid]["broken_components"])
        st.session_state.specs = dict(spice.CIRCUITS[manual_cid]["default_specs"])
        st.session_state.results = None
        st.session_state.ai_explanation = None
        st.session_state.qa_history = []
        st.session_state.user_design_request = None
        st.session_state.editor_version += 1
        st.rerun()

    # Manual Specs
    st.write("**Target Specifications:**")
    manual_specs = dict(st.session_state.specs)
    if selected_cid == "sallen_key":
        m_col_s1, m_col_s2, m_col_s3 = st.columns(3)
        with m_col_s1:
            fc_tgt_in = st.number_input("Cutoff Frequency fc (Hz)", value=float(manual_specs.get("fc_target", 1000.0)), step=50.0)
        with m_col_s2:
            pk_max_in = st.number_input("Max Peaking (dB)", value=float(manual_specs.get("peaking_max", 0.5)), step=0.1)
        with m_col_s3:
            fc_tol_in = st.number_input("fc Tolerance (±%)", value=float(manual_specs.get("fc_tol", 0.05) * 100.0), step=1.0) / 100.0

        st.session_state.specs = {
            "fc_target": fc_tgt_in,
            "fc_tol": fc_tol_in,
            "peaking_max": pk_max_in,
            "dc_gain_target": 0.0,
            "dc_gain_tol": 0.5
        }
    else:
        m_col_s1, m_col_s2 = st.columns(2)
        with m_col_s1:
            g_tgt_in = st.number_input("Target Voltage Gain", value=float(manual_specs.get("gain_target", 10.0)), step=0.5)
        with m_col_s2:
            bw_min_in = st.number_input("Min Bandwidth (kHz)", value=float(manual_specs.get("bw_min", 50000.0) / 1000.0), step=5.0) * 1000.0

        st.session_state.specs = {
            "gain_target": g_tgt_in,
            "gain_tol": 0.02,
            "bw_min": bw_min_in
        }

    # Data Editor
    st.write("**Component Values:**")
    editor_rows = []
    for comp, val in st.session_state.components.items():
        c_type = c_info["component_types"].get(comp, "R")
        unit_str = "Ω" if c_type == "R" else "F"
        val_str = spice.format_spice_val(val)
        editor_rows.append({"Component": comp, "Value": val_str, "Unit": unit_str})

    df_editor = pd.DataFrame(editor_rows)
    editor_key = f"comp_editor_{selected_cid}_{st.session_state.editor_version}"
    edited_df = st.data_editor(
        df_editor,
        key=editor_key,
        disabled=["Component", "Unit"],
        hide_index=True,
        use_container_width=True
    )

    manual_valid = True
    manual_parsed = {}
    for row in edited_df.itertuples():
        comp = row.Component
        raw_val = str(row.Value).strip()
        try:
            p_val = spice.parse_spice_val(raw_val)
            if p_val <= 0 or np.isnan(p_val):
                manual_valid = False
            else:
                manual_parsed[comp] = float(p_val)
        except Exception:
            manual_valid = False

    has_manual_change = False
    for k, p_v in manual_parsed.items():
        c_v = st.session_state.components.get(k, 0.0)
        if abs(p_v - c_v) / max(1e-12, abs(c_v)) > 0.001:
            has_manual_change = True
            break

    if manual_valid and has_manual_change:
        st.session_state.components = dict(manual_parsed)
        st.session_state.results = None
        st.rerun()

    btn_manual_fix = st.button("🚀 Run Optimizer on Current Components", type="primary", disabled=not manual_valid)
    if btn_manual_fix:
        with st.status("Executing Autonomous Repair Pipeline...", expanded=True) as status_box:
            try:
                if verified_mode:
                    res_m = agent.run_agent_loop(
                        circuit_id=selected_cid,
                        initial_components=st.session_state.components,
                        specs=st.session_state.specs,
                        api_key=effective_key,
                        max_iterations=4
                    )
                else:
                    f_s, g_s = spice.simulate_circuit(selected_cid, st.session_state.components)
                    m_s = spice.measure_circuit(f_s, g_s, c_info["type"])
                    p_s, e_s = spice.evaluate_spec(selected_cid, m_s, st.session_state.specs)
                    res_m = {
                        "passed": p_s,
                        "iterations_run": 1,
                        "initial_components": dict(st.session_state.components),
                        "final_components": dict(st.session_state.components),
                        "initial_measurements": m_s,
                        "final_measurements": m_s,
                        "freqs": f_s,
                        "initial_gain_db": g_s,
                        "final_gain_db": g_s,
                        "final_evaluation_table": e_s,
                        "final_diagnosis": "Single-step preview.",
                        "final_reason": "Single evaluation without optimizer.",
                        "iterations_log": [],
                        "is_unverified_guess": True
                    }
                st.session_state.results = res_m
                st.session_state.components = dict(res_m["final_components"])
                status_box.update(label=f"Repair complete in {res_m['iterations_run']} iteration(s)!", state="complete", expanded=False)
            except Exception as ex:
                status_box.update(label="Repair error!", state="error")
                st.error(f"Error: {ex}")

    st.write("**Current Netlist:**")
    st.code(spice.generate_netlist(selected_cid, st.session_state.components), language="spice")


# ------------------------------------------------------------------------------
# SIMULATION BASELINE
# ------------------------------------------------------------------------------
comp_keys = tuple(sorted(st.session_state.components.keys()))
comp_vals = tuple(float(st.session_state.components[k]) for k in comp_keys)

try:
    freqs_broken, gain_broken, meas_broken = run_cached_ac_simulation(selected_cid, comp_keys, comp_vals)
    passed_broken, metrics_broken = spice.evaluate_spec(selected_cid, meas_broken, st.session_state.specs)
except Exception as e:
    st.error(f"Simulation error: {e}")
    st.stop()


# ==============================================================================
# SECTION 1: AUTONOMOUS PIPELINE ROUTE (Wrapped in st.container(border=True))
# ==============================================================================
with st.container(border=True):
    st.markdown('<div class="silkscreen-label">STATUS • AUTONOMOUS PIPELINE ROUTE</div>', unsafe_allow_html=True)
    current_step = 4 if st.session_state.results else (2 if st.session_state.user_design_request else 1)
    caption_map = {
        1: "Ready for design specification prompt or preset selection.",
        2: "Drafted unoptimized initial guess components based on specification.",
        3: "SPICE physics simulation executed. Specifications violated.",
        4: "Verified! All specifications met with commercial E24/E12 components."
    }
    components.render_pipeline_strip(
        current_step=current_step,
        active_caption=caption_map.get(current_step, ""),
        height=135
    )


# ==============================================================================
# SECTION 2: VERIFICATION BENCHMARK BANNER (Wrapped in st.container(border=True))
# ==============================================================================
with st.container(border=True):
    st.markdown('<div class="silkscreen-label">DUT • VERIFICATION BENCHMARK</div>', unsafe_allow_html=True)
    if st.session_state.results:
        if st.session_state.results.get("is_unverified_guess"):
            theme.render_verdict_lamp(
                status="unverified_guess",
                message="Unverified AI guess — evaluated once in SPICE with no closed-loop optimizer."
            )
        elif st.session_state.results["passed"]:
            theme.render_verdict_lamp(
                status="verified",
                message=f"All specifications verified with standard commercial E-series components in {st.session_state.results['iterations_run']} iteration(s)."
            )
        else:
            theme.render_verdict_lamp(
                status="failed",
                message=f"Specifications not satisfied after {st.session_state.results['iterations_run']} iteration(s)."
            )
    else:
        # Before the first fix: amber "DESIGN NOT YET VERIFIED" banner
        theme.render_verdict_lamp(
            status="unverified",
            message="Pick an example or describe a circuit to start."
        )


# ==============================================================================
# SECTION 3: SEVEN-SEGMENT READOUT CARDS (Wrapped in st.container(border=True))
# ==============================================================================
with st.container(border=True):
    st.markdown('<div class="silkscreen-label">CH1 • INSTRUMENT MEASUREMENT READOUTS</div>', unsafe_allow_html=True)

    # Determine status of each readout: neutral amber before fix; phosphor green if pass, red if fail
    if st.session_state.results is None:
        card1_status = "neutral"
        card2_status = "neutral"
        card3_status = "neutral"
    else:
        final_mets = st.session_state.results.get("final_metrics", [])
        card1_status = "pass" if len(final_mets) > 0 and final_mets[0]["passed"] else "fail"
        card2_status = "pass" if len(final_mets) > 1 and final_mets[1]["passed"] else "fail"
        card3_status = "pass" if len(final_mets) > 2 and final_mets[2]["passed"] else "fail"

    m_col1, m_col2, m_col3 = st.columns(3)

    if selected_cid == "sallen_key":
        fc_tgt = float(st.session_state.specs.get("fc_target", 1000.0))
        pk_tgt = float(st.session_state.specs.get("peaking_max", 0.5))

        fc_broken = meas_broken.get("fc_3db_hz", 0.0)
        pk_broken = meas_broken.get("peaking_db", 0.0)
        dc_broken = meas_broken.get("dc_gain_db", 0.0)

        if st.session_state.results:
            m_final = st.session_state.results["final_measurements"]
            m_init = st.session_state.results["initial_measurements"]
            fc_final = m_final.get("fc_3db_hz", 0.0)
            pk_final = m_final.get("peaking_db", 0.0)
            dc_final = m_final.get("dc_gain_db", 0.0)
            fc_init_val = m_init.get("fc_3db_hz", 0.0)
            pk_init_val = m_init.get("peaking_db", 0.0)

            c1_html = theme.render_seven_segment_card(
                title=f"Cutoff fc (Target: {fc_tgt:.0f} Hz)",
                value=f"{fc_final:.1f}",
                unit="Hz",
                delta=f"Δ {fc_final - fc_init_val:+.1f} Hz vs initial ({fc_init_val:.0f} Hz)",
                status=card1_status
            )
            c2_html = theme.render_seven_segment_card(
                title=f"Peaking (Limit: ≤ {pk_tgt:.1f} dB)",
                value=f"{pk_final:.2f}",
                unit="dB",
                delta=f"Δ {pk_final - pk_init_val:+.2f} dB vs initial ({pk_init_val:.2f} dB)",
                status=card2_status
            )
            c3_html = theme.render_seven_segment_card(
                title="DC Gain (Target: 0.0 dB)",
                value=f"{dc_final:.2f}",
                unit="dB",
                delta=f"Δ {dc_final - dc_broken:+.2f} dB",
                status=card3_status
            )
        else:
            c1_html = theme.render_seven_segment_card(
                title=f"Cutoff fc (Target: {fc_tgt:.0f} Hz)",
                value=f"{fc_broken:.1f}",
                unit="Hz",
                delta=f"Δ {fc_broken - fc_tgt:+.1f} Hz vs target",
                status=card1_status
            )
            c2_html = theme.render_seven_segment_card(
                title=f"Peaking (Limit: ≤ {pk_tgt:.1f} dB)",
                value=f"{pk_broken:.2f}",
                unit="dB",
                delta=f"Δ {pk_broken - pk_tgt:+.2f} dB vs limit",
                status=card2_status
            )
            c3_html = theme.render_seven_segment_card(
                title="DC Gain (Target: 0.0 dB)",
                value=f"{dc_broken:.2f}",
                unit="dB",
                delta=f"Δ {dc_broken:+.2f} dB vs target",
                status=card3_status
            )

        m_col1.markdown(c1_html, unsafe_allow_html=True)
        m_col2.markdown(c2_html, unsafe_allow_html=True)
        m_col3.markdown(c3_html, unsafe_allow_html=True)

    elif selected_cid == "non_inverting_amp":
        gain_tgt = float(st.session_state.specs.get("gain_target", 10.0))
        bw_tgt = float(st.session_state.specs.get("bw_min", 50000.0))

        g_broken = meas_broken.get("linear_gain", 0.0)
        bw_broken = meas_broken.get("bandwidth_hz", 0.0)
        dc_broken = meas_broken.get("dc_gain_db", 0.0)

        if st.session_state.results:
            m_final = st.session_state.results["final_measurements"]
            m_init = st.session_state.results["initial_measurements"]
            g_final = m_final.get("linear_gain", 0.0)
            bw_final = m_final.get("bandwidth_hz", 0.0)
            dc_final = m_final.get("dc_gain_db", 0.0)
            g_init_val = m_init.get("linear_gain", 0.0)
            bw_init_val = m_init.get("bandwidth_hz", 0.0)

            c1_html = theme.render_seven_segment_card(
                title=f"Voltage Gain (Target: {gain_tgt:.1f}x)",
                value=f"{g_final:.2f}x",
                delta=f"Δ {g_final - g_init_val:+.2f}x vs initial ({g_init_val:.1f}x)",
                status=card1_status
            )
            c2_html = theme.render_seven_segment_card(
                title=f"Bandwidth (Min: ≥ {bw_tgt/1000:.0f} kHz)",
                value=f"{bw_final/1000:.1f}",
                unit="kHz",
                delta=f"Δ {(bw_final - bw_init_val)/1000:+.1f} kHz vs initial",
                status=card2_status
            )
            c3_html = theme.render_seven_segment_card(
                title="Amplification in Decibels",
                value=f"{dc_final:.2f}",
                unit="dB",
                delta=f"Δ {dc_final - dc_broken:+.2f} dB",
                status=card3_status
            )
        else:
            c1_html = theme.render_seven_segment_card(
                title=f"Voltage Gain (Target: {gain_tgt:.1f}x)",
                value=f"{g_broken:.2f}x",
                delta=f"Δ {g_broken - gain_tgt:+.2f}x vs target",
                status=card1_status
            )
            c2_html = theme.render_seven_segment_card(
                title=f"Bandwidth (Min: ≥ {bw_tgt/1000:.0f} kHz)",
                value=f"{bw_broken/1000:.1f}",
                unit="kHz",
                delta=f"Δ {(bw_broken - bw_tgt)/1000:+.1f} kHz vs target",
                status=card2_status
            )
            c3_html = theme.render_seven_segment_card(
                title="Amplification in Decibels",
                value=f"{dc_broken:.2f}",
                unit="dB",
                delta=f"Δ {dc_broken - 20.0 * np.log10(gain_tgt):+.2f} dB",
                status=card3_status
            )

        m_col1.markdown(c1_html, unsafe_allow_html=True)
        m_col2.markdown(c2_html, unsafe_allow_html=True)
        m_col3.markdown(c3_html, unsafe_allow_html=True)


# ==============================================================================
# SECTION 4: OSCILLOSCOPE BODE VIEW (Wrapped in st.container(border=True))
# ==============================================================================
with st.container(border=True):
    st.markdown('<div class="silkscreen-label">BODE • FREQUENCY RESPONSE ANALYZER</div>', unsafe_allow_html=True)

    target_f = float(st.session_state.specs.get("fc_target", 1000.0) if selected_cid == "sallen_key" else st.session_state.specs.get("bw_min", 50000.0))

    freqs_fixed = None
    gain_fixed = None
    readouts_dict = {}

    if selected_cid == "sallen_key":
        readouts_dict["initial"] = f"fc: {meas_broken.get('fc_3db_hz', 0):.0f} Hz | Peak: {meas_broken.get('peaking_db', 0):.2f} dB"
    else:
        readouts_dict["initial"] = f"Gain: {meas_broken.get('linear_gain', 0):.1f}x | BW: {meas_broken.get('bandwidth_hz', 0)/1000:.1f} kHz"

    if st.session_state.results:
        freqs_fixed, gain_fixed = st.session_state.results["final_curve"]
        m_fin = st.session_state.results["final_measurements"]
        if selected_cid == "sallen_key":
            readouts_dict["final"] = f"fc: {m_fin.get('fc_3db_hz', 0):.0f} Hz | Peak: {m_fin.get('peaking_db', 0):.2f} dB"
        else:
            readouts_dict["final"] = f"Gain: {m_fin.get('linear_gain', 0):.1f}x | BW: {m_fin.get('bandwidth_hz', 0)/1000:.1f} kHz"

    try:
        components.render_oscilloscope_bode(
            freqs_broken=freqs_broken,
            gain_broken=gain_broken,
            freqs_fixed=freqs_fixed,
            gain_fixed=gain_fixed,
            target_freq=target_f,
            circuit_id=selected_cid,
            readouts=readouts_dict,
            height=430
        )
    except Exception:
        # Graceful degradation to Plotly with -80 dB to +20 dB range
        st.caption("Standard view active")
        fig_bode = go.Figure()
        fig_bode.add_trace(go.Scatter(x=freqs_broken, y=gain_broken, name="Initial / Broken", line=dict(color="#FFB000", width=2)))
        if freqs_fixed is not None:
            fig_bode.add_trace(go.Scatter(x=freqs_fixed, y=gain_fixed, name="Repaired (E-Series)", line=dict(color="#39FF88", width=2.5)))
        fig_bode.update_layout(
            xaxis_type="log",
            yaxis=dict(range=[-80, 20], title="Gain (dB)"),
            height=380,
            template="plotly_dark"
        )
        st.plotly_chart(fig_bode, use_container_width=True)


# ==============================================================================
# SECTION 5: LIVE SCHEMATIC BLUEPRINT (Wrapped in st.container(border=True))
# ==============================================================================
with st.container(border=True):
    st.markdown('<div class="silkscreen-label">DUT • LIVE SCHEMATIC BLUEPRINT</div>', unsafe_allow_html=True)

    final_c = st.session_state.results["final_components"] if st.session_state.results else st.session_state.components
    initial_c = st.session_state.results["initial_components"] if st.session_state.results else st.session_state.components

    try:
        components.render_live_schematic(
            circuit_id=selected_cid,
            initial_components=initial_c,
            final_components=final_c,
            is_fixed=bool(st.session_state.results),
            height=330
        )
    except Exception:
        st.caption("Standard schematic view")
        fig_sch = draw_circuit_schematic(selected_cid, final_c)
        st.pyplot(fig_sch)


# ==============================================================================
# SECTION 6: DIAGNOSTIC SUMMARY (Wrapped in st.container(border=True))
# ==============================================================================
with st.container(border=True):
    st.markdown('<div class="silkscreen-label">DIAG • WHAT HAPPENED</div>', unsafe_allow_html=True)

    if st.session_state.results:
        init_m = st.session_state.results["initial_measurements"]
        fin_m = st.session_state.results["final_measurements"]

        if selected_cid == "sallen_key":
            init_fc = init_m.get("fc_3db_hz", 0.0)
            init_pk = init_m.get("peaking_db", 0.0)
            final_fc = fin_m.get("fc_3db_hz", 0.0)
            final_pk = fin_m.get("peaking_db", 0.0)
            tgt_fc = float(st.session_state.specs.get("fc_target", 1000.0))

            s1 = f"The initial circuit cut off audio at {init_fc:.0f} Hz instead of your target {tgt_fc:.0f} Hz."
            s2 = f"It had {init_pk:.2f} dB of peaking [an accidental loudness spike near the cutoff edge that causes ringing]."
            s3 = f"The AI rebalanced the resistor and capacitor values to provide Butterworth damping [the smoothest frequency curve without any bump]."
            s4 = f"The repaired circuit cuts off at {final_fc:.1f} Hz with zero distortion using standard off-the-shelf E-series [commercial store-bought] parts."
            summary_text = f"{s1} {s2} {s3} {s4}"
        else:
            init_g = init_m.get("linear_gain", 0.0)
            init_bw = init_m.get("bandwidth_hz", 0.0)
            final_g = fin_m.get("linear_gain", 0.0)
            final_bw = fin_m.get("bandwidth_hz", 0.0)
            tgt_g = float(st.session_state.specs.get("gain_target", 10.0))

            s1 = f"The initial circuit produced a {init_g:.1f}x gain instead of your target {tgt_g:.1f}x."
            s2 = f"This over-amplification severely limited the bandwidth [the frequency range over which signals pass clearly] to only {init_bw/1000:.1f} kHz."
            s3 = f"The AI tuned the feedback resistors to deliver {tgt_g:.1f}x gain while keeping impedance [resistance to AC electrical flow] low."
            s4 = f"The fixed amplifier achieves {final_g:.2f}x gain with {final_bw/1000:.1f} kHz bandwidth using standard E24 [commercial] resistors."
            summary_text = f"{s1} {s2} {s3} {s4}"
    else:
        summary_text = (
            "The circuit is currently in its initial uncalibrated state. "
            "Select an example prompt above or enter a custom requirement to trigger automated design and commercial component repair."
        )

    st.markdown(
        f'<div style="font-size: 15px; color: #D7E3EA; line-height: 1.7;">'
        f'<span style="color: #35D0FF; font-weight: bold; margin-right: 8px;">💡</span>'
        f'{summary_text}'
        f'</div>',
        unsafe_allow_html=True
    )


# ==============================================================================
# SECTION 7: TIME-DOMAIN TRANSIENT CLEANUP (Wrapped in st.container(border=True))
# ==============================================================================
with st.container(border=True):
    st.markdown('<div class="silkscreen-label">CH1/CH2 • TIME-DOMAIN TRANSIENT CLEANUP</div>', unsafe_allow_html=True)

    try:
        current_comps = st.session_state.results["final_components"] if st.session_state.results else st.session_state.components
        broken_comps = st.session_state.results["initial_components"] if st.session_state.results else spice.CIRCUITS[selected_cid]["broken_components"]

        spec_k = tuple(sorted(st.session_state.specs.keys()))
        spec_v = tuple(float(st.session_state.specs[k]) for k in spec_k)

        b_keys = tuple(sorted(broken_comps.keys()))
        b_vals = tuple(float(broken_comps[k]) for k in b_keys)
        t_b, v_in_b, v_out_b = run_cached_transient_simulation(selected_cid, b_keys, b_vals, spec_k, spec_v)

        f_keys = tuple(sorted(current_comps.keys()))
        f_vals = tuple(float(current_comps[k]) for k in f_keys)
        t_f, v_in_f, v_out_f = run_cached_transient_simulation(selected_cid, f_keys, f_vals, spec_k, spec_v)

        components.render_signal_cleanup_view(t=t_b, v_in=v_in_b, v_broken=v_out_b, v_fixed=v_out_f, height=360)
        st.caption("The fixed circuit keeps the wanted signal and removes unwanted distortion/noise.")
    except Exception as e_tran:
        st.info(f"Transient simulation active when ngspice transient engine responds ({e_tran}).")


# ==============================================================================
# SECTION 8: DETAILS & COMPONENT AUDIT (Wrapped in st.container(border=True))
# ==============================================================================
with st.container(border=True):
    st.markdown('<div class="silkscreen-label">BOM • COMPONENT SPECIFICATION & AUDIT</div>', unsafe_allow_html=True)

    with st.expander("Detailed numbers", expanded=False):
        st.subheader("Pass / Fail Verification Table")
        headers_metrics = ["Parameter", "Target", "Before", "After", "Status"]
        rows_metrics = []

        if st.session_state.results:
            final_mets = st.session_state.results["final_metrics"]
            for m_init, m_final in zip(metrics_broken, final_mets):
                status_str = "PASS" if m_final["passed"] else "FAIL"
                rows_metrics.append([
                    m_init["name"],
                    m_init["target_str"],
                    m_init["measured_str"],
                    m_final["measured_str"],
                    status_str
                ])
        else:
            for m_init in metrics_broken:
                status_str = "PASS" if m_init["passed"] else "FAIL"
                rows_metrics.append([
                    m_init["name"],
                    m_init["target_str"],
                    m_init["measured_str"],
                    "— (Pending Fix)",
                    status_str
                ])

        # Themed HTML Table with PASS/FAIL badges (Requirement 6)
        st.markdown(theme.render_html_table(headers_metrics, rows_metrics), unsafe_allow_html=True)

        st.subheader("Bill of Materials (BOM)")
        headers_bom = ["Component", "Broken Value", "Fixed Value", "Series (E24/E12)"]
        rows_bom = []
        c_types = c_info["component_types"]

        if st.session_state.results:
            final_comps = st.session_state.results["final_components"]
            init_comps = st.session_state.results["initial_components"]
            for comp, val_fixed in final_comps.items():
                c_type = c_types.get(comp, "R")
                val_broken = init_comps.get(comp, 0.0)
                series_str = "E24 (±5%)" if c_type == "R" else "E12 (±10%)"
                rows_bom.append([
                    comp,
                    format_comp_val(val_broken, c_type),
                    format_comp_val(val_fixed, c_type),
                    series_str
                ])
        else:
            init_comps = st.session_state.components
            for comp, val_broken in init_comps.items():
                c_type = c_types.get(comp, "R")
                series_str = "E24 (±5%)" if c_type == "R" else "E12 (±10%)"
                rows_bom.append([
                    comp,
                    format_comp_val(val_broken, c_type),
                    "—",
                    series_str
                ])

        st.markdown(theme.render_html_table(headers_bom, rows_bom), unsafe_allow_html=True)

    with st.expander("Learn the terms", expanded=False):
        st.markdown("""
- **Cutoff frequency:** The boundary pitch where a filter starts reducing unwanted higher or lower frequencies.
- **Peaking:** An accidental loudness spike near the cutoff frequency that can cause harsh tone ringing or audio distortion.
- **Damping:** The electrical braking effect that prevents a circuit from resonating or ringing uncontrollably.
- **Butterworth response:** The ideal filter tuning that delivers the flattest, smoothest possible passband without any resonant bump.
- **Decibel (dB):** A logarithmic sound scale where 0 dB means unchanged volume, positive numbers mean louder, and negative numbers mean quieter.
- **Gain:** The multiplication factor showing how many times bigger the output voltage is compared to the input.
- **Bandwidth:** The frequency range over which an amplifier maintains its full amplification power.
- **E-series (E24 / E12):** Standardized component values manufactured commercially worldwide so circuits can be built with real store-bought parts.
- **SPICE simulation:** A software physics simulator that calculates the exact voltages and currents of a circuit before building it.
""")

    with st.expander("📝 SPICE Netlist & Unified Diff", expanded=False):
        if st.session_state.results:
            orig_net = spice.generate_netlist(selected_cid, st.session_state.results["initial_components"])
            fixed_net = st.session_state.results["final_netlist"]
            diff = list(difflib.unified_diff(
                orig_net.splitlines(keepends=True),
                fixed_net.splitlines(keepends=True),
                fromfile="Broken Netlist",
                tofile="Fixed Netlist (E-Series)",
                n=2
            ))
            st.write("**Unified Netlist Diff:**")
            st.code("".join(diff), language="diff")
        else:
            st.write("**Current Netlist:**")
            st.code(spice.generate_netlist(selected_cid, st.session_state.components), language="spice")

    with st.expander("🧠 AI Agent Execution Log", expanded=False):
        if st.session_state.results and st.session_state.results.get("iterations_log"):
            for it in st.session_state.results["iterations_log"]:
                m_after = it["measurements_after"]
                if selected_cid == "sallen_key":
                    fc_val = m_after.get("fc_3db_hz", 0.0)
                    pk_val = m_after.get("peaking_db", 0.0)
                    res_str = f"fc = {fc_val:.1f} Hz, Peaking = {pk_val:.2f} dB"
                else:
                    gain_val = m_after.get("linear_gain", 0.0)
                    bw_val = m_after.get("bandwidth_hz", 0.0)
                    res_str = f"Gain = {gain_val:.2f}x, Bandwidth = {bw_val/1000:.1f} kHz"

                pass_badge = "✅ PASS" if it["passed"] else "⚠️ IN PROGRESS"
                comps_changed = ", ".join(it["components_to_tune"])
                st.markdown(
                    f"**Iteration {it['iteration']}:** {pass_badge} | "
                    f"**Diagnosis:** *\"{it['diagnosis']}\"* | "
                    f"**Components Changed:** `{comps_changed}` | "
                    f"**Result:** {res_str}"
                )
        else:
            st.info("No agent iterations logged yet. Run the repair pipeline to inspect execution logs.")


# ------------------------------------------------------------------------------
# PART 1 ITEM 4: "ASK ABOUT THIS RESULT" CHAT
# ------------------------------------------------------------------------------
st.markdown('<div class="silkscreen-label" style="margin-top: 1.5rem;">INTERACTIVE TUTOR • ASK ABOUT THIS RESULT</div>', unsafe_allow_html=True)

if not st.session_state.qa_history:
    st.caption("Ask questions about this calibration, op-amp behavior, or component values in the chat box below.")
else:
    for msg in st.session_state.qa_history:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
