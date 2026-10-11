import os
import sys
import time
import argparse

# Ensure UTF-8 output on Windows terminal
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

from controller.smart_controller import SmartTrafficController

def main():
    parser = argparse.ArgumentParser(description="Smart Traffic Management TraCI Simulation")
    parser.add_argument("--gui", action="store_true", help="Run with SUMO GUI")
    parser.add_argument("--steps", type=int, default=350, help="Number of simulation steps to run")
    parser.add_argument("--rain-at", type=int, default=60, help="Simulation time in seconds to toggle Heavy Rain on")
    parser.add_argument("--step-length", type=float, default=0.2, help="Simulation step length in seconds")
    parser.add_argument("--delay", type=float, default=0.02, help="Delay per step in seconds for terminal visual readability")
    args = parser.parse_args()

    base_dir = os.path.dirname(os.path.abspath(__file__))
    sumocfg_path = os.path.join(base_dir, "sumo_config", "simulation.sumocfg")

    print("\n" + "="*80)
    print("🚦 ECLIPSE SUMO + TraCI SMART TRAFFIC CONTROLLER")
    print("="*80)
    print("Features Active:")
    print("  [1] Automated Emergency Preemption (Ambulance Green Lock)")
    print("  [2] Transit Signal Priority / TSP (Bus Green Extension / Red Truncation)")
    print("  [3] 100m Radar/Thermal Sensor Simulation (Dynamic Density-Based Green Split)")
    print("  [4] Predictive Weather Integration (Rain toggle -> Yellow buffer +2s, Speed throttled)")
    print("="*80 + "\n")

    controller = SmartTrafficController(sumocfg_path, use_gui=args.gui, step_length=args.step_length)
    controller.start()

    rain_toggled = False
    try:
        step_count = 0
        total_steps = int(args.steps / args.step_length) if args.steps > 0 else 9999999
        
        while step_count < total_steps and controller.is_running:
            controller.step()
            sim_time = controller.sim_time

            # Feature 4 test: Trigger rain at designated time
            if args.rain_at > 0 and sim_time >= args.rain_at and not rain_toggled:
                rain_toggled = True
                print("\n🌧️ [SIMULATION EVENT] Activating Heavy Rain condition...")
                controller.toggle_weather(enable_rain=True)

            if args.delay > 0:
                time.sleep(args.delay)
            step_count += 1

    except KeyboardInterrupt:
        print("\n[INFO] Simulation interrupted by user.")
    finally:
        controller.stop()
        print("\n" + "="*80)
        print("✅ SIMULATION COMPLETE")
        print(f"Total simulated time: {controller.sim_time:.1f}s")
        print("="*80 + "\n")

if __name__ == "__main__":
    main()
