# ⚡ Analog Circuit Fixer

**Analog Circuit Fixer** is an autonomous analog circuit debugging and optimization web application built in Python using Streamlit, ngspice, Plotly, and SciPy.

The user selects a broken analog circuit netlist and a performance specification. The application simulates the circuit in **ngspice**, diagnoses failure root causes using an **LLM** (or cached expert demo rules), runs a **numerical optimizer** with SPICE in the loop, snaps components to **commercial E-series values** (E24 resistors, E12 capacitors), and re-simulates to confirm compliance.

> **Key Rule:** The LLM never claims success. Only the simulation result decides pass/fail.

---

## 🛠️ Supported Circuits & Templates

### 1. Sallen-Key 2nd-Order Low-Pass Filter (Unity Gain)
* **Target Specifications:**
  * Cutoff frequency $f_c = 1.0\text{ kHz}$ ($\pm 5\%$, $950\text{ to }1050\text{ Hz}$)
  * Passband Peaking $\le 0.5\text{ dB}$ (Butterworth response, $Q \approx 0.707$)
  * DC Gain $0.0\text{ dB}$ ($\pm 0.5\text{ dB}$)
* **Broken Preset:**
  * $R_1 = 7.5\text{ k}\Omega, R_2 = 7.5\text{ k}\Omega, C_1 = 68\text{ nF}, C_2 = 6.8\text{ nF}$
  * Causes $f_c \approx 1.42\text{ kHz}$ and severe $\approx 4.45\text{ dB}$ resonant peaking ($Q \approx 1.58$).

### 2. Non-Inverting Amplifier
* **Target Specifications:**
  * Linear Gain $= 10.0$ ($\pm 2\%$, $9.8\text{ to }10.2\times$, $20\text{ dB}$)
  * $-3\text{ dB}$ Bandwidth $\ge 50\text{ kHz}$
* **Broken Preset:**
  * $R_f = 100\text{ k}\Omega, R_g = 2.2\text{ k}\Omega$
  * Causes gain $\approx 46.5\times$ ($33.3\text{ dB}$) and bandwidth drop to $\approx 21.5\text{ kHz}$ due to op-amp GBW limits.

### Op-Amp Macro Model
Uses a realistic single-pole macro model (`OPAMP_1POLE`) with:
* DC Gain $A_0 = 10^5$ ($100\text{ dB}$)
* Gain-Bandwidth Product $\text{GBW} = 1.0\text{ MHz}$ (dominant pole at $f_p = 10\text{ Hz}$)
* Avoids ideal op-amps so real-world gain-bandwidth limitations are captured.

---

## 🚀 Quickstart

### 1. Prerequisites
* Python 3.10+
* `ngspice` installed and available in PATH (or `C:\Spice64\bin\ngspice_con.exe` / `C:\Spice64\bin\ngspice.exe` on Windows).

#### Installing ngspice:
* **Windows:**
  * Download portable zip from [ngspice sourceforge](https://sourceforge.net/projects/ngspice/files/ng-spice-rework/) and extract `Spice64` to `C:\` or your user folder (`C:\Users\<username>\Spice64\bin`).
  * Or install via Chocolatey: `choco install ngspice -y`
* **Ubuntu/Debian:** `sudo apt-get install ngspice`
* **macOS:** `brew install ngspice`

### 2. Install Python Dependencies
```bash
pip install -r requirements.txt
```

### 3. Run the Headless Test
Verifies end-to-end operation with the Sallen-Key broken preset in headless mode:
```bash
python test_headless.py
```

### 4. Launch the Web Application
```bash
streamlit run app.py
```
Open your browser at `http://localhost:8501`.

---

## 🤖 LLM & Demo Mode Configuration

The application includes a **Cached Demo Mode** that runs deterministically with zero external API dependencies:
* Set `DEMO=1` in your environment or leave the API Key field blank in the sidebar to run in Demo Mode.
* To use a live LLM:
  ```bash
  export LLM_API_KEY="your-api-key"
  # Optional: custom provider or model
  export LLM_BASE_URL="https://api.openai.com/v1"
  export LLM_MODEL="gpt-4o-mini"
  ```
  Or input your API key directly in the Streamlit sidebar.

---

## 📂 Project Architecture

```
PPVC/
├── app.py             # Streamlit UI (wide layout, Plotly Bode plot, netlist diff, BOM)
├── spice.py           # Circuit templates, SPICE netlist generation, ngspice execution, E-series snapping
├── agent.py           # Unified LLM provider, SciPy Nelder-Mead optimizer, agent loop
├── test_headless.py   # Headless automated test for Sallen-Key broken preset
├── requirements.txt   # Python package dependencies
└── README.md          # Documentation and run steps
```

---

## 🔬 How the Agent Loop Works

1. **Simulation:** Runs batch `ngspice -b` with `.control` block AC sweep ($10\text{ Hz}$ to $1\text{ MHz}$, 200 pts/dec) and parses output using `numpy`.
2. **Measurement & Verification:** Calculates DC gain, $-3\text{ dB}$ cutoff/bandwidth, and peaking. Evaluates against tolerances.
3. **LLM Diagnosis:** If failing, prompts the LLM to output pure JSON containing failure diagnosis, components to tune, search bounds, and rationale.
4. **Numerical Optimization:** Runs `scipy.optimize.minimize` (Nelder-Mead) over $\log_{10}$ of component values with SPICE simulation in the loop.
5. **Commercial Snapping:** Snaps resistors to the **E24 series** ($\pm 5\%$) and capacitors to the **E12 series** ($\pm 10\%$), performing fine neighbor checks if necessary.
6. **Pass/Fail Decision:** Re-simulates the final circuit and compares against specifications. Stops on PASS or maximum 4 iterations.
