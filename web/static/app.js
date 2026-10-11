// Smart Traffic Junction Simulation - Indian Left-Hand Traffic (3-Lane Dedicated Slip Lanes)
const canvas = document.getElementById('traffic-canvas');
const ctx = canvas.getContext('2d');
const tooltipEl = document.getElementById('veh-tooltip');
const canvasWrapper = document.getElementById('canvas-wrapper');

let ws = null;
let latestState = null;
let currentSpeed = 1.0;
let isPaused = false;
let rainActive = false;

// Viewport Zoom & Pan State (Default 1.75x zoomed to display full 250m approaches in all 4 directions)
let zoomLevel = 1.75;
let panOffset = { x: 0, y: 0 };
let isDragging = false;
let dragStart = { x: 0, y: 0 };
let hoveredVehicle = null;

// Dynamic Responsive Canvas Resizing
function resizeCanvas() {
    if (canvasWrapper) {
        canvas.width = canvasWrapper.clientWidth;
        canvas.height = canvasWrapper.clientHeight;
    }
}
window.addEventListener('resize', resizeCanvas);
resizeCanvas();

// UI Handles
const simClockEl = document.getElementById('sim-clock');
const vehCountEl = document.getElementById('veh-count');
const btnPause = document.getElementById('btn-pause');
const btnSpeed = document.getElementById('btn-speed');
const btnWeather = document.getElementById('btn-toggle-weather');

const cardPreempt = document.getElementById('card-preemption');
const badgePreempt = document.getElementById('badge-preemption');
const preemptCorridorEl = document.getElementById('preempt-corridor');
const preemptUnitEl = document.getElementById('preempt-unit');

const cardTsp = document.getElementById('card-tsp');
const badgeTsp = document.getElementById('badge-tsp');
const tspModeEl = document.getElementById('tsp-mode');

const nsDensityVal = document.getElementById('ns-density-val');
const ewDensityVal = document.getElementById('ew-density-val');
const nsGreenVal = document.getElementById('ns-green-val');
const ewGreenVal = document.getElementById('ew-green-val');
const nsDensityFill = document.getElementById('ns-density-fill');

const cardWeather = document.getElementById('card-weather');
const badgeWeather = document.getElementById('badge-weather');
const weatherSpeedEl = document.getElementById('weather-speed');
const weatherYellowEl = document.getElementById('weather-yellow');
const weatherIconEl = document.getElementById('weather-icon');

const signalPhaseBadge = document.getElementById('signal-phase-badge');
const signalTimerBadge = document.getElementById('signal-timer-badge');
const logContainer = document.getElementById('log-container');

// Connect WebSocket
function connectWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws`;
    ws = new WebSocket(wsUrl);

    ws.onopen = () => console.log('[WS] Connected to 3-Lane Indian LHD Simulation Server');
    ws.onmessage = (event) => {
        try {
            latestState = JSON.parse(event.data);
            updateDashboard(latestState);
        } catch (e) {
            console.error('[WS Parse Error]', e);
        }
    };
    ws.onclose = () => {
        console.warn('[WS] Reconnecting in 2s...');
        setTimeout(connectWebSocket, 2000);
    };
}

// User Actions
function toggleWeather() {
    rainActive = !rainActive;
    if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ action: 'toggle_weather', heavy_rain: rainActive }));
    }
}

function spawnVehicle(vtype, origin, destination) {
    if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ action: 'spawn_vehicle', vtype: vtype, origin: origin, destination: destination }));
    }
}

btnPause.addEventListener('click', () => {
    isPaused = !isPaused;
    btnPause.innerText = isPaused ? '▶ Resume' : '⏸ Pause';
    if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ action: 'pause_resume' }));
    }
});

btnSpeed.addEventListener('click', () => {
    const speeds = [1.0, 2.0, 4.0];
    const nextIdx = (speeds.indexOf(currentSpeed) + 1) % speeds.length;
    currentSpeed = speeds[nextIdx];
    btnSpeed.innerText = `⚡ ${currentSpeed}x Speed`;
    if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ action: 'set_speed', speed: currentSpeed }));
    }
});

function clearLogs() { logContainer.innerHTML = ''; }

// Zoom & Pan Functions
function zoomIn() { zoomLevel = Math.min(8.0, zoomLevel * 1.3); }
function zoomOut() { zoomLevel = Math.max(1.0, zoomLevel / 1.3); }
function resetZoom() { zoomLevel = 1.75; panOffset = { x: 0, y: 0 }; }

// Canvas Mouse Drag & Wheel
canvas.addEventListener('wheel', (e) => {
    e.preventDefault();
    const zoomFactor = e.deltaY < 0 ? 1.15 : 0.85;
    zoomLevel = Math.max(1.0, Math.min(8.0, zoomLevel * zoomFactor));
});

canvas.addEventListener('mousedown', (e) => {
    isDragging = true;
    dragStart = { x: e.clientX - panOffset.x, y: e.clientY - panOffset.y };
});

window.addEventListener('mousemove', (e) => {
    if (isDragging) {
        panOffset.x = e.clientX - dragStart.x;
        panOffset.y = e.clientY - dragStart.y;
    }

    if (latestState && latestState.vehicles) {
        const rect = canvas.getBoundingClientRect();
        const mouseX = e.clientX - rect.left;
        const mouseY = e.clientY - rect.top;

        let found = null;
        for (const veh of latestState.vehicles) {
            const p = toCanvas(veh.x, veh.y);
            const dist = Math.hypot(p.x - mouseX, p.y - mouseY);
            if (dist < 18 * (zoomLevel / 2.5)) {
                found = { ...veh, screenX: mouseX, screenY: mouseY };
                break;
            }
        }

        if (found) {
            hoveredVehicle = found;
            tooltipEl.style.display = 'block';
            tooltipEl.style.left = `${found.screenX + 14}px`;
            tooltipEl.style.top = `${found.screenY - 10}px`;
            tooltipEl.innerHTML = `
                <div><strong>ID:</strong> ${found.id}</div>
                <div><strong>Type:</strong> ${found.type.toUpperCase()}</div>
                <div><strong>Speed:</strong> ${found.speed} km/h</div>
                <div><strong>Approach:</strong> ${found.edge}</div>
            `;
        } else {
            hoveredVehicle = null;
            tooltipEl.style.display = 'none';
        }
    }
});

window.addEventListener('mouseup', () => isDragging = false);

// Dashboard Telemetry Updates
function updateDashboard(state) {
    if (!state) return;

    const mins = Math.floor(state.sim_time / 60);
    const secs = (state.sim_time % 60).toFixed(1);
    simClockEl.innerText = `${mins.toString().padStart(2, '0')}:${secs.padStart(4, '0')}`;
    vehCountEl.innerText = state.vehicle_count;

    // Emergency Preemption
    if (state.preemption_active) {
        cardPreempt.classList.add('active-alert');
        badgePreempt.className = 'badge badge-emergency';
        badgePreempt.innerText = 'OVERRIDE ACTIVE';
        preemptCorridorEl.innerText = `${state.preempted_corridor} CORRIDOR`;
        preemptUnitEl.innerText = state.active_ambulance_id || 'Ambulance Unit';
    } else {
        cardPreempt.classList.remove('active-alert');
        badgePreempt.className = 'badge badge-idle';
        badgePreempt.innerText = 'IDLE';
        preemptCorridorEl.innerText = 'None';
        preemptUnitEl.innerText = 'None';
    }

    // Transit Signal Priority (TSP)
    const hasActiveBuses = state.active_buses && state.active_buses.length > 0;
    if (hasActiveBuses) {
        cardTsp.classList.add('active-tsp');
        badgeTsp.className = 'badge badge-tsp';
        badgeTsp.innerText = 'TSP ACTIVE';
        tspModeEl.innerText = `Priority granted (${state.active_buses.length} Bus)`;
    } else {
        cardTsp.classList.remove('active-tsp');
        badgeTsp.className = 'badge badge-idle';
        badgeTsp.innerText = 'IDLE';
        tspModeEl.innerText = 'Monitoring (80m zone)';
    }

    // Radar Density
    if (state.radar_density && state.calculated_green) {
        const n = state.radar_density.North || 0;
        const s = state.radar_density.South || 0;
        const e = state.radar_density.East || 0;
        const w = state.radar_density.West || 0;
        nsDensityVal.innerText = `S:${s} N:${n}`;
        ewDensityVal.innerText = `E:${e} W:${w}`;
        
        const currentArm = state.current_phase.split('_')[0];
        const armKey = currentArm.charAt(0) + currentArm.slice(1).toLowerCase();
        const activeSec = state.calculated_green[armKey] || state.target_green || 12.0;
        nsGreenVal.innerText = `${activeSec}s`;
        ewGreenVal.innerText = `${currentArm}`;

        const total = Math.max(1, n + s + e + w);
        const activeVeh = (state.radar_density[armKey] || 0);
        const pct = Math.round((activeVeh / total) * 100);
        nsDensityFill.style.width = `${Math.max(15, pct)}%`;
    }

    // Weather
    rainActive = state.heavy_rain;
    if (state.heavy_rain) {
        cardWeather.classList.add('active-rain');
        badgeWeather.className = 'badge badge-rain';
        badgeWeather.innerText = 'HEAVY RAIN';
        weatherIconEl.innerText = '🌧️';
        weatherSpeedEl.innerText = '35 km/h (Reduced)';
        weatherYellowEl.innerText = `${state.yellow_duration}s (+2s Buffer)`;
        btnWeather.classList.add('active-rain-btn');
        btnWeather.innerText = '☀️ Switch to Clear Weather';
    } else {
        cardWeather.classList.remove('active-rain');
        badgeWeather.className = 'badge badge-clear';
        badgeWeather.innerText = 'CLEAR';
        weatherIconEl.innerText = '☀️';
        weatherSpeedEl.innerText = '50 km/h';
        weatherYellowEl.innerText = `${state.yellow_duration}s (Normal)`;
        btnWeather.classList.remove('active-rain-btn');
        btnWeather.innerText = '🌧️ Activate Heavy Rain (+2s Yellow)';
    }

    // Active Signal Indicator
    signalPhaseBadge.innerText = state.current_phase.replace('_', ' ');
    if (state.current_phase.includes('GREEN')) {
        signalPhaseBadge.className = 'signal-badge signal-green-badge';
        signalTimerBadge.innerText = `${state.phase_timer.toFixed(1)}s / ${state.target_green.toFixed(1)}s`;
    } else if (state.current_phase.includes('YELLOW')) {
        signalPhaseBadge.className = 'signal-badge signal-yellow-badge';
        signalTimerBadge.innerText = `${state.phase_timer.toFixed(1)}s / ${state.yellow_duration.toFixed(1)}s`;
    } else {
        signalPhaseBadge.className = 'signal-badge signal-red-badge';
        signalTimerBadge.innerText = `${state.phase_timer.toFixed(1)}s`;
    }

    // Event Logs
    if (state.recent_logs && state.recent_logs.length > 0) {
        renderLogs(state.recent_logs);
    }
}

function renderLogs(logs) {
    logContainer.innerHTML = '';
    logs.forEach(log => {
        const item = document.createElement('div');
        const catClass = log.category ? log.category.toLowerCase() : 'info';
        item.className = `log-item ${catClass}`;
        item.innerHTML = `<span class="log-time">[${log.time}]</span> <span class="log-cat">[${log.category.toUpperCase()}]</span> <span>${log.message}</span>`;
        logContainer.appendChild(item);
    });
    logContainer.scrollTop = logContainer.scrollHeight;
}

// -------------------------------------------------------------
// Coordinate Mapping with Dynamic Zoom & Pan
// -------------------------------------------------------------
const BASE_CENTER_X = 250.0;
const BASE_CENTER_Y = 250.0;

function toCanvas(sx, sy) {
    const cx = canvas.width / 2;
    const cy = canvas.height / 2;
    const baseScale = (Math.min(canvas.width, canvas.height) / 500.0) * zoomLevel;

    const screenX = cx + (sx - BASE_CENTER_X) * baseScale + panOffset.x;
    const screenY = cy - (sy - BASE_CENTER_Y) * baseScale + panOffset.y; // Invert Y
    return { x: screenX, y: screenY, scale: baseScale };
}

// Canvas 2D Intersection Renderer
function renderCanvas() {
    requestAnimationFrame(renderCanvas);
    if (!canvas.width || !canvas.height) return;

    ctx.clearRect(0, 0, canvas.width, canvas.height);
    const scale = (Math.min(canvas.width, canvas.height) / 500.0) * zoomLevel;
    const pCenter = toCanvas(250.0, 250.0);

    // 1. Background Ground
    ctx.fillStyle = '#080c14';
    ctx.fillRect(0, 0, canvas.width, canvas.height);

    // 2. Continuous Clean Asphalt Roadways
    ctx.fillStyle = '#151d2a';
    
    // NS Road: X in [240.4, 259.6]
    const pNS_l = toCanvas(240.4, 250.0);
    const pNS_r = toCanvas(259.6, 250.0);
    const roadNS_w = Math.abs(pNS_r.x - pNS_l.x);
    ctx.fillRect(pNS_l.x, 0, roadNS_w, canvas.height);

    // EW Road: Y in [240.4, 259.6]
    const pEW_t = toCanvas(250.0, 259.6);
    const pEW_b = toCanvas(250.0, 240.4);
    const roadEW_h = Math.abs(pEW_b.y - pEW_t.y);
    ctx.fillRect(0, pEW_t.y, canvas.width, roadEW_h);

    // 3. Wide Smooth Corner Slip Turn Curves (Clean asphalt connection for all 4 corners)
    const pJ_tl = toCanvas(215.4, 284.6);
    const pJ_br = toCanvas(284.6, 215.4);
    const jBoxW = Math.abs(pJ_br.x - pJ_tl.x);
    const jBoxH = Math.abs(pJ_br.y - pJ_tl.y);
    ctx.fillRect(pJ_tl.x, pJ_tl.y, jBoxW, jBoxH);

    // Crisp Outer Curb Borders
    ctx.strokeStyle = 'rgba(255, 255, 255, 0.18)';
    ctx.lineWidth = 1.8;
    // North outer curbs
    ctx.beginPath(); ctx.moveTo(pNS_l.x, 0); ctx.lineTo(pNS_l.x, pJ_tl.y); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(pNS_r.x, 0); ctx.lineTo(pNS_r.x, pJ_tl.y); ctx.stroke();
    // South outer curbs
    ctx.beginPath(); ctx.moveTo(pNS_l.x, canvas.height); ctx.lineTo(pNS_l.x, pJ_br.y); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(pNS_r.x, canvas.height); ctx.lineTo(pNS_r.x, pJ_br.y); ctx.stroke();
    // West outer curbs
    ctx.beginPath(); ctx.moveTo(0, pEW_t.y); ctx.lineTo(pJ_tl.x, pEW_t.y); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(0, pEW_b.y); ctx.lineTo(pJ_tl.x, pEW_b.y); ctx.stroke();
    // East outer curbs
    ctx.beginPath(); ctx.moveTo(canvas.width, pEW_t.y); ctx.lineTo(pJ_br.x, pEW_t.y); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(canvas.width, pEW_b.y); ctx.lineTo(pJ_br.x, pEW_b.y); ctx.stroke();

    // 4. Draw 100m Radar Detection Zones
    ctx.save();
    ctx.fillStyle = 'rgba(0, 240, 255, 0.08)';
    ctx.strokeStyle = 'rgba(0, 240, 255, 0.45)';
    ctx.lineWidth = 1.5;
    ctx.setLineDash([4, 4]);

    const drawRadarBox = (x1, y1, x2, y2) => {
        const p1 = toCanvas(x1, y1);
        const p2 = toCanvas(x2, y2);
        const rx = Math.min(p1.x, p2.x);
        const ry = Math.min(p1.y, p2.y);
        const rw = Math.abs(p2.x - p1.x);
        const rh = Math.abs(p2.y - p1.y);
        ctx.fillRect(rx, ry, rw, rh);
        ctx.strokeRect(rx, ry, rw, rh);
    };

    drawRadarBox(250.0, 384.6, 259.6, 284.6); // North Radar
    drawRadarBox(240.4, 215.4, 250.0, 115.4); // South Radar
    drawRadarBox(284.6, 250.0, 384.6, 240.4); // East Radar
    drawRadarBox(115.4, 259.6, 215.4, 250.0); // West Radar
    ctx.restore();

    // 5. Center Medians (Yellow double line at X=250.0 and Y=250.0)
    ctx.save();
    ctx.strokeStyle = '#f59e0b';
    ctx.lineWidth = Math.max(2, 1.2 * (zoomLevel / 2.0));

    // North Median
    ctx.beginPath(); ctx.moveTo(pCenter.x, 0); ctx.lineTo(pCenter.x, pJ_tl.y); ctx.stroke();
    // South Median
    ctx.beginPath(); ctx.moveTo(pCenter.x, canvas.height); ctx.lineTo(pCenter.x, pJ_br.y); ctx.stroke();
    // West Median
    ctx.beginPath(); ctx.moveTo(0, pCenter.y); ctx.lineTo(pJ_tl.x, pCenter.y); ctx.stroke();
    // East Median
    ctx.beginPath(); ctx.moveTo(canvas.width, pCenter.y); ctx.lineTo(pJ_br.x, pCenter.y); ctx.stroke();

    // White dashed lane dividers (3 lanes: 3.2m spacing)
    ctx.strokeStyle = 'rgba(255, 255, 255, 0.4)';
    ctx.setLineDash([6, 8]);
    ctx.lineWidth = 1.2;

    const drawLine = (x1, y1, x2, y2) => {
        const p1 = toCanvas(x1, y1);
        const p2 = toCanvas(x2, y2);
        ctx.beginPath(); ctx.moveTo(p1.x, p1.y); ctx.lineTo(p2.x, p2.y); ctx.stroke();
    };

    // North lane dividers (Inbound: 253.2, 256.4 | Outbound: 246.8, 243.6)
    drawLine(253.2, 500.0, 253.2, 284.6);
    drawLine(256.4, 500.0, 256.4, 284.6);
    drawLine(246.8, 500.0, 246.8, 284.6);
    drawLine(243.6, 500.0, 243.6, 284.6);

    // South lane dividers
    drawLine(246.8, 215.4, 246.8, 0.0);
    drawLine(243.6, 215.4, 243.6, 0.0);
    drawLine(253.2, 215.4, 253.2, 0.0);
    drawLine(256.4, 215.4, 256.4, 0.0);

    // West lane dividers
    drawLine(0.0, 253.2, 215.4, 253.2);
    drawLine(0.0, 256.4, 215.4, 256.4);
    drawLine(0.0, 246.8, 215.4, 246.8);
    drawLine(0.0, 243.6, 215.4, 243.6);

    // East lane dividers
    drawLine(284.6, 246.8, 500.0, 246.8);
    drawLine(284.6, 243.6, 500.0, 243.6);
    drawLine(284.6, 253.2, 500.0, 253.2);
    drawLine(284.6, 256.4, 500.0, 256.4);
    ctx.restore();

    // 6. Draw Dedicated Indian "FREE LEFT TURN SLIP LANES" Markings & Curved Arrows
    ctx.save();
    ctx.fillStyle = 'rgba(16, 185, 129, 0.9)';
    ctx.strokeStyle = '#10b981';
    ctx.lineWidth = 2;

    const drawFreeLeftArrow = (sx, sy, angleDeg, labelText) => {
        const p = toCanvas(sx, sy);
        ctx.save();
        ctx.translate(p.x, p.y);
        ctx.rotate((angleDeg * Math.PI) / 180);

        ctx.beginPath();
        ctx.moveTo(0, 12);
        ctx.lineTo(0, -6);
        ctx.arc(-10, -6, 10, 0, Math.PI, true);
        ctx.stroke();

        ctx.beginPath();
        ctx.moveTo(-20, -6);
        ctx.lineTo(-25, -1);
        ctx.lineTo(-15, -1);
        ctx.closePath();
        ctx.fill();

        if (zoomLevel >= 2.0) {
            ctx.font = `700 ${Math.max(9, 2.6 * zoomLevel)}px 'Outfit', sans-serif`;
            ctx.fillStyle = '#34d399';
            ctx.fillText(labelText, -28, 22);
        }
        ctx.restore();
    };

    drawFreeLeftArrow(258.0, 305.0, 0, "FREE LEFT");   // North inbound dedicated slip
    drawFreeLeftArrow(242.0, 195.0, 180, "FREE LEFT"); // South inbound dedicated slip
    drawFreeLeftArrow(305.0, 242.0, 90, "FREE LEFT");  // East inbound dedicated slip
    drawFreeLeftArrow(195.0, 258.0, 270, "FREE LEFT"); // West inbound dedicated slip
    ctx.restore();

    // 7. Controlled Stoplines (Across Lanes 1 and 2; Lane 0 is dedicated free slip)
    ctx.save();
    ctx.strokeStyle = 'rgba(255, 255, 255, 0.95)';
    ctx.lineWidth = 3.5;
    drawLine(250.0, 284.6, 256.4, 284.6); // North controlled stopline
    drawLine(243.6, 215.4, 250.0, 215.4); // South controlled stopline
    drawLine(284.6, 243.6, 284.6, 250.0); // East controlled stopline
    drawLine(215.4, 250.0, 215.4, 256.4); // West controlled stopline
    ctx.restore();

    // 8. Weather Effects (Rain)
    if (latestState && latestState.heavy_rain) {
        ctx.save();
        ctx.strokeStyle = 'rgba(147, 197, 253, 0.35)';
        ctx.lineWidth = 1.2;
        const timeOffset = Date.now() * 0.3;
        for (let i = 0; i < 60; i++) {
            const rx = (i * 47 + timeOffset * 3) % canvas.width;
            const ry = (i * 67 + timeOffset * 7) % canvas.height;
            ctx.beginPath();
            ctx.moveTo(rx, ry);
            ctx.lineTo(rx - 4, ry + 14);
            ctx.stroke();
        }
        ctx.restore();
    }

    // 9. Draw Vehicles Layer
    if (latestState && latestState.vehicles) {
        latestState.vehicles.forEach(veh => {
            const p = toCanvas(veh.x, veh.y);
            if (p.x >= -60 && p.x <= canvas.width + 60 && p.y >= -60 && p.y <= canvas.height + 60) {
                const isHovered = hoveredVehicle && hoveredVehicle.id === veh.id;
                drawVehicle(p.x, p.y, veh.angle, veh.type, veh.speed, scale, isHovered);
            }
        });
    }

    // 10. ELEVATED TRAFFIC LIGHT GANTRIES (Rendered ON TOP of vehicles on sidewalks)
    if (latestState) {
        const phase = latestState.current_phase;
        let nColor = '#ff334b';
        let sColor = '#ff334b';
        let eColor = '#ff334b';
        let wColor = '#ff334b';

        if (phase === 'SOUTH_GREEN') {
            sColor = '#00e676';
        } else if (phase === 'SOUTH_YELLOW') {
            sColor = '#ffb800';
        } else if (phase === 'NORTH_GREEN') {
            nColor = '#00e676';
        } else if (phase === 'NORTH_YELLOW') {
            nColor = '#ffb800';
        } else if (phase === 'EAST_GREEN') {
            eColor = '#00e676';
        } else if (phase === 'EAST_YELLOW') {
            eColor = '#ffb800';
        } else if (phase === 'WEST_GREEN') {
            wColor = '#00e676';
        } else if (phase === 'WEST_YELLOW') {
            wColor = '#ffb800';
        }

        // Position gantries cleanly outside the road so vehicles NEVER cover them
        const gNorth = toCanvas(264.0, 292.0);
        const gSouth = toCanvas(236.0, 208.0);
        const gEast  = toCanvas(292.0, 236.0);
        const gWest  = toCanvas(208.0, 264.0);

        drawElevatedSignalGantry(gNorth.x, gNorth.y, nColor, 'NORTH SIGNAL');
        drawElevatedSignalGantry(gSouth.x, gSouth.y, sColor, 'SOUTH SIGNAL');
        drawElevatedSignalGantry(gEast.x, gEast.y, eColor, 'EAST SIGNAL');
        drawElevatedSignalGantry(gWest.x, gWest.y, wColor, 'WEST SIGNAL');
    }
}

// Elevated Signal Gantry with Black Backplate & Glowing LED Heads
function drawElevatedSignalGantry(x, y, mainColor, label) {
    ctx.save();
    const boxW = Math.max(26, 8.0 * zoomLevel);
    const boxH = Math.max(52, 16.0 * zoomLevel);
    const radius = 6;

    // Signal Mast Pole
    ctx.fillStyle = '#64748b';
    ctx.fillRect(x - 2, y, 4, 20);

    // Black Housing Backplate
    ctx.fillStyle = '#0a0f1d';
    ctx.strokeStyle = '#00f0ff';
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    ctx.roundRect(x - boxW / 2, y - boxH, boxW, boxH, radius);
    ctx.fill();
    ctx.stroke();

    const bulbR = Math.max(4.0, 1.3 * zoomLevel);
    const bulbSpacing = boxH / 4;

    // 1. Red Bulb
    const isRed = mainColor === '#ff334b';
    drawSignalBulb(x, y - boxH + bulbSpacing, isRed ? '#ff334b' : '#33151b', bulbR, isRed);

    // 2. Yellow Bulb
    const isYellow = mainColor === '#ffb800';
    drawSignalBulb(x, y - boxH + bulbSpacing * 2, isYellow ? '#ffb800' : '#332700', bulbR, isYellow);

    // 3. Green Bulb (Main)
    const isGreen = mainColor === '#00e676';
    drawSignalBulb(x, y - boxH + bulbSpacing * 3, isGreen ? '#00e676' : '#002914', bulbR, isGreen);

    // Label on Gantry
    if (zoomLevel >= 1.8) {
        ctx.font = `700 ${Math.max(9, 2.5 * zoomLevel)}px 'Outfit', sans-serif`;
        ctx.fillStyle = '#f8fafc';
        ctx.shadowColor = '#000000';
        ctx.shadowBlur = 6;
        ctx.fillText(label, x - boxW / 2 - 12, y - boxH - 6);
    }
    ctx.restore();
}

function drawSignalBulb(bx, by, color, r, isLit) {
    ctx.save();
    ctx.beginPath();
    ctx.arc(bx, by, r, 0, Math.PI * 2);
    ctx.fillStyle = color;
    if (isLit) {
        ctx.shadowColor = color;
        ctx.shadowBlur = 18;
    }
    ctx.fill();
    ctx.strokeStyle = 'rgba(255, 255, 255, 0.4)';
    ctx.lineWidth = 1;
    ctx.stroke();
    ctx.restore();
}

function drawVehicle(x, y, angleDeg, type, speed, scale, isHovered) {
    ctx.save();
    ctx.translate(x, y);
    ctx.rotate((angleDeg * Math.PI) / 180);

    let vWidth = 2.0 * scale;
    let vLength = 4.4 * scale;
    let fillColor = '#ffd028';
    let strokeColor = '#b45309';

    if (type === 'ambulance') {
        vWidth = 2.4 * scale;
        vLength = 6.2 * scale;
        fillColor = '#ff334b';
        strokeColor = '#ffffff';

        const flash = Math.sin(Date.now() * 0.02) > 0;
        ctx.shadowColor = flash ? '#00f0ff' : '#ff334b';
        ctx.shadowBlur = 18;
    } else if (type === 'bus') {
        vWidth = 2.6 * scale;
        vLength = 11.5 * scale;
        fillColor = '#3b82f6';
        strokeColor = '#93c5fd';
        ctx.shadowColor = '#3b82f6';
        ctx.shadowBlur = 8;
    } else if (type === 'autorickshaw') {
        vWidth = 1.6 * scale;
        vLength = 2.8 * scale;
        fillColor = '#10b981';
        strokeColor = '#facc15';
        ctx.shadowColor = '#10b981';
        ctx.shadowBlur = 6;
    } else {
        ctx.shadowColor = '#ffd028';
        ctx.shadowBlur = 4;
    }

    if (isHovered) {
        ctx.shadowColor = '#00f0ff';
        ctx.shadowBlur = 24;
    }

    // Vehicle Body
    ctx.fillStyle = fillColor;
    ctx.fillRect(-vWidth / 2, -vLength / 2, vWidth, vLength);
    ctx.strokeStyle = strokeColor;
    ctx.lineWidth = 1.2;
    ctx.strokeRect(-vWidth / 2, -vLength / 2, vWidth, vLength);

    // Windshield
    ctx.fillStyle = '#0f172a';
    ctx.fillRect(-vWidth / 2 + 1, -vLength / 2 + 1, vWidth - 2, Math.max(2, vLength * 0.2));

    // Headlights Beam
    ctx.fillStyle = 'rgba(255, 255, 200, 0.4)';
    ctx.beginPath();
    ctx.moveTo(-vWidth / 3, -vLength / 2);
    ctx.lineTo(-vWidth / 2 - 4, -vLength / 2 - 12);
    ctx.lineTo(vWidth / 2 + 4, -vLength / 2 - 12);
    ctx.lineTo(vWidth / 3, -vLength / 2);
    ctx.closePath();
    ctx.fill();

    // Ambulance Siren Bulb
    if (type === 'ambulance') {
        const sirenColor = Math.sin(Date.now() * 0.03) > 0 ? '#00f0ff' : '#ff334b';
        ctx.beginPath();
        ctx.arc(0, 0, Math.max(2, vWidth * 0.25), 0, Math.PI * 2);
        ctx.fillStyle = sirenColor;
        ctx.fill();
    }

    ctx.restore();
}

// Initialize
connectWebSocket();
renderCanvas();
