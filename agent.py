"""
agent.py - LLM diagnosis, numerical optimizer, and agent loop
for Analog Circuit Fixer.
"""

import json
import os
import re
import numpy as np
import requests
from scipy.optimize import minimize

import spice

# Fallback / demo status flag
def is_demo_mode(api_key: str = None) -> bool:
    """Return True if demo mode is requested or no API key is available."""
    if os.environ.get("DEMO", "0").lower() in ("1", "true", "yes"):
        return True
    key = api_key or os.environ.get("LLM_API_KEY")
    return not bool(key)


def call_llm_provider(prompt: str, api_key: str = None) -> str:
    """
    Unified LLM provider call.
    Default uses OpenAI-compatible chat completions endpoint.
    Easy to swap to any custom provider.
    """
    key = api_key or os.environ.get("LLM_API_KEY")
    if not key:
        raise ValueError("LLM_API_KEY environment variable is not set.")

    base_url = os.environ.get("LLM_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    model = os.environ.get("LLM_MODEL", "gpt-4o-mini")

    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are an expert analog circuit design and debugging AI. "
                    "Analyze the given SPICE netlist, circuit specs, measurements, and history. "
                    "Respond with JSON ONLY. Do not include markdown code fences or conversational text."
                )
            },
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.2,
        "max_tokens": 800
    }

    url = f"{base_url}/chat/completions"
    response = requests.post(url, headers=headers, json=payload, timeout=20)
    response.raise_for_status()
    data = response.json()
    return data["choices"][0]["message"]["content"]


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
    initial_components: dict,
    specs: dict,
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
