"""
test_headless.py - Headless test for Analog Circuit Fixer.
Runs the Sallen-Key broken preset, performs optimization via the agent loop,
and prints before/after measurements and pass/fail tables.
"""

import sys
import spice
import agent

def main():
    print("=" * 70)
    print("   ANALOG CIRCUIT FIXER - HEADLESS TEST (SALLEN-KEY PRESET)")
    print("=" * 70)

    try:
        ngspice_path = spice.find_ngspice()
        print(f"[OK] ngspice located at: {ngspice_path}")
    except Exception as e:
        print(f"[ERROR] {e}")
        sys.exit(1)

    circuit_id = "sallen_key"
    circuit_info = spice.CIRCUITS[circuit_id]
    broken_comps = circuit_info["broken_components"]
    specs = circuit_info["default_specs"]

    print(f"\nCircuit: {circuit_info['name']}")
    print(f"Target Specs:")
    print(f"  - Cutoff frequency fc: {specs['fc_target']:.0f} Hz (+-{specs['fc_tol']*100:.0f}%) [950 - 1050 Hz]")
    print(f"  - Passband Peaking:   <= {specs['peaking_max']:.1f} dB (Butterworth Q~0.707)")
    print(f"  - DC Gain:             {specs['dc_gain_target']:.1f} dB (+-{specs['dc_gain_tol']:.1f} dB)")

    print("\n--- 1. SIMULATING BROKEN PRESET ---")
    print("Broken Component Values:")
    for k, v in broken_comps.items():
        c_type = circuit_info["component_types"].get(k, "R")
        print(f"  {k}: {spice.format_eng(v, c_type)} ({v:.3e})")

    freqs_init, gain_init = spice.simulate_circuit(circuit_id, broken_comps)
    meas_init = spice.measure_circuit(freqs_init, gain_init, circuit_info["type"])
    passed_init, metrics_init = spice.evaluate_spec(circuit_id, meas_init, specs)

    print("\nInitial Measurements (BROKEN):")
    for m in metrics_init:
        badge = "PASS" if m["passed"] else "FAIL"
        print(f"  [{badge}] {m['name']:<24}: {m['measured_str']:<14} (Target: {m['target_str']})")

    assert not passed_init, "Initial broken preset unexpectedly passed spec!"
    print("\n-> Confirmed: Broken circuit FAILS spec.")

    print("\n--- 2. RUNNING AGENT LOOP (DIAGNOSIS + OPTIMIZATION + SNAPPING) ---")
    res = agent.run_agent_loop(
        circuit_id=circuit_id,
        initial_components=broken_comps,
        specs=specs,
        max_iterations=4,
        log_callback=lambda msg: print(f"  {msg}")
    )

    print(f"\nAgent Loop Completed in {res['iterations_run']} iteration(s).")
    for it in res["iterations_log"]:
        print(f"\n[Iteration {it['iteration']}] Source: {it['source']}")
        print(f"Diagnosis: {it['diagnosis']}")
        print(f"Tuned:     {it['components_to_tune']}")
        print(f"Reason:    {it['reason']}")
        print("Continuous optimized values:")
        for k, v in it["components_continuous"].items():
            print(f"  {k}: {spice.format_eng(v, circuit_info['component_types'].get(k, 'R'))}")
        print("Snapped E-series values:")
        for k, v in it["components_snapped"].items():
            c_type = "E24 Resistor" if circuit_info['component_types'].get(k) == "R" else "E12 Capacitor"
            print(f"  {k}: {spice.format_eng(v, circuit_info['component_types'].get(k, 'R'))} ({c_type})")

    print("\n--- 3. VERIFYING FIXED CIRCUIT WITH STANDARD E-SERIES VALUES ---")
    print("Final Measurements (AFTER FIX):")
    for m in res["final_metrics"]:
        badge = "PASS" if m["passed"] else "FAIL"
        print(f"  [{badge}] {m['name']:<24}: {m['measured_str']:<14} (Target: {m['target_str']})")

    print("\n" + "=" * 70)
    print("                      BEFORE VS AFTER COMPARISON")
    print("=" * 70)
    print(f"{'Metric':<24} | {'Before':<14} | {'After':<14} | {'Target Spec':<20} | {'Status'}")
    print("-" * 85)
    for m_init, m_final in zip(res["initial_metrics"], res["final_metrics"]):
        status = "PASS" if m_final["passed"] else "FAIL"
        print(
            f"{m_init['name']:<24} | "
            f"{m_init['measured_str']:<14} | "
            f"{m_final['measured_str']:<14} | "
            f"{m_init['target_str']:<20} | "
            f"[{status}]"
        )
    print("-" * 85)

    if res["passed"]:
        print("\n>>> ALL SPECIFICATIONS PASSED! HEADLESS TEST SUCCEEDED! <<<\n")
    else:
        print("\n>>> TEST FAILED: Specs were not met after optimization. <<<\n")
        sys.exit(1)

if __name__ == "__main__":
    main()
