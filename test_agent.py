"""
test_agent.py - Verification suite for agent.py interfaces and fallbacks.
Tests AI design translation, optimizer integration, rough guess generation,
and beginner Q&A tutor.
"""

import unittest
import numpy as np
import spice
import agent


class TestAgentInterfaces(unittest.TestCase):
    def test_get_ai_status(self):
        online, status = agent.get_ai_status(api_key=None)
        self.assertIsInstance(online, bool)
        self.assertIsInstance(status, str)
        self.assertIn("AI:", status)

    def test_design_circuit_from_prompt_supported(self):
        res = agent.design_circuit_from_prompt("Remove hiss above 3 kHz from my audio", api_key=None)
        self.assertTrue(res["supported"])
        self.assertEqual(res["template"], "sallen_key")
        self.assertIn("fc_target", res["specs"])
        self.assertAlmostEqual(res["specs"]["fc_target"], 3000.0)

    def test_design_circuit_from_prompt_amplifier(self):
        res = agent.design_circuit_from_prompt("Boost a 10 mV mic signal to 100 mV", api_key=None)
        self.assertTrue(res["supported"])
        self.assertEqual(res["template"], "non_inverting_amp")
        self.assertIn("gain_target", res["specs"])
        self.assertAlmostEqual(res["specs"]["gain_target"], 10.0)

    def test_design_circuit_from_prompt_unsupported(self):
        res = agent.design_circuit_from_prompt("Keep only a 1 kHz tone and reject everything else", api_key=None)
        self.assertFalse(res["supported"])
        self.assertIn("Band-pass", res["reason_if_unsupported"])

    def test_design_circuit_from_prompt_none_input(self):
        res = agent.design_circuit_from_prompt(None, api_key=None)
        self.assertFalse(res["supported"])

    def test_generate_rough_guess_sallen_key(self):
        guess = agent.generate_rough_guess("sallen_key", {"fc_target": 2000.0})
        self.assertIn("R1", guess)
        self.assertIn("R2", guess)
        self.assertIn("C1", guess)
        self.assertIn("C2", guess)
        self.assertGreater(guess["R1"], 0)

    def test_generate_rough_guess_amplifier(self):
        guess = agent.generate_rough_guess("non_inverting_amp", {"gain_target": 15.0})
        self.assertIn("Rf", guess)
        self.assertIn("Rg", guess)
        self.assertGreater(guess["Rf"], 0)

    def test_generate_rough_guess_none_specs(self):
        guess = agent.generate_rough_guess("sallen_key", None)
        self.assertIn("R1", guess)

    def test_ask_about_results_canned_numeric_fallback(self):
        ans = agent.ask_about_results(
            circuit_id="sallen_key",
            specs={"fc_target": 1000.0},
            initial_measurements={"fc_3db_hz": 1421.5, "peaking_db": 4.45, "dc_gain_db": 0.0},
            final_measurements={"fc_3db_hz": 976.6, "peaking_db": 0.0, "dc_gain_db": 0.0},
            initial_components={"R1": 7500, "R2": 7500, "C1": 68e-9, "C2": 6.8e-9},
            final_components={"R1": 6800, "R2": 8200, "C1": 22e-9, "C2": 15e-9},
            question="What is peaking and why did the capacitors change?",
            api_key=None
        )
        self.assertIsInstance(ans, str)
        self.assertGreater(len(ans), 20)
        self.assertIn("peaking", ans.lower())

    def test_run_agent_loop_execution(self):
        circuit_id = "sallen_key"
        broken_comps = spice.CIRCUITS[circuit_id]["broken_components"]
        specs = spice.CIRCUITS[circuit_id]["default_specs"]

        res = agent.run_agent_loop(
            circuit_id=circuit_id,
            initial_components=broken_comps,
            specs=specs,
            max_iterations=2
        )
        self.assertIn("passed", res)
        self.assertIn("iterations_run", res)
        self.assertIn("final_components", res)
        self.assertIn("final_measurements", res)
        self.assertIn("final_metrics", res)
        self.assertIn("final_netlist", res)
        self.assertTrue(res["passed"])


if __name__ == "__main__":
    unittest.main()

