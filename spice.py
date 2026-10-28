"""
spice.py - SPICE netlist generation, ngspice execution, and circuit measurement
for Analog Circuit Fixer.
"""

import os
import re
import shutil
import subprocess
import tempfile
import numpy as np

# Standard E-series values
E12_VALUES = np.array([1.0, 1.2, 1.5, 1.8, 2.2, 2.7, 3.3, 3.9, 4.7, 5.6, 6.8, 8.2])
E24_VALUES = np.array([
    1.0, 1.1, 1.2, 1.3, 1.5, 1.6, 1.8, 2.0, 2.2, 2.4, 2.7, 3.0,
    3.3, 3.6, 3.9, 4.3, 4.7, 5.1, 5.6, 6.2, 6.8, 7.5, 8.2, 9.1
])

# Single-pole op-amp macro model subcircuit
# DC gain: 1e5 (100 dB), GBW: 1 MHz -> pole at fp = 10 Hz
# R_pole = 1k, C_pole = 1 / (2 * pi * 10 * 1000) = 15.9154943 uF
OPAMP_SUBCKT = """* Single-Pole Op-Amp Macro Model
* DC Gain = 1e5 (100 dB), GBW = 1.0 MHz (fp = 10 Hz)
.subckt OPAMP_1POLE in_p in_m out ref
E1 int ref in_p in_m 1e5
R_pole int node 1k
C_pole node ref 15.9154943u
E2 out ref node ref 1.0
.ends
"""

def find_ngspice() -> str:
    """Locate the ngspice executable on the system."""
    user_home = os.path.expanduser("~")
    candidates = [
        "ngspice_con",
        "ngspice",
        "ngspice_con.exe",
        "ngspice.exe",
        os.path.join(user_home, "Spice64", "bin", "ngspice_con.exe"),
        os.path.join(user_home, "Spice64", "bin", "ngspice.exe"),
        r"C:\Spice64\bin\ngspice_con.exe",
        r"C:\Spice64\bin\ngspice.exe",
        r"C:\Program Files\ngspice\bin\ngspice.exe",
        r"C:\Program Files (x86)\ngspice\bin\ngspice.exe",
        "/usr/bin/ngspice",
        "/usr/local/bin/ngspice",
        "/opt/homebrew/bin/ngspice",
    ]
    for c in candidates:
        w = shutil.which(c) or (c if os.path.exists(c) else None)
        if w:
            return w
    raise RuntimeError(
        "ngspice was not found on your system! "
        "Please install ngspice and ensure it is available in PATH or at C:\\Spice64\\bin."
    )


def format_eng(val: float, comp_type: str = "") -> str:
    """Format numeric value into standard engineering / SPICE notation."""
    if val is None or np.isnan(val):
        return "N/A"
    abs_v = abs(val)
    if abs_v == 0:
        return "0"

    if abs_v >= 1e6:
        # SPICE uses 'Meg' for 10^6
        formatted = f"{val/1e6:.3g}Meg"
    elif abs_v >= 1e3:
        formatted = f"{val/1e3:.3g}k"
    elif abs_v >= 1:
        formatted = f"{val:.3g}"
    elif abs_v >= 1e-3:
        formatted = f"{val*1e3:.3g}m"
    elif abs_v >= 1e-6:
        formatted = f"{val*1e6:.3g}u"
    elif abs_v >= 1e-9:
        formatted = f"{val*1e9:.3g}n"
    elif abs_v >= 1e-12:
        formatted = f"{val*1e12:.3g}p"
    else:
        formatted = f"{val:.3e}"

    if comp_type == "R":
        return f"{formatted} Ohm"
    elif comp_type == "C":
        return f"{formatted}F"
    return formatted


def format_spice_val(val: float) -> str:
    """Format value for SPICE netlist syntax."""
    abs_v = abs(val)
    if abs_v >= 1e6:
        return f"{val/1e6:.4g}Meg"
    elif abs_v >= 1e3:
        return f"{val/1e3:.4g}k"
    elif abs_v >= 1:
        return f"{val:.4g}"
    elif abs_v >= 1e-3:
        return f"{val*1e3:.4g}m"
    elif abs_v >= 1e-6:
        return f"{val*1e6:.4g}u"
    elif abs_v >= 1e-9:
        return f"{val*1e9:.4g}n"
    elif abs_v >= 1e-12:
        return f"{val*1e12:.4g}p"
    else:
        return f"{val:.4e}"


def parse_spice_val(val_str: str) -> float:
    """Parse SPICE notation string into float."""
    s = str(val_str).strip().replace("Ω", "").replace("F", "").replace("Hz", "")
    multipliers = {
        "t": 1e12, "g": 1e9, "meg": 1e6, "k": 1e3,
        "m": 1e-3, "u": 1e-6, "n": 1e-9, "p": 1e-12, "f": 1e-15
    }
    match = re.match(r"^([-+]?[0-9]*\.?[0-9]+(?:[eE][-+]?[0-9]+)?)\s*([a-zA-Z]*)", s)
    if not match:
        return float(s)
    num, suffix = match.groups()
    base = float(num)
    suffix = suffix.lower()
    if suffix.startswith("meg"):
        return base * 1e6
    for k, mult in multipliers.items():
        if suffix.startswith(k):
            return base * mult
    return base


def snap_value(val: float, comp_type: str = "R") -> float:
    """Snap a value to standard E24 (resistors) or E12 (capacitors)."""
    if val <= 0:
        return val
    series = E24_VALUES if comp_type == "R" else E12_VALUES
    dec = 10.0 ** np.floor(np.log10(val))
    norm = val / dec
    best = min(series, key=lambda s: abs(np.log10(norm) - np.log10(s)))
    return float(best * dec)


def snap_components(components: dict, comp_types: dict) -> dict:
    """Snap an entire dictionary of components to standard E-series."""
    snapped = {}
    for comp, val in components.items():
        c_type = comp_types.get(comp, "R")
        snapped[comp] = snap_value(val, c_type)
    return snapped


# Circuit Templates and Configurations
CIRCUITS = {
    "sallen_key": {
        "id": "sallen_key",
        "name": "Sallen-Key 2nd-Order Low-Pass Filter",
        "description": "Unity-gain Sallen-Key low-pass filter with 100 dB, 1 MHz GBW single-pole op-amp model.",
        "type": "low_pass",
        "component_types": {"R1": "R", "R2": "R", "C1": "C", "C2": "C"},
        # Broken preset: wrong R/C values giving fc ~1.4 kHz and ~4.4 dB peaking
        "broken_components": {"R1": 7.5e3, "R2": 7.5e3, "C1": 68e-9, "C2": 6.8e-9},
        "default_specs": {
            "fc_target": 1000.0,       # 1 kHz
            "fc_tol": 0.05,            # +-5% (950 to 1050 Hz)
            "peaking_max": 0.5,        # <= 0.5 dB
            "dc_gain_target": 0.0,     # 0 dB
            "dc_gain_tol": 0.5         # +-0.5 dB (-0.5 to +0.5 dB)
        },
        "default_bounds": {
            "R1": [1e3, 1e5],
            "R2": [1e3, 1e5],
            "C1": [1e-9, 1e-6],
            "C2": [1e-9, 1e-6]
        },
        "demo_diagnosis": {
            "diagnosis": "The circuit cutoff frequency fc is ~1.42 kHz (well above the 1.0 kHz +-5% spec) and passband peaking is ~4.4 dB (far exceeding the 0.5 dB Butterworth limit). The ratio C1/C2 is approximately 10:1, which creates high Q resonance (Q ~ 1.58).",
            "components_to_tune": ["R1", "R2", "C1", "C2"],
            "bounds": {"R1": [2e3, 5e4], "R2": [2e3, 5e4], "C1": [5e-9, 2e-7], "C2": [2e-9, 1e-7]},
            "reason": "Lower the C1/C2 ratio to ~2.0-2.2 to set Butterworth damping (Q ~ 0.707) and scale R1, R2 to place the corner frequency fc precisely at 1.0 kHz."
        }
    },
    "non_inverting_amp": {
        "id": "non_inverting_amp",
        "name": "Non-Inverting Amplifier",
        "description": "Closed-loop non-inverting amplifier with 100 dB, 1 MHz GBW single-pole op-amp model.",
        "type": "amplifier",
        "component_types": {"Rf": "R", "Rg": "R"},
        # Broken preset: wrong feedback resistors giving gain ~46.5 and bandwidth ~21 kHz
        "broken_components": {"Rf": 100e3, "Rg": 2.2e3},
        "default_specs": {
            "gain_target": 10.0,       # Linear gain = 10 (20 dB)
            "gain_tol": 0.02,          # +-2% (9.8 to 10.2)
            "bw_min": 50000.0          # Bandwidth >= 50 kHz
        },
        "default_bounds": {
            "Rf": [1e3, 2e5],
            "Rg": [500.0, 5e4]
        },
        "demo_diagnosis": {
            "diagnosis": "The feedback resistor ratio Rf/Rg is ~45.5, creating a closed-loop gain of ~46.5 (33.3 dB), which severely misses the target gain of 10 (+-2%). Because the op-amp has a finite 1 MHz gain-bandwidth product (GBW), this excessive gain forces the -3 dB bandwidth down to ~21.5 kHz, failing the 50 kHz requirement.",
            "components_to_tune": ["Rf", "Rg"],
            "bounds": {"Rf": [5e3, 5e4], "Rg": [500.0, 1e4]},
            "reason": "Adjust Rf and Rg so that 1 + Rf/Rg = 10 (ratio Rf/Rg = 9) with impedance levels that maintain closed-loop bandwidth well above 50 kHz (ideally ~100 kHz)."
        }
    }
}


def generate_netlist(circuit_id: str, components: dict, out_file: str = "ac_out.txt") -> str:
    """Generate SPICE netlist text from component dictionary."""
    out_spice_path = out_file.replace("\\", "/")

    if circuit_id == "sallen_key":
        r1_s = format_spice_val(components.get("R1", 7.5e3))
        r2_s = format_spice_val(components.get("R2", 7.5e3))
        c1_s = format_spice_val(components.get("C1", 68e-9))
        c2_s = format_spice_val(components.get("C2", 6.8e-9))

        return f"""* Sallen-Key 2nd-Order Low-Pass Filter (Unity Gain)
* Target Spec: fc = 1.0 kHz (+-5%), Peaking <= 0.5 dB, DC Gain = 0 dB (+-0.5 dB)

{OPAMP_SUBCKT}
Vin in 0 dc 0 ac 1
R1 in n1 {r1_s}
R2 n1 n_plus {r2_s}
C1 n1 out {c1_s}
C2 n_plus 0 {c2_s}
XOP n_plus out out 0 OPAMP_1POLE

.control
ac dec 200 10 1Meg
wrdata {out_spice_path} vdb(out)
quit
.endc
.end
"""

    elif circuit_id == "non_inverting_amp":
        rf_s = format_spice_val(components.get("Rf", 100e3))
        rg_s = format_spice_val(components.get("Rg", 2.2e3))

        return f"""* Non-Inverting Amplifier
* Target Spec: Gain = 10 (+-2%), Bandwidth >= 50 kHz

{OPAMP_SUBCKT}
Vin in 0 dc 0 ac 1
XOP in n_inv out 0 OPAMP_1POLE
Rf out n_inv {rf_s}
Rg n_inv 0 {rg_s}

.control
ac dec 200 10 1Meg
wrdata {out_spice_path} vdb(out)
quit
.endc
.end
"""
    else:
        raise ValueError(f"Unknown circuit_id: {circuit_id}")


def parse_components_from_netlist(netlist_text: str, circuit_id: str) -> dict:
    """Parse component values from netlist text if edited by the user."""
    target_comps = CIRCUITS[circuit_id]["broken_components"].keys()
    parsed = {}
    for line in netlist_text.splitlines():
        line = line.strip()
        if not line or line.startswith("*") or line.startswith("."):
            continue
        parts = line.split()
        if len(parts) >= 4:
            comp_name = parts[0].strip()
            # Handle R1, R2, C1, C2, Rf, Rg
            for tc in target_comps:
                if comp_name.upper() == tc.upper():
                    try:
                        val = parse_spice_val(parts[3])
                        parsed[tc] = val
                    except Exception:
                        pass
    return parsed


def simulate_circuit(circuit_id: str, components: dict, timeout: float = 3.0):
    """
    Simulate circuit with ngspice in batch mode.
    Returns (freqs, gain_db).
    """
    ngspice_bin = find_ngspice()

    with tempfile.NamedTemporaryFile(suffix=".cir", delete=False, mode="w") as f_cir:
        cir_path = f_cir.name
    with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f_out:
        out_path = f_out.name

    try:
        netlist = generate_netlist(circuit_id, components, out_file=out_path)
        with open(cir_path, "w") as f:
            f.write(netlist)

        res = subprocess.run(
            [ngspice_bin, "-b", cir_path],
            capture_output=True,
            text=True,
            timeout=timeout
        )

        if res.returncode != 0 or not os.path.exists(out_path) or os.path.getsize(out_path) == 0:
            raise RuntimeError(f"ngspice simulation failed:\n{res.stderr}\n{res.stdout}")

        data = np.loadtxt(out_path)
        if data.ndim != 2 or data.shape[1] < 2:
            raise ValueError("Corrupt simulation data returned by ngspice.")

        freqs = data[:, 0]
        gain_db = data[:, 1]
        return freqs, gain_db

    finally:
        if os.path.exists(cir_path):
            try:
                os.remove(cir_path)
            except Exception:
                pass
        if os.path.exists(out_path):
            try:
                os.remove(out_path)
            except Exception:
                pass


def measure_circuit(freqs: np.ndarray, gain_db: np.ndarray, circuit_type: str) -> dict:
    """Calculate key analog metrics from frequency and gain_db arrays."""
    dc_gain_db = float(gain_db[0])
    linear_gain = float(10.0 ** (dc_gain_db / 20.0))
    peaking_db = max(0.0, float(np.max(gain_db) - dc_gain_db))

    # Calculate -3 dB cutoff frequency relative to DC gain
    target_3db = dc_gain_db - 3.0103
    idx = np.where(gain_db <= target_3db)[0]
    fc_3db_hz = None
    if len(idx) > 0:
        i = idx[0]
        if i > 0:
            f0, f1 = freqs[i - 1], freqs[i]
            g0, g1 = gain_db[i - 1], gain_db[i]
            # Log-frequency interpolation for precision
            fc_3db_hz = float(f0 * ((f1 / f0) ** ((target_3db - g0) / (g1 - g0))))
        else:
            fc_3db_hz = float(freqs[0])
    else:
        fc_3db_hz = float(freqs[-1])

    return {
        "dc_gain_db": dc_gain_db,
        "linear_gain": linear_gain,
        "peaking_db": peaking_db,
        "fc_3db_hz": fc_3db_hz,
        "bandwidth_hz": fc_3db_hz
    }


def evaluate_spec(circuit_id: str, measurements: dict, specs: dict = None) -> tuple[bool, list]:
    """
    Compare measurements against specs.
    Returns (all_passed: bool, metrics_table: list[dict]).
    """
    if specs is None:
        specs = CIRCUITS[circuit_id]["default_specs"]

    metrics = []
    all_passed = True

    if circuit_id == "sallen_key":
        # Spec 1: Cutoff frequency fc
        fc_target = specs.get("fc_target", 1000.0)
        fc_tol = specs.get("fc_tol", 0.05)
        fc_min = fc_target * (1.0 - fc_tol)
        fc_max = fc_target * (1.0 + fc_tol)
        meas_fc = measurements.get("fc_3db_hz", 0.0)
        fc_pass = (meas_fc is not None) and (fc_min <= meas_fc <= fc_max)
        if not fc_pass:
            all_passed = False
        metrics.append({
            "name": "Cutoff Frequency (fc)",
            "measured": meas_fc,
            "measured_str": f"{meas_fc:.1f} Hz" if meas_fc else "N/A",
            "target_str": f"{fc_target:.0f} Hz (+-{fc_tol*100:.0f}%)",
            "range_str": f"{fc_min:.1f} - {fc_max:.1f} Hz",
            "passed": fc_pass
        })

        # Spec 2: Peaking
        peak_max = specs.get("peaking_max", 0.5)
        meas_peak = measurements.get("peaking_db", 0.0)
        peak_pass = meas_peak <= peak_max
        if not peak_pass:
            all_passed = False
        metrics.append({
            "name": "Passband Peaking",
            "measured": meas_peak,
            "measured_str": f"{meas_peak:.2f} dB",
            "target_str": f"<= {peak_max:.1f} dB (Butterworth)",
            "range_str": f"<= {peak_max:.2f} dB",
            "passed": peak_pass
        })

        # Spec 3: DC Gain
        dc_target = specs.get("dc_gain_target", 0.0)
        dc_tol = specs.get("dc_gain_tol", 0.5)
        dc_min = dc_target - dc_tol
        dc_max = dc_target + dc_tol
        meas_dc = measurements.get("dc_gain_db", 0.0)
        dc_pass = (dc_min <= meas_dc <= dc_max)
        if not dc_pass:
            all_passed = False
        metrics.append({
            "name": "DC Gain",
            "measured": meas_dc,
            "measured_str": f"{meas_dc:.2f} dB",
            "target_str": f"{dc_target:.1f} dB (+-{dc_tol:.1f} dB)",
            "range_str": f"{dc_min:.1f} to {dc_max:.1f} dB",
            "passed": dc_pass
        })

    elif circuit_id == "non_inverting_amp":
        # Spec 1: Linear Gain
        gain_target = specs.get("gain_target", 10.0)
        gain_tol = specs.get("gain_tol", 0.02)
        gain_min = gain_target * (1.0 - gain_tol)
        gain_max = gain_target * (1.0 + gain_tol)
        meas_gain = measurements.get("linear_gain", 0.0)
        gain_pass = (gain_min <= meas_gain <= gain_max)
        if not gain_pass:
            all_passed = False
        metrics.append({
            "name": "Closed-Loop Gain",
            "measured": meas_gain,
            "measured_str": f"{meas_gain:.2f}x ({measurements.get('dc_gain_db', 0):.2f} dB)",
            "target_str": f"{gain_target:.1f}x (+-{gain_tol*100:.0f}%)",
            "range_str": f"{gain_min:.2f} - {gain_max:.2f}x",
            "passed": gain_pass
        })

        # Spec 2: -3 dB Bandwidth
        bw_min = specs.get("bw_min", 50000.0)
        meas_bw = measurements.get("bandwidth_hz", 0.0)
        bw_pass = (meas_bw is not None) and (meas_bw >= bw_min)
        if not bw_pass:
            all_passed = False
        metrics.append({
            "name": "-3 dB Bandwidth",
            "measured": meas_bw,
            "measured_str": f"{meas_bw/1e3:.1f} kHz" if meas_bw else "N/A",
            "target_str": f">= {bw_min/1e3:.0f} kHz",
            "range_str": f">= {bw_min/1e3:.1f} kHz",
            "passed": bw_pass
        })

    return all_passed, metrics
