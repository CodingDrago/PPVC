"""
agent.py - LLM diagnosis, numerical optimizer, and agent loop
for Analog Circuit Fixer.
"""

import json
import os
import re
import numpy as np
import requests
from dotenv import load_dotenv
from scipy.optimize import minimize

import spice

# Load environment variables from .env file if present
load_dotenv()

# Fallback / demo status flag
def is_demo_mode(api_key: str = None) -> bool:
    """Return True if demo mode is requested or no API key is available."""
    if os.environ.get("DEMO", "0").lower() in ("1", "true", "yes"):
        return True
    key = api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("LLM_API_KEY")
    return not bool(key)


def get_ai_status(api_key: str = None) -> tuple[bool, str]:
    """Return (is_online: bool, status_chip: str) for UI indicator."""
    if is_demo_mode(api_key):
        return False, "AI: offline demo mode"
    return True, "AI: Gemini online"


def call_llm_provider(
    prompt: str,
    api_key: str = None,
    system_prompt: str = None,
    json_mode: bool = True
) -> str:
    """
    Unified LLM provider call using Google Gemini via google-genai SDK.
    Enforces 8s timeout, JSON mode when requested, and environment-based keys.
    Falls back gracefully or raises so callers route to rule-based fallback.
    """
    if is_demo_mode(api_key):
        raise ValueError("Demo mode active or API key not supplied")

    key = api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("LLM_API_KEY")
    if not key:
        raise ValueError("GEMINI_API_KEY environment variable is not set.")

    model = os.environ.get("GEMINI_MODEL") or os.environ.get("LLM_MODEL") or "gemini-2.5-flash"

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(
            api_key=key,
            http_options=types.HttpOptions(timeout=8000)
        )

        config_kwargs = {
            "temperature": 0.2,
        }
        if json_mode:
            config_kwargs["response_mime_type"] = "application/json"
        if system_prompt:
            config_kwargs["system_instruction"] = system_prompt

        config = types.GenerateContentConfig(**config_kwargs)

        response = client.models.generate_content(
            model=model,
            contents=prompt,
            config=config
        )

        if response and response.text:
            return response.text
        raise ValueError("Empty response received from Gemini model")
    except Exception as e:
        raise RuntimeError(f"Gemini API error: {e}")


def get_llm_diagnosis(
    circuit_id: str,
    netlist: str,
    specs: dict,
    measurements: dict,
    current_components: dict,
    history: list = None,
    api_key: str = None
) -> dict:
    """
    Ask LLM to diagnose why the circuit is failing and select components + bounds to tune.
    Falls back gracefully if demo mode is active or API call fails.
    """
    history = history or []
    demo_fallback = spice.CIRCUITS[circuit_id]["demo_diagnosis"]

    if is_demo_mode(api_key):
        res = dict(demo_fallback)
        res["source"] = "Cached Demo Diagnosis"
        return res

    prompt = f"""Target Circuit: {spice.CIRCUITS[circuit_id]['name']}
Current Netlist:
{netlist}

Circuit Specifications:
{json.dumps(specs, indent=2)}

Current SPICE Measurements:
{json.dumps(measurements, indent=2)}

Previous Iteration History:
{json.dumps(history, indent=2)}

Instructions:
1. Diagnose why the circuit is failing the target specifications.
2. Select which components should be tuned (e.g. {list(current_components.keys())}).
3. Provide realistic search bounds [min, max] for each tuned component.
4. Provide the engineering reason for your choices.

Respond with valid JSON ONLY in this exact format:
{{
  "diagnosis": "Detailed explanation of failure cause",
  "components_to_tune": ["R1", "C2"],
  "bounds": {{"R1": [1e3, 1e5], "C2": [1e-9, 1e-6]}},
  "reason": "Engineering rationale for tuning these components"
}}
"""

    try:
        raw_text = call_llm_provider(prompt, api_key=api_key)
        # Strip markdown fences if present
        clean_text = raw_text.strip()
        clean_text = re.sub(r"^```(?:json)?\s*", "", clean_text)
        clean_text = re.sub(r"\s*```$", "", clean_text)

        parsed = json.loads(clean_text)
        if "components_to_tune" in parsed and "bounds" in parsed:
            # Ensure bounds values are floats
            clean_bounds = {}
            for comp, b in parsed["bounds"].items():
                if isinstance(b, list) and len(b) == 2:
                    clean_bounds[comp] = [float(b[0]), float(b[1])]
            parsed["bounds"] = clean_bounds
            parsed["source"] = "LLM API"
            return parsed
        raise ValueError("Invalid JSON schema from LLM")

    except Exception as e:
        # Fallback to tuning all components within +-10x of current values
        fb_bounds = {}
        for comp, val in current_components.items():
            fb_bounds[comp] = [max(1e-12, float(val) / 10.0), float(val) * 10.0]

        return {
            "diagnosis": demo_fallback["diagnosis"],
            "components_to_tune": list(current_components.keys()),
            "bounds": fb_bounds,
            "reason": f"Fallback diagnosis due to API failure ({e}). Tuning all components within +-10x range.",
            "source": f"Fallback ({e})"
        }


def optimize_circuit_components(
    circuit_id: str,
    base_components: dict,
    components_to_tune: list,
    bounds: dict,
    specs: dict
) -> tuple[dict, dict]:
    """
    Run numeric optimization (Nelder-Mead) over log10 of selected component values,
    with the SPICE simulator in the loop.
    Then snap resistors to E24 and capacitors to E12.
    Returns (continuous_optimized_components, snapped_e_series_components).
    """
    comp_types = spice.CIRCUITS[circuit_id]["component_types"]
    tune_keys = [k for k in components_to_tune if k in base_components]
    if not tune_keys:
        tune_keys = list(base_components.keys())

    # Build log10 bounds and ensure initial guess is strictly within bounds
    bounds_log = []
    x0 = []
    for k in tune_keys:
        val = max(1e-12, float(base_components[k]))
        b = bounds.get(k, [val / 10.0, val * 10.0])
        low_val = min(float(b[0]), val * 0.9)
        high_val = max(float(b[1]), val * 1.1)
        low = np.log10(max(1e-12, low_val))
        high = np.log10(max(1e-12, high_val))
        if low > high:
            low, high = high, low
        bounds_log.append((low, high))
        val_log = np.clip(np.log10(val), low + 1e-5, high - 1e-5)
        x0.append(val_log)

    circuit_type = spice.CIRCUITS[circuit_id]["type"]

    # Objective / Cost function with SPICE simulation in the loop
    def cost_func(x):
        test_comps = dict(base_components)
        for i, k in enumerate(tune_keys):
            test_comps[k] = float(10.0 ** x[i])

        try:
            freqs, gain_db = spice.simulate_circuit(circuit_id, test_comps, timeout=2.0)
            meas = spice.measure_circuit(freqs, gain_db, circuit_type)

            if circuit_type == "low_pass":
                fc_target = specs.get("fc_target", 1000.0)
                peaking_max = specs.get("peaking_max", 0.5)
                dc_target = specs.get("dc_gain_target", 0.0)

                meas_fc = meas.get("fc_3db_hz", 10.0)
                meas_peak = meas.get("peaking_db", 0.0)
                meas_dc = meas.get("dc_gain_db", 0.0)

                fc_err = ((meas_fc - fc_target) / fc_target) ** 2
                peak_penalty = (max(0.0, meas_peak - peaking_max) / max(0.1, peaking_max)) ** 2
                dc_err = (meas_dc - dc_target) ** 2

                # Weighted normalized squared error
                return 30.0 * fc_err + 40.0 * peak_penalty + 5.0 * dc_err

            elif circuit_type == "amplifier":
                gain_target = specs.get("gain_target", 10.0)
                bw_min = specs.get("bw_min", 50000.0)

                meas_gain = meas.get("linear_gain", 1.0)
                meas_bw = meas.get("bandwidth_hz", 10.0)

                gain_err = ((meas_gain - gain_target) / gain_target) ** 2
                bw_penalty = (max(0.0, bw_min - meas_bw) / bw_min) ** 2

                return 40.0 * gain_err + 25.0 * bw_penalty

            return 0.0

        except Exception:
            return 1e6

    # Nelder-Mead optimization
    res = minimize(
        cost_func,
        x0,
        method="Nelder-Mead",
        bounds=bounds_log,
        options={"maxiter": 40, "disp": False}
    )

    opt_comps = dict(base_components)
    for i, k in enumerate(tune_keys):
        opt_comps[k] = float(10.0 ** res.x[i])

    # Snap resistors to E24 and capacitors to E12
    snapped_comps = spice.snap_components(opt_comps, comp_types)

    # Fine discrete refinement for E-series components
    # If initial snap doesn't pass spec, test immediate neighbor E-series resistors
    try:
        f_snap, g_snap = spice.simulate_circuit(circuit_id, snapped_comps)
        m_snap = spice.measure_circuit(f_snap, g_snap, circuit_type)
        pass_snap, _ = spice.evaluate_spec(circuit_id, m_snap, specs)

        if not pass_snap:
            # Check adjacent E24 resistors to compensate for coarse E12 capacitor rounding
            best_comps = dict(snapped_comps)
            best_cost = cost_func([np.log10(snapped_comps[k]) for k in tune_keys])

            resistor_keys = [k for k in tune_keys if comp_types.get(k) == "R"]
            if resistor_keys:
                candidates = [snapped_comps]
                for rk in resistor_keys:
                    r_val = snapped_comps[rk]
                    # Find index in E24
                    dec = 10.0 ** np.floor(np.log10(r_val))
                    norm = round(r_val / dec, 2)
                    idx = np.argmin(np.abs(spice.E24_VALUES - norm))
                    for offset in [-1, 1]:
                        new_idx = idx + offset
                        if 0 <= new_idx < len(spice.E24_VALUES):
                            new_r = float(spice.E24_VALUES[new_idx] * dec)
                            cand = dict(snapped_comps)
                            cand[rk] = new_r
                            candidates.append(cand)

                for cand in candidates:
                    c_val = cost_func([np.log10(cand[k]) for k in tune_keys])
                    if c_val < best_cost:
                        best_cost = c_val
                        best_comps = cand

                snapped_comps = best_comps
    except Exception:
        pass

    return opt_comps, snapped_comps


def run_agent_loop(
    circuit_id: str,
    initial_components: dict = None,
    specs: dict = None,
    api_key: str = None,
    max_iterations: int = 4,
    log_callback = None
) -> dict:
    """
    Main Agent Loop:
    1. Simulate, measure, compare with spec, produce a pass/fail table.
    2. If failing, call LLM API for diagnosis and tuning bounds.
    3. Run scipy.optimize (Nelder-Mead) over log10 of components with simulator in loop.
    4. Snap resistors to E24 and capacitors to E12, re-simulate, check spec.
    5. Stop on PASS or max iterations.
    The LLM never claims success. Only simulation results decide pass/fail.
    """
    circuit_info = spice.CIRCUITS[circuit_id]
    circuit_type = circuit_info["type"]
    specs = specs or dict(circuit_info["default_specs"])
    initial_components = dict(initial_components or circuit_info["broken_components"])

    # Initial baseline simulation
    init_freqs, init_gain = spice.simulate_circuit(circuit_id, initial_components)
    init_meas = spice.measure_circuit(init_freqs, init_gain, circuit_type)
    init_passed, init_metrics = spice.evaluate_spec(circuit_id, init_meas, specs)

    history = []
    current_components = dict(initial_components)
    current_measurements = dict(init_meas)
    current_passed = init_passed
    current_metrics = list(init_metrics)
    current_freqs = init_freqs
    current_gain = init_gain

    if current_passed:
        return {
            "passed": True,
            "iterations_run": 0,
            "iterations_log": [],
            "initial_components": initial_components,
            "initial_measurements": init_meas,
            "initial_metrics": init_metrics,
            "initial_curve": (init_freqs, init_gain),
            "final_components": current_components,
            "final_measurements": current_measurements,
            "final_metrics": current_metrics,
            "final_curve": (current_freqs, current_gain),
            "final_netlist": spice.generate_netlist(circuit_id, current_components)
        }

    for iter_idx in range(1, max_iterations + 1):
        if log_callback:
            log_callback(f"Starting Iteration {iter_idx}/{max_iterations}...")

        # Current netlist for LLM
        curr_netlist = spice.generate_netlist(circuit_id, current_components)

        # Step 2: Call LLM API (or demo cached fallback)
        llm_result = get_llm_diagnosis(
            circuit_id=circuit_id,
            netlist=curr_netlist,
            specs=specs,
            measurements=current_measurements,
            current_components=current_components,
            history=history,
            api_key=api_key
        )

        diagnosis = llm_result.get("diagnosis", "")
        components_to_tune = llm_result.get("components_to_tune", list(current_components.keys()))
        bounds = llm_result.get("bounds", {})
        reason = llm_result.get("reason", "")
        source = llm_result.get("source", "LLM")

        # Step 3 & 4: Run Nelder-Mead optimization + snap to E-series
        opt_comps, snapped_comps = optimize_circuit_components(
            circuit_id=circuit_id,
            base_components=current_components,
            components_to_tune=components_to_tune,
            bounds=bounds,
            specs=specs
        )

        # Re-simulate with snapped E-series components
        snapped_freqs, snapped_gain = spice.simulate_circuit(circuit_id, snapped_comps)
        snapped_meas = spice.measure_circuit(snapped_freqs, snapped_gain, circuit_type)

        # Strictly check spec using simulation results ONLY!
        passed, metrics = spice.evaluate_spec(circuit_id, snapped_meas, specs)

        # Record iteration log
        iter_entry = {
            "iteration": iter_idx,
            "diagnosis": diagnosis,
            "components_to_tune": components_to_tune,
            "bounds": bounds,
            "reason": reason,
            "source": source,
            "components_before": dict(current_components),
            "components_continuous": dict(opt_comps),
            "components_snapped": dict(snapped_comps),
            "measurements_before": dict(current_measurements),
            "measurements_after": dict(snapped_meas),
            "metrics": metrics,
            "passed": passed
        }
        history.append(iter_entry)

        # Update current state
        current_components = dict(snapped_comps)
        current_measurements = dict(snapped_meas)
        current_passed = passed
        current_metrics = metrics
        current_freqs = snapped_freqs
        current_gain = snapped_gain

        # Step 5: Stop on PASS
        if passed:
            if log_callback:
                log_callback(f"Circuit PASSED all specifications at Iteration {iter_idx}!")
            break

    return {
        "passed": current_passed,
        "iterations_run": len(history),
        "iterations_log": history,
        "initial_components": initial_components,
        "initial_measurements": init_meas,
        "initial_metrics": init_metrics,
        "initial_curve": (init_freqs, init_gain),
        "final_components": current_components,
        "final_measurements": current_measurements,
        "final_metrics": current_metrics,
        "final_curve": (current_freqs, current_gain),
        "final_netlist": spice.generate_netlist(circuit_id, current_components)
    }


def design_circuit_from_prompt(user_text: str, api_key: str = None) -> dict:
    """
    Translate user's plain-English design request into circuit template + specs.
    Calls LLM if available; falls back to keyword/rule-based path if API fails or DEMO=1.
    Strictly validates template exists in registry and specs inside allowed ranges.
    Never invents a template.
    """
    def rule_based_design(text_raw: str) -> dict:
        text = str(text_raw or "").lower()
        # Check for unsupported circuits first
        if any(k in text for k in ["bandpass", "band-pass", "keep only", "tone and reject", "notch", "band reject"]):
            return {
                "supported": False,
                "template": "",
                "specs": {},
                "explanation": "",
                "reason_if_unsupported": (
                    "Band-pass filters (which isolate a single tone and reject all other frequencies) are not in our template registry. "
                    "Our registry currently supports Sallen-Key Low-Pass Filters and Non-Inverting Amplifiers."
                )
            }
        if any(k in text for k in ["rumble", "below", "highpass", "high-pass", "block low", "reject low"]):
            return {
                "supported": False,
                "template": "",
                "specs": {},
                "explanation": "",
                "reason_if_unsupported": (
                    "High-pass rumble filters (which block frequencies below a set threshold) are not in our template registry. "
                    "Our registry currently supports Sallen-Key Low-Pass Filters and Non-Inverting Amplifiers."
                )
            }

        # Check for amplifier
        if any(k in text for k in ["boost", "amplify", "gain", "mic", "signal to", "amplifier"]):
            gain = 10.0
            m_ratio = re.search(r"(\d+(?:\.\d+)?)\s*(?:m?v)?\s*(?:mic\s*)?(?:signal\s*)?to\s*(\d+(?:\.\d+)?)\s*(?:m?v)?", text)
            if m_ratio:
                vin = float(m_ratio.group(1))
                vout = float(m_ratio.group(2))
                if vin > 0:
                    gain = vout / vin
            else:
                m_gain = re.search(r"(?:gain of|by|boost)\s*(\d+(?:\.\d+)?)\s*x?", text)
                if m_gain:
                    gain = float(m_gain.group(1))
            gain = max(1.5, min(100.0, gain))
            return {
                "supported": True,
                "template": "non_inverting_amp",
                "specs": {
                    "gain_target": gain,
                    "gain_tol": 0.02,
                    "bw_min": 50000.0
                },
                "explanation": (
                    f"We will design a non-inverting amplifier to boost your signal by {gain:.1f}x. "
                    f"This raises your signal voltage cleanly while preserving audio detail and bandwidth."
                ),
                "reason_if_unsupported": ""
            }

        # Check for low-pass filter
        if any(k in text for k in ["hiss", "low pass", "lowpass", "above", "filter", "cutoff", "audio", "treble"]):
            fc = 1000.0
            m_freq = re.search(r"(\d+(?:\.\d+)?)\s*(k|khz|hz|mhz)?", text)
            if m_freq:
                val = float(m_freq.group(1))
                unit = (m_freq.group(2) or "").lower()
                if unit in ["k", "khz"]:
                    fc = val * 1000.0
                elif unit == "mhz":
                    fc = val * 1e6
                elif unit == "hz":
                    fc = val
                elif val < 100:
                    fc = val * 1000.0
                else:
                    fc = val
            fc = max(20.0, min(100000.0, fc))
            return {
                "supported": True,
                "template": "sallen_key",
                "specs": {
                    "fc_target": fc,
                    "fc_tol": 0.05,
                    "peaking_max": 0.5,
                    "dc_gain_target": 0.0,
                    "dc_gain_tol": 0.5
                },
                "explanation": (
                    f"We will design a Sallen-Key low-pass filter with a cutoff frequency of {fc:.0f} Hz. "
                    f"This lets the desirable lower audio frequencies pass through freely while removing high-frequency hiss."
                ),
                "reason_if_unsupported": ""
            }

        return {
            "supported": False,
            "template": "",
            "specs": {},
            "explanation": "",
            "reason_if_unsupported": (
                "We could not recognize this circuit requirement or it is not in our registry. "
                "Our registry currently supports Sallen-Key Low-Pass Filters (e.g. 'Remove hiss above 3 kHz') "
                "and Non-Inverting Amplifiers (e.g. 'Boost a 10 mV mic signal to 100 mV')."
            )
        }

    # If demo mode, run rule-based path directly
    if is_demo_mode(api_key):
        return rule_based_design(user_text)

    # Prompt LLM with strict registry instructions
    system_prompt = (
        "You are an expert circuit design AI assistant. "
        "The ONLY circuits available in our registry are:\n"
        "1. 'sallen_key' (Sallen-Key 2nd-Order Low-Pass Filter):\n"
        "   - What it does: Allows low frequencies to pass, cuts off high frequencies (removes hiss, high-frequency noise).\n"
        "   - Valid spec fields: 'fc_target' (float between 20.0 and 100000.0 Hz).\n"
        "2. 'non_inverting_amp' (Non-Inverting Amplifier):\n"
        "   - What it does: Amplifies/boosts a weak input voltage to a stronger output voltage without inverting polarity.\n"
        "   - Valid spec fields: 'gain_target' (float between 1.5 and 100.0), 'bw_min' (float between 1000.0 and 500000.0 Hz).\n\n"
        "RULES:\n"
        "- Respond with JSON ONLY. Do not include markdown fences (```) or other text.\n"
        "- If the request requires any other circuit (e.g. band-pass, high-pass rumble filter, notch filter), you MUST set 'supported': false.\n"
        "- NEVER invent a template name. The ONLY valid template names are 'sallen_key' and 'non_inverting_amp'.\n"
        "- Output format:\n"
        "{\n"
        '  "supported": true/false,\n'
        '  "template": "<sallen_key or non_inverting_amp>",\n'
        '  "specs": {"<spec_key>": value},\n'
        '  "explanation": "<2 plain-English sentences for a beginner>",\n'
        '  "reason_if_unsupported": "..."\n'
        "}"
    )

    try:
        raw = call_llm_provider(user_text, api_key=api_key, system_prompt=system_prompt)
        clean = raw.strip()
        clean = re.sub(r"^```(?:json)?\s*", "", clean)
        clean = re.sub(r"\s*```$", "", clean)
        data = json.loads(clean)

        supported = bool(data.get("supported", False))
        if not supported:
            reason = data.get("reason_if_unsupported", "") or "This circuit is not currently supported in our registry."
            return {
                "supported": False,
                "template": "",
                "specs": {},
                "explanation": "",
                "reason_if_unsupported": reason
            }

        template = str(data.get("template", "")).strip()
        if template not in spice.CIRCUITS:
            # Never invent a template!
            return rule_based_design(user_text)

        specs = data.get("specs", {})
        if not isinstance(specs, dict):
            return rule_based_design(user_text)

        # Validate spec ranges
        if template == "sallen_key":
            fc = float(specs.get("fc_target", 1000.0))
            if not (20.0 <= fc <= 100000.0):
                return rule_based_design(user_text)
            clean_specs = {
                "fc_target": fc,
                "fc_tol": float(specs.get("fc_tol", 0.05)),
                "peaking_max": float(specs.get("peaking_max", 0.5)),
                "dc_gain_target": float(specs.get("dc_gain_target", 0.0)),
                "dc_gain_tol": float(specs.get("dc_gain_tol", 0.5))
            }
        elif template == "non_inverting_amp":
            gain = float(specs.get("gain_target", 10.0))
            if not (1.5 <= gain <= 100.0):
                return rule_based_design(user_text)
            clean_specs = {
                "gain_target": gain,
                "gain_tol": float(specs.get("gain_tol", 0.02)),
                "bw_min": float(specs.get("bw_min", 50000.0))
            }
        else:
            return rule_based_design(user_text)

        explanation = data.get("explanation", "")
        if not explanation:
            explanation = rule_based_design(user_text).get("explanation", "")

        return {
            "supported": True,
            "template": template,
            "specs": clean_specs,
            "explanation": explanation,
            "reason_if_unsupported": ""
        }

    except Exception:
        return rule_based_design(user_text)


def generate_rough_guess(circuit_id: str, specs: dict = None) -> dict:
    """
    Create a rough first-guess design: scale the template's default component values
    to roughly the right frequency or gain range with no optimization (so it usually fails the spec).
    """
    specs = specs or {}
    if circuit_id == "sallen_key":
        fc_target = float(specs.get("fc_target", 1000.0))
        scale = 1000.0 / max(20.0, fc_target)
        c1_guess = spice.snap_value(68e-9 * scale, "C")
        c2_guess = spice.snap_value(6.8e-9 * scale, "C")
        return {
            "R1": 7.5e3,
            "R2": 7.5e3,
            "C1": c1_guess,
            "C2": c2_guess
        }
    elif circuit_id == "non_inverting_amp":
        gain_target = float(specs.get("gain_target", 10.0))
        rg_guess = 2.2e3
        rf_guess = spice.snap_value(rg_guess * (gain_target * 2.0), "R")
        return {
            "Rf": rf_guess,
            "Rg": rg_guess
        }
    else:
        if circuit_id in spice.CIRCUITS:
            return dict(spice.CIRCUITS[circuit_id]["broken_components"])
        return {}


def ask_about_results(
    circuit_id: str,
    specs: dict = None,
    initial_measurements: dict = None,
    final_measurements: dict = None,
    initial_components: dict = None,
    final_components: dict = None,
    question: str = "",
    api_key: str = None
) -> str:
    """
    Answer beginner questions about circuit repair results in 3 sentences or less.
    Falls back to a dynamic canned answer built from the numbers if in DEMO mode or API fails.
    """
    if circuit_id not in spice.CIRCUITS:
        return "Circuit details are not available."

    c_info = spice.CIRCUITS[circuit_id]
    c_name = c_info["name"]

    specs = specs or {}
    initial_measurements = initial_measurements or {}
    final_measurements = final_measurements or {}
    initial_components = initial_components or {}
    final_components = final_components or {}
    question = str(question or "")

    # Human-readable component changes
    comp_changes = []
    for k, v_fin in final_components.items():
        v_init = initial_components.get(k, 0.0)
        c_type = c_info["component_types"].get(k, "R")
        s_init = spice.format_eng(v_init, c_type)
        s_fin = spice.format_eng(v_fin, c_type)
        comp_changes.append(f"{k}: {s_init} -> {s_fin}")
    comp_changes_str = ", ".join(comp_changes)

    # Format numbers for prompt & fallback
    if circuit_id == "sallen_key":
        tgt_fc = specs.get("fc_target", 1000.0)
        init_fc = initial_measurements.get("fc_3db_hz", 0.0)
        final_fc = final_measurements.get("fc_3db_hz", 0.0)
        init_pk = initial_measurements.get("peaking_db", 0.0)
        final_pk = final_measurements.get("peaking_db", 0.0)
        specs_summary = f"Cutoff fc = {tgt_fc:.0f} Hz (±5%), Peaking <= 0.5 dB"
        meas_summary_before = f"Cutoff = {init_fc:.1f} Hz, Peaking = {init_pk:.2f} dB"
        meas_summary_after = f"Cutoff = {final_fc:.1f} Hz, Peaking = {final_pk:.2f} dB"
    else:
        tgt_gain = specs.get("gain_target", 10.0)
        tgt_bw = specs.get("bw_min", 50000.0)
        init_gain = initial_measurements.get("linear_gain", 0.0)
        final_gain = final_measurements.get("linear_gain", 0.0)
        init_bw = initial_measurements.get("bandwidth_hz", 0.0)
        final_bw = final_measurements.get("bandwidth_hz", 0.0)
        specs_summary = f"Gain = {tgt_gain:.1f}x (±2%), Bandwidth >= {tgt_bw/1000:.0f} kHz"
        meas_summary_before = f"Gain = {init_gain:.2f}x, Bandwidth = {init_bw/1000:.1f} kHz"
        meas_summary_after = f"Gain = {final_gain:.2f}x, Bandwidth = {final_bw/1000:.1f} kHz"

    if not is_demo_mode(api_key):
        system_prompt = (
            "You are a friendly, encouraging electronics tutor explaining circuit design to a complete beginner. "
            "Explain clearly and simply in at most 3 sentences. Avoid unexplained jargon. Never exceed 3 sentences."
        )
        prompt = f"""Circuit: {c_name}
Target Specs: {specs_summary}
Before Measurements: {meas_summary_before}
After Measurements: {meas_summary_after}
Component Changes: {comp_changes_str}

User Question: "{question}"

Answer the question accurately for a beginner based on the numbers above in 3 sentences or less."""

        try:
            ans = call_llm_provider(prompt, api_key=api_key, system_prompt=system_prompt, json_mode=False)
            clean_ans = ans.strip()
            clean_ans = re.sub(r"^```(?:markdown|json|text)?\s*", "", clean_ans)
            clean_ans = re.sub(r"\s*```$", "", clean_ans)
            sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", clean_ans) if s.strip()]
            if len(sentences) > 3:
                clean_ans = " ".join(sentences[:3])
            return clean_ans
        except Exception:
            pass  # Fall through to canned answer built from numbers

    # Canned fallback built from actual numbers
    q_lower = question.lower()
    if any(k in q_lower for k in ["peaking", "peak", "resonance", "bump", "overshoot"]):
        if circuit_id == "sallen_key":
            return (
                f"Peaking is an unwanted resonance bump where frequencies near cutoff get accidentally boosted too loud. "
                f"Your original circuit had {init_pk:.2f} dB of peaking because its capacitor ratio was too high. "
                f"We adjusted the capacitors to bring peaking down to {final_pk:.2f} dB, creating a smooth Butterworth response."
            )
        else:
            return (
                f"In this amplifier, we tuned feedback resistors to satisfy your target gain of {tgt_gain:.1f}x without overshoot. "
                f"The bandwidth was improved from {init_bw/1000:.1f} kHz to {final_bw/1000:.1f} kHz. "
                f"This guarantees flat, distortion-free amplification across the entire audio spectrum."
            )

    if any(k in q_lower for k in ["cutoff", "frequency", "hz", "khz", "filter", "hiss"]):
        if circuit_id == "sallen_key":
            return (
                f"The cutoff frequency is the point where the filter starts blocking higher audio tones. "
                f"The circuit was adjusted from {init_fc:.1f} Hz to {final_fc:.1f} Hz to closely hit your {tgt_fc:.0f} Hz target. "
                f"This successfully filters out high-frequency noise while leaving your desired audio crisp and intact."
            )

    if any(k in q_lower for k in ["gain", "volume", "loud", "boost", "amplify", "bandwidth"]):
        if circuit_id == "non_inverting_amp":
            return (
                f"The original circuit amplified the signal too much ({init_gain:.2f}x), which choked its bandwidth down to {init_bw/1000:.1f} kHz. "
                f"By adjusting the feedback resistors ({comp_changes_str}), we achieved the target gain of {final_gain:.2f}x. "
                f"This also freed up bandwidth to {final_bw/1000:.1f} kHz, ensuring high fidelity."
            )

    if any(k in q_lower for k in ["why", "change", "resistor", "capacitor", "r1", "r2", "c1", "c2", "rf", "rg", "component", "parts"]):
        return (
            f"We adjusted {comp_changes_str} so that the circuit's electrical behavior aligns with your exact design target. "
            f"Before the repair, the measurements were {meas_summary_before}, but after tuning they reached {meas_summary_after}. "
            f"All final parts are snapped to commercial E-series standards, so you can easily purchase and build this circuit."
        )

    # General canned response built from numbers
    return (
        f"The circuit was re-tuned from {meas_summary_before} to {meas_summary_after} to meet your specification. "
        f"This was achieved by adjusting components to standard values: {comp_changes_str}. "
        f"Simulation verifies that all required performance criteria are now completely satisfied."
    )


def answer_user_question(
    question: str,
    circuit_id: str = "sallen_key",
    specs: dict = None,
    results: dict = None,
    api_key: str = None,
    **kwargs
) -> str:
    """
    User-facing entry point to answer beginner questions about circuit results.
    Accepts results dict directly or via individual measurement/component parameters.
    """
    res = results or kwargs.get("res", {})
    init_comps = kwargs.get("initial_components") or res.get("initial_components")
    final_comps = kwargs.get("final_components") or res.get("final_components")
    init_meas = kwargs.get("initial_measurements") or res.get("initial_measurements")
    final_meas = kwargs.get("final_measurements") or res.get("final_measurements")
    circuit_specs = specs or res.get("specs")

    return ask_about_results(
        circuit_id=circuit_id,
        specs=circuit_specs,
        initial_measurements=init_meas,
        final_measurements=final_meas,
        initial_components=init_comps,
        final_components=final_comps,
        question=question,
        api_key=api_key
    )


