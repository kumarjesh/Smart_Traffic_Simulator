import asyncio
import websockets
import json
import urllib.request
import sys

if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

async def test_all():
    print("--- 1. Testing REST Endpoints ---")
    req = urllib.request.Request(
        "http://127.0.0.1:8000/api/weather",
        data=json.dumps({"heavy_rain": True}).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req) as response:
        res = json.loads(response.read().decode())
        print("Weather toggle response:", res)

    # Spawn Ambulance
    req2 = urllib.request.Request(
        "http://127.0.0.1:8000/api/spawn",
        data=json.dumps({"vtype": "ambulance", "origin": "East", "destination": "West"}).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req2) as response:
        res2 = json.loads(response.read().decode())
        print("Ambulance spawn response:", res2)

    print("\n--- 2. Testing Real-Time WebSocket Telemetry ---")
    async with websockets.connect("ws://127.0.0.1:8000/ws") as ws:
        for i in range(8):
            msg = await ws.recv()
            data = json.loads(msg)
            print(f"Step {i+1}: Time={data['sim_time']}s | Phase={data['current_phase']} | "
                  f"Preemption={data['preemption_active']} | "
                  f"Vehicles={data['vehicle_count']} | "
                  f"Radar(NS={data['radar_density']['NS']}, EW={data['radar_density']['EW']}) | "
                  f"Rain={data['heavy_rain']}")
            await asyncio.sleep(0.4)

    print("\n✅ All Endpoints and WebSocket Telemetry Streams are fully functional!")

if __name__ == "__main__":
    asyncio.run(test_all())
