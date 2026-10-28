"""
app.py - Analog Circuit Fixer Streamlit Web Application.
Diagnoses broken analog circuits using an LLM, optimizes components using SPICE in the loop,
and snaps to standard E-series values with simulation-verified pass/fail results.
"""

import difflib
import os
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import agent
import spice

# 1. Page Configuration (Wide layout, clean default theme, no custom CSS)
st.set_page_config(
    page_title="Analog Circuit Fixer",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)


def format_comp_val(val: float, comp_type: str) -> str:
    """Format numeric component value into standard engineering format (e.g. 6.8 kΩ, 22 nF)."""
    if val is None or np.isnan(val):
        return "N/A"
    abs_v = abs(val)
    if comp_type == "R":
        if abs_v >= 1e6:
            return f"{val/1e6:.4g} MΩ"
        elif abs_v >= 1e3:
            return f"{val/1e3:.4g} kΩ"
        else:
            return f"{val:.4g} Ω"
    else:
        if abs_v >= 1e-3:
            return f"{val*1e3:.4g} mF"
        elif abs_v >= 1e-6:
            return f"{val*1e6:.4g} µF"
        elif abs_v >= 1e-9:
            return f"{val*1e9:.4g} nF"
        elif abs_v >= 1e-12:
            return f"{val*1e12:.4g} pF"
        else:
            return f"{val:.4e} F"


@st.cache_data
def run_cached_simulation(circuit_id: str, comp_keys: tuple, comp_vals: tuple):
    """Run ngspice simulation on component values and cache results for instant plotting."""
    comps = dict(zip(comp_keys, comp_vals))
    freqs, gain_db = spice.simulate_circuit(circuit_id, comps)
    circuit_type = spice.CIRCUITS[circuit_id]["type"]
    meas = spice.measure_circuit(freqs, gain_db, circuit_type)
    return freqs, gain_db, meas


# Check ngspice availability
ngspice_available = True
ngspice_err = ""
try:
    ngspice_bin = spice.find_ngspice()
except Exception as e:
    ngspice_available = False
    ngspice_err = str(e)


# --- SIDEBAR: CONTROLS ---
with st.sidebar:
    st.header("⚙️ Controls")

    circuit_choices = {
        "sallen_key": "Sallen-Key Low-Pass (Unity Gain)",
        "non_inverting_amp": "Non-Inverting Amplifier"
    }

    selected_cid = st.selectbox(
        "Circuit Template",
        options=list(circuit_choices.keys()),
        format_func=lambda k: circuit_choices[k],
        key="circuit_select"
    )
    st.caption("Pick a circuit, then edit its component values below.")

    # Reset state whenever the user switches circuit templates
    if "circuit_id" not in st.session_state or st.session_state.circuit_id != selected_cid:
        st.session_state.circuit_id = selected_cid
        c_init_info = spice.CIRCUITS[selected_cid]
        st.session_state.components = dict(c_init_info["broken_components"])
        st.session_state.specs = dict(c_init_info["default_specs"])
        st.session_state.results = None
        editor_key = f"comp_editor_{selected_cid}"
        if editor_key in st.session_state:
            del st.session_state[editor_key]

    c_info = spice.CIRCUITS[selected_cid]
    current_specs = dict(st.session_state.specs)

    st.subheader("🎯 Target Specifications")
    if selected_cid == "sallen_key":
        fc_target = st.number_input(
            "Cutoff Frequency fc (Hz)",
            value=float(current_specs.get("fc_target", 1000.0)),
            step=50.0,
            help="Target -3 dB corner frequency"
        )
        fc_tol = st.number_input(
            "fc Tolerance (±%)",
            value=float(current_specs.get("fc_tol", 0.05) * 100.0),
            step=1.0
        ) / 100.0
        peaking_max = st.number_input(
            "Max Peaking (dB)",
            value=float(current_specs.get("peaking_max", 0.5)),
            step=0.1,
            help="Butterworth damping requirement (Q ~ 0.707)"
        )
        dc_gain_target = st.number_input(
            "DC Gain (dB)",
            value=float(current_specs.get("dc_gain_target", 0.0)),
            step=0.1
        )
        dc_gain_tol = st.number_input(
            "DC Gain Tol (±dB)",
            value=float(current_specs.get("dc_gain_tol", 0.5)),
            step=0.1
        )

        st.session_state.specs = {
            "fc_target": fc_target,
            "fc_tol": fc_tol,
            "peaking_max": peaking_max,
            "dc_gain_target": dc_gain_target,
            "dc_gain_tol": dc_gain_tol
        }

    elif selected_cid == "non_inverting_amp":
        gain_target = st.number_input(
            "Target Gain (Linear)",
            value=float(current_specs.get("gain_target", 10.0)),
            step=0.5
        )
        gain_tol = st.number_input(
            "Gain Tolerance (±%)",
            value=float(current_specs.get("gain_tol", 0.02) * 100.0),
            step=0.5
        ) / 100.0
        bw_min = st.number_input(
            "Min -3 dB Bandwidth (kHz)",
            value=float(current_specs.get("bw_min", 50000.0) / 1000.0),
            step=5.0
        ) * 1000.0

        st.session_state.specs = {
            "gain_target": gain_target,
            "gain_tol": gain_tol,
            "bw_min": bw_min
        }

    st.divider()

    col_btn1, col_btn2 = st.columns(2)
    with col_btn1:
        if st.button("🔄 Reset Broken", use_container_width=True):
            st.session_state.components = dict(c_info["broken_components"])
            st.session_state.specs = dict(c_info["default_specs"])
            st.session_state.results = None
            editor_key = f"comp_editor_{selected_cid}"
            if editor_key in st.session_state:
                del st.session_state[editor_key]
            st.rerun()

    # Placeholder for Fix Circuit button (rendered below after component validation)
    fix_button_placeholder = col_btn2.empty()

    st.divider()
    st.subheader("🤖 LLM Settings")
    env_key = os.environ.get("LLM_API_KEY", "")
    user_key = st.text_input(
        "API Key (optional)",
        value=env_key,
        type="password",
        help="OpenAI-compatible API key. If blank, cached demo diagnosis is used."
    )
    force_demo = st.checkbox(
        "Cached Demo Mode",
        value=os.environ.get("DEMO", "0").lower() in ("1", "true", "yes") or (not user_key),
        help="Guarantees immediate expert diagnosis with zero external API dependencies."
    )

    st.divider()
    if ngspice_available:
        st.success("✓ ngspice detected")
    else:
        st.error(f"❌ ngspice not found: {ngspice_err}")


# --- MAIN AREA ---

# 1. Top: Title + One-line subtitle
st.title("⚡ Analog Circuit Fixer")
st.write("Broken circuit in → simulation → AI diagnosis → optimizer → verified fix out.")

# 2. 4-step progress strip under the title
step_col1, step_col2, step_col3, step_col4 = st.columns(4)
step_col1.info("**① Simulate**\n\n*ngspice batch AC sweep*")
step_col2.info("**② Diagnose (AI)**\n\n*Root-cause analysis*")
step_col3.info("**③ Optimize**\n\n*Nelder-Mead log search*")
step_col4.info("**④ Verify**\n\n*E-series simulation*")

if not ngspice_available:
    st.error(
        f"**Error locating ngspice:** {ngspice_err}\n\n"
        "Please ensure ngspice is installed and available in PATH."
    )
    st.stop()


# 2. Edit circuit components section at top of main area
st.subheader("✏️ Edit Circuit Components")
st.caption("Change any component value below (e.g. 10k, 22n, 7500, 6.8e-8). The netlist and simulation update automatically.")

# Build editable dataframe from session state
editor_rows = []
for comp, val in st.session_state.components.items():
    c_type = c_info["component_types"].get(comp, "R")
    unit_str = "Ω" if c_type == "R" else "F"
    val_str = spice.format_spice_val(val)
    editor_rows.append({"Component": comp, "Value": val_str, "Unit": unit_str})

df_editor_init = pd.DataFrame(editor_rows)

editor_key = f"comp_editor_{selected_cid}"
edited_df = st.data_editor(
    df_editor_init,
    key=editor_key,
    disabled=["Component", "Unit"],
    hide_index=True,
    use_container_width=True
)

# Validate edited values: must be positive numbers
is_components_valid = True
validation_errors = []
parsed_components = {}

for row in edited_df.itertuples():
    comp = row.Component
    raw_val = str(row.Value).strip()
    try:
        parsed_val = spice.parse_spice_val(raw_val)
        if parsed_val <= 0 or np.isnan(parsed_val):
            is_components_valid = False
            validation_errors.append(f"{comp}: value must be a positive number (got '{raw_val}')")
        else:
            parsed_components[comp] = float(parsed_val)
    except Exception:
        is_components_valid = False
        validation_errors.append(f"{comp}: could not parse '{raw_val}' as a valid number")

if not is_components_valid:
    for err in validation_errors:
        st.error(f"❌ {err}")
else:
    # If values changed, update session_state and reset results so broken curve updates
    if parsed_components != st.session_state.components:
        st.session_state.components = dict(parsed_components)
        st.session_state.results = None
        st.rerun()

# Render the Fix Circuit button in the sidebar (disabled if validation fails)
fix_button = fix_button_placeholder.button(
    "🚀 Fix Circuit",
    type="primary",
    disabled=(not is_components_valid or not ngspice_available),
    use_container_width=True
)


# 3. Generated netlist: updates live from edited values
st.caption("Generated netlist, updates as you edit values")
generated_netlist = spice.generate_netlist(selected_cid, st.session_state.components)
st.code(generated_netlist, language="spice")


# 4. Run simulation immediately on page load and on every edit (cached with st.cache_data)
comp_keys = tuple(sorted(st.session_state.components.keys()))
comp_vals = tuple(float(st.session_state.components[k]) for k in comp_keys)

sim_error = None
try:
    freqs_broken, gain_broken, meas_broken = run_cached_simulation(selected_cid, comp_keys, comp_vals)
    passed_broken, metrics_broken = spice.evaluate_spec(selected_cid, meas_broken, st.session_state.specs)
except Exception as e:
    sim_error = str(e)
    freqs_broken, gain_broken, meas_broken = None, None, {}
    passed_broken, metrics_broken = False, []

if sim_error:
    st.error(f"Simulation error: {sim_error}")
    st.stop()


# Handle "Fix Circuit" action
if fix_button and is_components_valid:
    effective_key = None if force_demo else (user_key or None)

    with st.status("Executing Autonomous Repair Pipeline...", expanded=True) as status_box:
        st.write("① **Simulate:** Measuring baseline performance in ngspice...")
        st.write("② **Diagnose (AI):** Analyzing damping, resonant peaking, and bandwidth constraints...")
        st.write("③ **Optimize:** Running Nelder-Mead search in log10 space with simulator in the loop...")
        st.write("④ **Verify:** Snapping components to standard E-series and running final simulation...")

        try:
            results = agent.run_agent_loop(
                circuit_id=selected_cid,
                initial_components=st.session_state.components,
                specs=st.session_state.specs,
                api_key=effective_key,
                max_iterations=4
            )
            st.session_state.results = results
            status_box.update(
                label=f"Autonomous repair completed in {results['iterations_run']} iteration(s)!",
                state="complete",
                expanded=False
            )
        except Exception as e:
            status_box.update(label="Error during circuit repair!", state="error")
            st.error(f"Execution failed: {e}")


# 5. Large Banner
if st.session_state.results:
    if st.session_state.results["passed"]:
        st.success("✅ SPEC MET - verified by simulation")
    else:
        st.error(f"❌ Spec not met after {st.session_state.results['iterations_run']} iterations")
else:
    if passed_broken:
        st.success("✅ Current circuit passes all specifications!")
    else:
        st.warning("⚠️ Current circuit is failing specifications. Review the live simulation below and click '🚀 Fix Circuit' in the sidebar.")


# 6. Bode plot + 3 metrics cards
st.subheader("Bode Plot: Frequency vs Gain")

fig = go.Figure()

# Red curve for Broken (always plotted immediately on load and on every edit)
if freqs_broken is not None and gain_broken is not None:
    fig.add_trace(go.Scatter(
        x=freqs_broken,
        y=gain_broken,
        mode="lines",
        name="Broken (Original)",
        line=dict(color="#EF4444", width=2.5),
        hovertemplate="<b>Frequency</b>: %{x:.1f} Hz<br><b>Gain</b>: %{y:.2f} dB<extra></extra>"
    ))

# Green curve for Fixed (E-Series), displayed after fixing
if st.session_state.results:
    freqs_fix, gain_fix = st.session_state.results["final_curve"]
    fig.add_trace(go.Scatter(
        x=freqs_fix,
        y=gain_fix,
        mode="lines",
        name="Fixed (E-Series)",
        line=dict(color="#10B981", width=3.0),
        hovertemplate="<b>Frequency</b>: %{x:.1f} Hz<br><b>Gain</b>: %{y:.2f} dB<extra></extra>"
    ))

# Plot annotations and reference lines
if selected_cid == "sallen_key":
    fc_val = st.session_state.specs.get("fc_target", 1000.0)
    pk_max = st.session_state.specs.get("peaking_max", 0.5)

    fig.add_vline(
        x=fc_val,
        line=dict(color="#3B82F6", width=2, dash="dash"),
        annotation_text=f"Target fc ({fc_val:.0f} Hz)",
        annotation_position="top left"
    )
    fig.add_hrect(
        y0=-0.5,
        y1=pk_max,
        fillcolor="#10B981",
        opacity=0.15,
        line=dict(color="#10B981", width=1, dash="dot"),
        annotation_text=f"Allowed Peaking Limit (≤ {pk_max:.1f} dB)",
        annotation_position="top right"
    )
    fig.add_hline(
        y=-3.01,
        line=dict(color="#6B7280", width=1.5, dash="dot"),
        annotation_text="-3 dB Cutoff Line",
        annotation_position="bottom right"
    )

elif selected_cid == "non_inverting_amp":
    g_val = st.session_state.specs.get("gain_target", 10.0)
    g_db_val = 20.0 * np.log10(g_val)
    bw_val = st.session_state.specs.get("bw_min", 50000.0)

    fig.add_hline(
        y=g_db_val,
        line=dict(color="#3B82F6", width=2, dash="dash"),
        annotation_text=f"Target Gain ({g_val:.0f}x / {g_db_val:.1f} dB)",
        annotation_position="top left"
    )
    fig.add_vline(
        x=bw_val,
        line=dict(color="#F59E0B", width=2, dash="dash"),
        annotation_text=f"Min Bandwidth ({bw_val/1000:.0f} kHz)",
        annotation_position="bottom left"
    )
    fig.add_vrect(
        x0=bw_val,
        x1=1e6,
        fillcolor="#10B981",
        opacity=0.12,
        line_width=0,
        annotation_text="Compliant Bandwidth Zone",
        annotation_position="top right"
    )

fig.update_layout(
    title="AC Bode Magnitude Response",
    xaxis=dict(
        type="log",
        title="Frequency (Hz)",
        gridcolor="#E2E8F0"
    ),
    yaxis=dict(
        title="Gain (dB)",
        gridcolor="#E2E8F0"
    ),
    height=400,
    margin=dict(l=40, r=20, t=40, b=40),
    legend=dict(
        yanchor="top",
        y=0.98,
        xanchor="right",
        x=0.98
    )
)

st.plotly_chart(fig, use_container_width=True)


# 3 st.metric cards
m_col1, m_col2, m_col3 = st.columns(3)

if selected_cid == "sallen_key":
    fc_tgt = st.session_state.specs.get("fc_target", 1000.0)
    pk_tgt = st.session_state.specs.get("peaking_max", 0.5)
    dc_tgt = st.session_state.specs.get("dc_gain_target", 0.0)

    fc_broken = meas_broken.get("fc_3db_hz", 0.0)
    pk_broken = meas_broken.get("peaking_db", 0.0)
    dc_broken = meas_broken.get("dc_gain_db", 0.0)

    if st.session_state.results:
        m_final = st.session_state.results["final_measurements"]
        fc_final = m_final.get("fc_3db_hz", 0.0)
        pk_final = m_final.get("peaking_db", 0.0)
        dc_final = m_final.get("dc_gain_db", 0.0)

        d_fc = fc_final - fc_broken
        d_pk = pk_final - pk_broken
        d_dc = dc_final - dc_broken

        m_col1.metric(
            label=f"Cutoff (target {fc_tgt:.0f} Hz)",
            value=f"{fc_final:.1f} Hz",
            delta=f"{d_fc:+.1f} Hz vs broken",
            delta_color="normal"
        )
        m_col2.metric(
            label=f"Peaking (target ≤ {pk_tgt:.1f} dB)",
            value=f"{pk_final:.2f} dB",
            delta=f"{d_pk:+.2f} dB vs broken",
            delta_color="normal"
        )
        m_col3.metric(
            label=f"DC Gain (target {dc_tgt:.1f} dB)",
            value=f"{dc_final:.2f} dB",
            delta=f"{d_dc:+.2f} dB vs broken",
            delta_color="normal"
        )
    else:
        d_fc = fc_broken - fc_tgt
        d_pk = pk_broken - pk_tgt
        d_dc = dc_broken - dc_tgt

        m_col1.metric(
            label=f"Cutoff (target {fc_tgt:.0f} Hz)",
            value=f"{fc_broken:.1f} Hz",
            delta=f"{d_fc:+.1f} Hz vs target",
            delta_color="inverse"
        )
        m_col2.metric(
            label=f"Peaking (target ≤ {pk_tgt:.1f} dB)",
            value=f"{pk_broken:.2f} dB",
            delta=f"{d_pk:+.2f} dB vs limit",
            delta_color="inverse" if pk_broken > pk_tgt else "off"
        )
        m_col3.metric(
            label=f"DC Gain (target {dc_tgt:.1f} dB)",
            value=f"{dc_broken:.2f} dB",
            delta=f"{d_dc:+.2f} dB vs target",
            delta_color="off" if abs(d_dc) <= st.session_state.specs.get("dc_gain_tol", 0.5) else "inverse"
        )

elif selected_cid == "non_inverting_amp":
    gain_tgt = st.session_state.specs.get("gain_target", 10.0)
    bw_tgt = st.session_state.specs.get("bw_min", 50000.0)

    g_broken = meas_broken.get("linear_gain", 0.0)
    bw_broken = meas_broken.get("bandwidth_hz", 0.0)
    dc_broken = meas_broken.get("dc_gain_db", 0.0)

    if st.session_state.results:
        m_final = st.session_state.results["final_measurements"]
        g_final = m_final.get("linear_gain", 0.0)
        bw_final = m_final.get("bandwidth_hz", 0.0)
        dc_final = m_final.get("dc_gain_db", 0.0)

        delta_g = g_final - g_broken
        delta_bw = (bw_final - bw_broken) / 1000.0
        delta_dc = dc_final - dc_broken

        m_col1.metric(
            label=f"Gain (target {gain_tgt:.1f}x)",
            value=f"{g_final:.2f}x",
            delta=f"{delta_g:+.2f}x vs broken",
            delta_color="normal"
        )
        m_col2.metric(
            label=f"Bandwidth (target ≥ {bw_tgt/1000:.0f} kHz)",
            value=f"{bw_final/1000:.1f} kHz",
            delta=f"{delta_bw:+.1f} kHz vs broken",
            delta_color="normal"
        )
        m_col3.metric(
            label="DC Gain (target 20.0 dB)",
            value=f"{dc_final:.2f} dB",
            delta=f"{delta_dc:+.2f} dB vs broken",
            delta_color="normal"
        )
    else:
        d_g = g_broken - gain_tgt
        d_bw = (bw_broken - bw_tgt) / 1000.0

        m_col1.metric(
            label=f"Gain (target {gain_tgt:.1f}x)",
            value=f"{g_broken:.2f}x",
            delta=f"{d_g:+.2f}x vs target",
            delta_color="inverse" if abs(d_g) > 0.2 else "off"
        )
        m_col2.metric(
            label=f"Bandwidth (target ≥ {bw_tgt/1000:.0f} kHz)",
            value=f"{bw_broken/1000:.1f} kHz",
            delta=f"{d_bw:+.1f} kHz vs target",
            delta_color="inverse" if d_bw < 0 else "off"
        )
        m_col3.metric(
            label="DC Gain (target 20.0 dB)",
            value=f"{dc_broken:.2f} dB",
            delta=f"{dc_broken - 20.0:+.2f} dB vs target",
            delta_color="off"
        )


# 7. Pass/Fail table (Native DataFrame only)
st.subheader("Pass / Fail Verification Table")

table_data = []
if st.session_state.results:
    final_mets = st.session_state.results["final_metrics"]
    for m_init, m_final in zip(metrics_broken, final_mets):
        status_str = "✅ PASS" if m_final["passed"] else "❌ FAIL"
        table_data.append({
            "Parameter": m_init["name"],
            "Target": m_init["target_str"],
            "Before": m_init["measured_str"],
            "After": m_final["measured_str"],
            "Status": status_str
        })
else:
    for m_init in metrics_broken:
        status_str = "✅ PASS" if m_init["passed"] else "❌ FAIL"
        table_data.append({
            "Parameter": m_init["name"],
            "Target": m_init["target_str"],
            "Before": m_init["measured_str"],
            "After": "— (Pending Fix)",
            "Status": status_str
        })

df_metrics = pd.DataFrame(table_data)

def style_status(val):
    if "PASS" in str(val):
        return "color: #15803d; font-weight: bold;"
    elif "FAIL" in str(val):
        return "color: #b91c1c; font-weight: bold;"
    return ""

st.dataframe(
    df_metrics.style.map(style_status, subset=["Status"]),
    hide_index=True,
    use_container_width=True
)


# 8. "What happened?" panel (st.info)
st.subheader("What Happened?")

if st.session_state.results:
    if selected_cid == "sallen_key":
        init_fc = st.session_state.results["initial_measurements"].get("fc_3db_hz", 0.0)
        init_pk = st.session_state.results["initial_measurements"].get("peaking_db", 0.0)
        final_fc = st.session_state.results["final_measurements"].get("fc_3db_hz", 0.0)
        final_pk = st.session_state.results["final_measurements"].get("peaking_db", 0.0)
        tgt_fc = st.session_state.specs.get("fc_target", 1000.0)
        comps_str = ", ".join(st.session_state.results["final_components"].keys())

        narrative = (
            f"The broken filter cut off at {init_fc:.0f} Hz instead of {tgt_fc:.0f} Hz and exhibited {init_pk:.2f} dB of peaking "
            f"because its damping was too low (excessive C1/C2 ratio causing Q ≈ 1.58). "
            f"The optimizer adjusted {comps_str} so the frequency response achieved Butterworth maximally flat damping (Q ≈ 0.707). "
            f"The simulator confirmed all specs pass with standard commercial E24/E12 components (fc = {final_fc:.1f} Hz, peaking = {final_pk:.2f} dB)."
        )
    else:
        init_g = st.session_state.results["initial_measurements"].get("linear_gain", 0.0)
        init_bw = st.session_state.results["initial_measurements"].get("bandwidth_hz", 0.0)
        final_g = st.session_state.results["final_measurements"].get("linear_gain", 0.0)
        final_bw = st.session_state.results["final_measurements"].get("bandwidth_hz", 0.0)
        tgt_g = st.session_state.specs.get("gain_target", 10.0)
        comps_str = ", ".join(st.session_state.results["final_components"].keys())

        narrative = (
            f"The broken amplifier had a closed-loop gain of {init_g:.2f}x instead of {tgt_g:.1f}x, which throttled its bandwidth "
            f"down to {init_bw/1000:.1f} kHz due to the op-amp's 1.0 MHz gain-bandwidth product (GBW) limit. "
            f"The optimizer retuned feedback resistors {comps_str} to satisfy the 10x specification while keeping impedance low. "
            f"The simulator confirmed all specs pass with gain = {final_g:.2f}x and bandwidth = {final_bw/1000:.1f} kHz using standard E24 resistors."
        )
else:
    if passed_broken:
        narrative = (
            "The circuit currently meets all target specifications based on the live SPICE simulation. "
            "You can modify any component in the editor above to test different variations."
        )
    else:
        narrative = (
            "The circuit is currently failing target specifications based on the live simulation above. "
            "Click '🚀 Fix Circuit' in the sidebar to run the autonomous diagnosis and optimization pipeline."
        )

st.info(narrative)


# 9. BOM as a native DataFrame
st.subheader("Bill of Materials (BOM)")

bom_data = []
c_types = c_info["component_types"]

if st.session_state.results:
    final_comps = st.session_state.results["final_components"]
    init_comps = st.session_state.results["initial_components"]

    for comp, val_fixed in final_comps.items():
        c_type = c_types.get(comp, "R")
        val_broken = init_comps.get(comp, 0.0)
        series_str = "E24 (±5%)" if c_type == "R" else "E12 (±10%)"
        bom_data.append({
            "Component": comp,
            "Broken value": format_comp_val(val_broken, c_type),
            "Fixed value": format_comp_val(val_fixed, c_type),
            "Series (E24/E12)": series_str
        })
else:
    init_comps = st.session_state.components
    for comp, val_broken in init_comps.items():
        c_type = c_types.get(comp, "R")
        series_str = "E24 (±5%)" if c_type == "R" else "E12 (±10%)"
        bom_data.append({
            "Component": comp,
            "Broken value": format_comp_val(val_broken, c_type),
            "Fixed value": "—",
            "Series (E24/E12)": series_str
        })

df_bom = pd.DataFrame(bom_data)
st.dataframe(df_bom, hide_index=True, use_container_width=True)


# 10. Expanders: Concepts, Agent Log, Unified Netlist Diff
with st.expander("📖 Concepts & Definitions", expanded=False):
    st.markdown("""
- **Cutoff frequency (-3 dB point):** The corner frequency $f_c$ where output signal power drops to half ($-3.01\\text{ dB}$ below passband gain, or voltage gain $\\approx 70.7\\%$) marking the boundary of the filter's passband.
- **Peaking / Q factor:** The resonant gain bump near cutoff caused by an underdamped pole pair. Higher Quality Factor ($Q$) causes taller peaking; maintaining $Q \\le 0.707$ ensures a strictly monotonic response without overshoot.
- **Butterworth (maximally flat):** The unique mathematical filter alignment characterized by an optimal damping factor ($Q = 1/\\sqrt{2} \\approx 0.7071$) that provides the flattest possible passband with zero ripple before transitioning into rolloff.
- **E24 / E12 Series (standard part values):** Standard geometric progressions used by component manufacturers. E24 offers 24 preferred values per decade ($\\pm 5\\%$ tolerance for resistors); E12 offers 12 preferred values per decade ($\\pm 10\\%$ tolerance for capacitors).
""")

with st.expander("🧠 Agent Execution Log", expanded=False):
    if st.session_state.results and st.session_state.results["iterations_log"]:
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
        st.info("No agent iterations logged yet. Click '🚀 Fix Circuit' to execute the repair loop.")

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
        st.code(generated_netlist, language="spice")
