# ⚡ Circuit Assistant (Analog Circuit Fixer)

**Circuit Assistant** is an instrument-grade, autonomous analog circuit design, physical SPICE simulation, and component repair application. Built for electronics engineers and students, it features a **"Lab Bench at Night"** dark instrument aesthetic, CRT oscilloscope visualizations, live blueprint schematics, and an autonomous optimization pipeline.

The user describes a circuit requirement in plain English (or clicks an example prompt). The application translates the requirement into circuit specifications, executes high-fidelity **ngspice** simulations, diagnoses failure modes with **Google Gemini** (or offline engineering heuristics), executes a **numerical optimizer** with SPICE in the loop, and snaps components to standard **commercial E-series values** (E24 resistors, E12 capacitors).

> **Key Rule:** The AI never claims success on its own. Only physical SPICE simulation results decide pass or fail.

---

## 🎨 Interface & Design Language: "Lab Bench at Night"

The user interface feels like a high-end oscilloscope and benchtop instrument rather than a generic dashboard:
* **Hardware Color Palette:** Deep CRT background (`#070A0D`), dark instrument panels (`#0E1419`), panel borders (`#1B2A33`), PCB copper traces (`#C8742B`), phosphor green readouts (`#39FF88`), scope amber (`#FFB000`), signal cyan (`#35D0FF`), and fail red (`#FF4D5E`).
* **Instrument Typography:** Google Fonts `@import` featuring **Space Grotesk** (headings and chassis labels), **JetBrains Mono** (labels, netlists, and code), and **Share Tech Mono** (high-visibility digital readouts).
* **Subtle PCB Background:** Inline SVG data-URI with thin 45°/90° copper traces and circular via pads at low opacity with a graticule grid.
* **Front Panel Sidebar:** Styled like an instrument rack faceplate with a custom vector logo (sine wave through resistor zigzag), status LEDs, and a **Verified Mode** solver switch.
* **Status Lamps & 7-Segment Displays:** Large verified verdict banners, 7-segment readouts with deltas, and silkscreen chassis labels (`CH1`, `DUT`, `BODE`).

---

## 🔬 Signature Instrument Components

1. **Oscilloscope Bode View (Hero Component):**
   * HTML5 Canvas CRT with a 10×8 graticule, minor tick marks, rounded bezel, scanline overlay, and phosphor glow.
   * Sweeps in the broken response in amber/red over 1.2s, followed by the phosphor green fixed curve.
   * Features a vertical dashed `TARGET fc` cursor, horizontal `-3 dB` reference line, and interactive mouse-hover crosshair HUD.
2. **Live Blueprint Schematic:**
   * Inline SVG schematic (op-amp, resistors, capacitors, ground symbols, and terminals).
   * Displays live component values. When repaired, changed parts flash amber and morph to their commercial values.
   * A glowing cyan electron particle continuously loops along the signal path.
3. **PCB Pipeline Strip:**
   * 4-station PCB trace route: `SIMULATE` ➔ `DIAGNOSE (AI)` ➔ `OPTIMIZE` ➔ `VERIFY`.
   * Displays traveling copper pulses, active state LEDs (amber when active, phosphor green when done), and real-time captioning.
4. **Signal Cleanup View (Time-Domain Scopes):**
   * Three stacked mini CRT scopes: **What goes in** (grey), **Before fix** (amber/red), and **After fix** (phosphor green).
   * Demonstrates how the repaired circuit removes noise and distortion in real time.
5. **Firmware Boot Sequence:**
   * Terminal typeout on empty state (<2s) testing ngspice, optimizer, and AI engine status with an idling phosphor sine wave.

---

## 🛠️ Supported Circuit Templates

### 1. Sallen-Key 2nd-Order Low-Pass Filter (Unity Gain)
* **What it does:** Passes desirable low frequencies freely while cutting off unwanted high-frequency noise and hiss.
* **Target Specifications:**
  * Cutoff frequency $f_c = 1.0\text{ kHz}$ ($\pm 5\%$, $950\text{ to }1050\text{ Hz}$)
  * Passband Peaking $\le 0.5\text{ dB}$ (Butterworth response, $Q \approx 0.707$)
  * DC Gain $0.0\text{ dB}$ ($\pm 0.5\text{ dB}$)
* **Broken Preset:**
  * $R_1 = 7.5\text{ k}\Omega, R_2 = 7.5\text{ k}\Omega, C_1 = 68\text{ nF}, C_2 = 6.8\text{ nF}$
  * Causes $f_c \approx 1.42\text{ kHz}$ and severe $\approx 4.45\text{ dB}$ resonant peaking ($Q \approx 1.58$).

### 2. Non-Inverting Amplifier
* **What it does:** Cleanly amplifies a weak input voltage to a stronger output voltage without inverting polarity.
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

---

## 🤖 Google Gemini AI & Offline Demo Mode

The application uses Google Gemini via the official `google-genai` SDK:
* Automatically loads configuration from `.env` via `python-dotenv`.
* Structured JSON mode (`response_mime_type="application/json"`) for circuit design and diagnosis.
* Strict 8-second timeout enforcement.
* **Offline Demo Mode:** If `GEMINI_API_KEY` is absent, `DEMO=1` is set, or a network timeout/error occurs, the app silently and instantly falls back to rule-based engineering heuristics.
* The sidebar displays a status indicator: `AI: Gemini online` or `AI: offline demo mode`.

### Configuration (`.env`)
Create a `.env` file in the root directory (see `.env.example`):
```env
GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_MODEL=gemini-2.5-flash
DEMO=0
```

---

## 🚀 Quickstart

### 1. Prerequisites
* Python 3.10+
* `ngspice` installed and available in PATH (or `C:\Spice64\bin\ngspice_con.exe` on Windows).

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Run Headless Verification Test
Verifies end-to-end SPICE simulation, Nelder-Mead optimization, and E-series snapping:
```bash
python test_headless.py
```

### 4. Launch the Web Application
```bash
streamlit run app.py
```
Open your browser at `http://localhost:8501`.

---

## 📂 Project Architecture

```
PPVC/
├── app.py             # Main Streamlit app (Instrument shell, chat front door, metric displays)
├── theme.py           # "Lab Bench at Night" CSS variables, PCB background, tactile styles
├── components.py      # Custom CRT oscilloscope, live schematic SVG, pipeline strip, boot console
├── spice.py           # Netlist generators, ngspice simulation runner, measurement & E-series logic
├── agent.py           # Google Gemini provider, SciPy Nelder-Mead optimizer, autonomous agent loop
├── test_headless.py   # Headless automated regression test
├── requirements.txt   # Package dependencies
├── .env.example       # Example environment variables
├── .gitignore         # Git ignore rules (.env, __pycache__)
└── README.md          # Project documentation
```
