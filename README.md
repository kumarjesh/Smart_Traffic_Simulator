# Smart Traffic Management System (Eclipse SUMO + Python TraCI)

An intelligent 4-way traffic junction simulation system powered by **Eclipse SUMO** and **Python (TraCI)** featuring adaptive signal control, sensor density estimation, emergency vehicle preemption, transit priority, weather forecasting integration, and a real-time interactive web dashboard.

---

## Features

1. **Automated Emergency Preemption**:
   - Detects incoming ambulances within 140m.
   - Automatically overrides active signals through a safe transition phase and holds the green light until the ambulance clears the intersection.
2. **Transit Signal Priority (TSP)**:
   - Detects approaching transit buses within 80m.
   - Extends the green light by **+5.0 seconds** or accelerates red-to-green transitions so buses do not experience stop-and-go delays.
3. **Radar / Thermal 100m Approach Density**:
   - Simulates spatial vehicle detection across 100-meter approach corridors on North, South, East, and West arms.
   - Dynamically calculates green light splits based on real-time vehicle density ratios.
4. **Predictive Weather Integration**:
   - Toggle for `heavy_rain`.
   - Increases yellow clearance buffer time by **+2.0 seconds** (from 3.0s to 5.0s) and automatically throttles road speed limits from 50 km/h to 35 km/h for wet asphalt safety.
5. **Real-Time Interactive Web Dashboard**:
   - Top-down 2D canvas showing animated cars, buses, and ambulances with flashing sirens.
   - Live telemetry ribbon and color-coded event log console.
   - Manual injection buttons to test emergency preemption, TSP extensions, and rain toggling interactively.

---

## Quick Start

### 1. Launch Interactive Web Dashboard
```powershell
python -m uvicorn web.server:app --host 127.0.0.1 --port 8000
```
Open **[http://127.0.0.1:8000](http://127.0.0.1:8000)** in your browser.

### 2. Run CLI Mode with Color Logs
```powershell
python run_simulation.py --steps 300 --delay 0.02
```

### 3. Run with Desktop SUMO-GUI
```powershell
python run_simulation.py --gui --steps 300
```
