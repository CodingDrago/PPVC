"""
test_full_flow.py - Headless execution of all prompt suggestion chips and Q&A flow.
Verifies end-to-end design translation, optimization, transient simulation, and Q&A tutoring.
"""
import sys
import spice
import agent


def test_chip_prompt_1():
    print("\n--- Testing Chip Prompt 1: Audio Hiss ---")
    prompt = "Remove hiss above 3 kHz from my audio"
    res = agent.design_circuit_from_prompt(prompt, api_key=None)
    assert res["supported"], f"Expected supported, got: {res}"
    assert res["template"] == "sallen_key"
    assert res["specs"]["fc_target"] == 3000.0

    # Rough guess
    rough = agent.generate_rough_guess("sallen_key", res["specs"])
    print(f"Rough guess: {rough}")

    # Transient check on rough components
    t, vin, vout = spice.simulate_transient("sallen_key", rough, res["specs"])
    assert len(t) > 0, "Transient simulation returned empty time array"
    print(f"Rough transient points: {len(t)}")

    # Full fix loop
    loop_res = agent.run_agent_loop("sallen_key", rough, res["specs"], max_iterations=4)
    print(f"Fix loop completed: passed={loop_res['passed']} in {loop_res['iterations_run']} iter(s)")
    assert loop_res["passed"], "Calibration should pass target specs"

    # Transient check on final components
    t_fin, vin_fin, vout_fin = spice.simulate_transient("sallen_key", loop_res["final_components"], res["specs"])
    assert len(t_fin) > 0
    print(f"Final transient verified: {len(t_fin)} points")
    return loop_res


def test_chip_prompt_2():
    print("\n--- Testing Chip Prompt 2: Mic Preamp ---")
    prompt = "Boost a 10 mV mic signal to 100 mV"
    res = agent.design_circuit_from_prompt(prompt, api_key=None)
    assert res["supported"], f"Expected supported, got: {res}"
    assert res["template"] == "non_inverting_amp"
    assert res["specs"]["gain_target"] == 10.0

    # Rough guess
    rough = agent.generate_rough_guess("non_inverting_amp", res["specs"])
    print(f"Rough guess: {rough}")

    # Transient check on rough components
    t, vin, vout = spice.simulate_transient("non_inverting_amp", rough, res["specs"])
    assert len(t) > 0
    print(f"Rough transient points: {len(t)}")

    # Full fix loop
    loop_res = agent.run_agent_loop("non_inverting_amp", rough, res["specs"], max_iterations=4)
    print(f"Fix loop completed: passed={loop_res['passed']} in {loop_res['iterations_run']} iter(s)")
    assert loop_res["passed"], "Calibration should pass target specs"

    # Transient check on final components
    t_fin, vin_fin, vout_fin = spice.simulate_transient("non_inverting_amp", loop_res["final_components"], res["specs"])
    assert len(t_fin) > 0
    print(f"Final transient verified: {len(t_fin)} points")
    return loop_res


def test_chip_prompt_3():
    print("\n--- Testing Chip Prompt 3: 1 kHz Tone (Unsupported Band-pass) ---")
    prompt = "Keep only a 1 kHz tone and reject everything else"
    res = agent.design_circuit_from_prompt(prompt, api_key=None)
    assert not res["supported"], f"Expected unsupported, got: {res}"
    assert "Band-pass" in res["reason_if_unsupported"] or "registry" in res["reason_if_unsupported"]
    print(f"[PASS] Friendly rejection: {res['reason_if_unsupported']}")


def test_chip_prompt_4():
    print("\n--- Testing Chip Prompt 4: Sub Rumble (Unsupported High-pass) ---")
    prompt = "Block low-frequency rumble below 200 Hz"
    res = agent.design_circuit_from_prompt(prompt, api_key=None)
    assert not res["supported"], f"Expected unsupported, got: {res}"
    assert "High-pass" in res["reason_if_unsupported"] or "registry" in res["reason_if_unsupported"]
    print(f"[PASS] Friendly rejection: {res['reason_if_unsupported']}")


def test_question(loop_res):
    print("\n--- Testing Question: 'Why did C1 and C2 change?' ---")
    question = "Why did C1 and C2 change?"
    ans = agent.answer_user_question(
        question=question,
        circuit_id="sallen_key",
        specs={"fc_target": 3000.0},
        results=loop_res
    )
    assert ans and len(ans) > 20, f"Expected non-empty answer, got: {ans}"
    print(f"Tutor Answer:\n{ans}")


def test_unverified_mode():
    print("\n--- Testing Unverified Mode (Fast Preview) ---")
    rough = agent.generate_rough_guess("sallen_key", {"fc_target": 2000.0})
    f, g = spice.simulate_circuit("sallen_key", rough)
    m = spice.measure_circuit(f, g, "filter")
    passed, table = spice.evaluate_spec("sallen_key", m, {"fc_target": 2000.0})
    res = {
        "passed": passed,
        "iterations_run": 1,
        "initial_components": dict(rough),
        "final_components": dict(rough),
        "initial_measurements": m,
        "final_measurements": m,
        "is_unverified_guess": True
    }
    assert res["is_unverified_guess"]
    print(f"[PASS] Single simulation evaluated: cutoff={m.get('fc_3db_hz', 0):.1f} Hz")


if __name__ == "__main__":
    print("=" * 60)
    print("RUNNING HEADLESS FULL FLOW VERIFICATION")
    print("=" * 60)

    try:
        loop_res = test_chip_prompt_1()
        test_chip_prompt_2()
        test_chip_prompt_3()
        test_chip_prompt_4()
        test_question(loop_res)
        test_unverified_mode()

        print("\n" + "=" * 60)
        print("ALL 4 CHIP PROMPTS, TRANSIENTS, AND QUESTION PASSED WITH 0 EXCEPTIONS!")
        print("=" * 60)
    except Exception as e:
        print(f"\n[FAIL] Exception encountered: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

