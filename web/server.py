import os
import sys
import asyncio
import json
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel

if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

from controller.smart_controller import SmartTrafficController

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SUMOCFG_PATH = os.path.join(BASE_DIR, "sumo_config", "simulation.sumocfg")
WEB_DIR = os.path.join(BASE_DIR, "web", "static")

controller = None
sim_task = None
connected_clients = set()
is_paused = False
sim_speed = 1.0 # Multiplier

async def simulation_loop():
    global controller, is_paused, sim_speed
    print("[SERVER] TraCI simulation loop ready (on-demand mode).")
    while True:
        if controller and controller.is_running:
            if not is_paused and connected_clients:
                try:
                    controller.step()
                except Exception as e:
                    print(f"[SIM ERROR] {e}. Auto-restarting simulation...")
                    try:
                        controller.stop()
                        controller.start()
                    except Exception as err:
                        print(f"[RESTART ERROR] {err}")
                    await asyncio.sleep(1.0)
                    continue

                # Broadcast state to all connected websocket clients
                state = controller.get_simulation_state()
                state_json = json.dumps(state)
                disconnected = set()
                for ws in list(connected_clients):
                    try:
                        await ws.send_text(state_json)
                    except Exception:
                        disconnected.add(ws)
                for ws in disconnected:
                    connected_clients.discard(ws)

                # Delay to throttle loop based on simulation step length and speed
                step_delay = max(0.01, (controller.step_length / sim_speed))
                await asyncio.sleep(step_delay)
            else:
                # Idle sleeping when no browsers are connected to save CPU & RAM on Free tier
                await asyncio.sleep(0.5)
        else:
            await asyncio.sleep(0.5)

async def init_controller():
    global controller, sim_task
    print("[SERVER] Initializing SmartTrafficController in background...")
    try:
        controller = SmartTrafficController(SUMOCFG_PATH, use_gui=False, step_length=0.2)
        controller.start()
        print("[SERVER] SmartTrafficController initialized successfully.")
        sim_task = asyncio.create_task(simulation_loop())
    except Exception as e:
        print(f"[SERVER ERROR] Failed to start controller: {e}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize controller in background so HTTP health checks respond immediately (0s delay)
    asyncio.create_task(init_controller())
    yield
    # Shutdown
    global sim_task, controller
    if sim_task:
        sim_task.cancel()
    if controller:
        controller.stop()

app = FastAPI(title="Smart Traffic Management System", lifespan=lifespan)

# Mount static files
os.makedirs(WEB_DIR, exist_ok=True)
app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")

@app.api_route("/", methods=["GET", "HEAD"])
async def get_index():
    index_file = os.path.join(WEB_DIR, "index.html")
    return FileResponse(index_file)

@app.api_route("/style.css", methods=["GET", "HEAD"])
async def get_style():
    return FileResponse(os.path.join(WEB_DIR, "style.css"))

@app.api_route("/app.js", methods=["GET", "HEAD"])
async def get_script():
    return FileResponse(os.path.join(WEB_DIR, "app.js"))

@app.api_route("/healthz", methods=["GET", "HEAD"])
async def healthz():
    return {"status": "ok"}

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    connected_clients.add(websocket)
    try:
        if controller and controller.is_running:
            await websocket.send_text(json.dumps(controller.get_simulation_state()))
        while True:
            data = await websocket.receive_text()
            cmd = json.loads(data)
            action = cmd.get("action")
            
            if action == "toggle_weather":
                rain = cmd.get("heavy_rain")
                controller.toggle_weather(rain)
            elif action == "spawn_vehicle":
                vtype = cmd.get("vtype", "ambulance")
                origin = cmd.get("origin", "North")
                dest = cmd.get("destination", "South")
                controller.inject_vehicle(vtype, origin, dest)
            elif action == "pause_resume":
                global is_paused
                is_paused = not is_paused
            elif action == "set_speed":
                global sim_speed
                sim_speed = float(cmd.get("speed", 1.0))
            elif action == "restart":
                if controller:
                    controller.stop()
                    controller.start()
    except WebSocketDisconnect:
        connected_clients.discard(websocket)
    except Exception as e:
        connected_clients.discard(websocket)

class WeatherRequest(BaseModel):
    heavy_rain: bool

class SpawnRequest(BaseModel):
    vtype: str = "ambulance"
    origin: str = "North"
    destination: str = "South"

@app.post("/api/weather")
async def api_weather(req: WeatherRequest):
    if controller:
        controller.toggle_weather(req.heavy_rain)
        return {"status": "ok", "heavy_rain": controller.heavy_rain}
    return {"error": "controller not initialized"}

@app.post("/api/spawn")
async def api_spawn(req: SpawnRequest):
    if controller:
        vid = controller.inject_vehicle(req.vtype, req.origin, req.destination)
        return {"status": "ok", "vehicle_id": vid}
    return {"error": "controller not initialized"}

@app.post("/api/restart")
async def api_restart():
    global controller
    if controller:
        controller.stop()
        controller.start()
        return {"status": "ok", "message": "Simulation restarted"}
    return {"error": "controller not initialized"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("web.server:app", host="0.0.0.0", port=8000, reload=False)
