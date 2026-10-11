import os
import sys
import time
import math

if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

import sumolib
import traci

# 4-Phase Isolated Approach Signal Phasing for Indian Left-Hand Traffic (LHD)
# Exactly ONE Approach Signal is GREEN at any given time to eliminate all right-turn and cross-junction conflicts!
# Links (16 total):
# South (0..3): 0=FreeLeft(G), 1=Straight(G), 2=Straight(G), 3=Right(G)
# East  (4..7): 4=FreeLeft(G), 5=Straight(G), 6=Straight(G), 7=Right(G)
# North (8..11): 8=FreeLeft(G), 9=Straight(G), 10=Straight(G), 11=Right(G)
# West  (12..15): 12=FreeLeft(G), 13=Straight(G), 14=Straight(G), 15=Right(G)

PHASE_SOUTH_GREEN  = "GGGGGrrrGrrrGrrr"  # South ONLY Green (Free lefts open on all arms)
PHASE_SOUTH_YELLOW = "GyyyGrrrGrrrGrrr"  # South Yellow
PHASE_ALL_RED      = "GrrrGrrrGrrrGrrr"  # All-Red Clearance (Flushes junction between transitions)

PHASE_NORTH_GREEN  = "GrrrGrrrGGGGGrrr"  # North ONLY Green
PHASE_NORTH_YELLOW = "GrrrGrrrGyyyGrrr"  # North Yellow

PHASE_EAST_GREEN   = "GrrrGGGGGrrrGrrr"  # East ONLY Green
PHASE_EAST_YELLOW  = "GrrrGyyyGrrrGrrr"  # East Yellow

PHASE_WEST_GREEN   = "GrrrGrrrGrrrGGGG"  # West ONLY Green
PHASE_WEST_YELLOW  = "GrrrGrrrGrrrGyyy"  # West Yellow

PHASE_CYCLE_ORDER = ["SOUTH", "NORTH", "EAST", "WEST"]

EDGE_NORTH = "N2C"
EDGE_SOUTH = "S2C"
EDGE_EAST  = "E2C"
EDGE_WEST  = "W2C"

EDGE_TO_ARM = {
    EDGE_NORTH: "NORTH",
    EDGE_SOUTH: "SOUTH",
    EDGE_EAST:  "EAST",
    EDGE_WEST:  "WEST"
}
INCOMING_EDGES = [EDGE_NORTH, EDGE_SOUTH, EDGE_EAST, EDGE_WEST]

class SmartTrafficController:
    def __init__(self, sumocfg_path, use_gui=False, step_length=0.2):
        self.sumocfg_path = sumocfg_path
        self.use_gui = use_gui
        self.step_length = step_length
        self.tls_id = "center"

        # 4-Phase Isolated Approach State Machine
        self.current_arm_idx = 0         # 0=SOUTH, 1=NORTH, 2=EAST, 3=WEST
        self.current_phase = "SOUTH_GREEN"
        self.phase_timer = 0.0           # Seconds spent in current phase
        self.target_green_duration = 12.0 # Dynamically set by radar density
        
        # Weather Integration
        self.heavy_rain = False
        self.base_yellow_time = 3.0
        self.rain_yellow_time = 5.0      # +2.0s during heavy rain
        self.all_red_time = 1.5          # 1.5s clearance between every phase
        self.normal_speed = 13.89        # 50 km/h
        self.rain_speed = 9.72           # 35 km/h

        # Sensor Density (100m Radar)
        self.radar_density = {"North": 0, "South": 0, "East": 0, "West": 0, "NS": 0, "EW": 0}
        self.calculated_green = {"North": 12.0, "South": 12.0, "East": 12.0, "West": 12.0}

        # Emergency Preemption State Machine
        self.preemption_active = False
        self.preempted_corridor = None   # "SOUTH", "NORTH", "EAST", "WEST"
        self.active_ambulance_id = None
        self.preemption_hold_time = 0.0
        self.preemption_state = "IDLE"   # "IDLE", "TRANSITION_YELLOW", "TRANSITION_ALL_RED", "LOCKED_GREEN"
        self.preemption_timer = 0.0
        self.spawn_counter = 0

        # Transit Signal Priority (TSP)
        self.tsp_active = False
        self.active_bus_ids = set()
        self.tsp_extended_time = 0.0

        # Logs buffer
        self.logs = []
        self.is_running = False
        self.sim_time = 0.0

    def log_event(self, category, message, highlight="info"):
        timestamp = f"{self.sim_time:06.1f}s"
        log_entry = {
            "time": timestamp,
            "sim_seconds": self.sim_time,
            "category": category,
            "message": message,
            "highlight": highlight
        }
        self.logs.append(log_entry)
        if len(self.logs) > 500:
            self.logs.pop(0)

        colors = {
            "emergency": "\033[91m", # Red
            "tsp": "\033[94m",       # Blue
            "radar": "\033[92m",     # Green
            "weather": "\033[93m",   # Yellow
            "info": "\033[97m"       # White
        }
        reset = "\033[0m"
        color = colors.get(category.lower(), colors["info"])
        print(f"{color}[{timestamp}] [{category.upper()}] {message}{reset}")

    def start(self):
        binary = sumolib.checkBinary("sumo-gui" if self.use_gui else "sumo")
        sumo_cmd = [
            binary,
            "-c", self.sumocfg_path,
            "--step-length", str(self.step_length),
            "--start", "true",
            "--quit-on-end", "true"
        ]
        traci.start(sumo_cmd)
        self.is_running = True
        self.apply_weather_settings(initial=True)
        self.set_tls_phase("SOUTH_GREEN")
        self.log_event("info", "4-Phase Isolated Signal Control active (1 Exclusive Green Arm at a time).", "info")

    def stop(self):
        if self.is_running:
            try:
                traci.close()
            except Exception:
                pass
            self.is_running = False
            self.log_event("info", "TraCI connection closed.", "info")

    def toggle_weather(self, enable_rain=None):
        if enable_rain is None:
            self.heavy_rain = not self.heavy_rain
        else:
            self.heavy_rain = enable_rain

        self.apply_weather_settings()

    def apply_weather_settings(self, initial=False):
        target_speed = self.rain_speed if self.heavy_rain else self.normal_speed
        for edge in INCOMING_EDGES:
            for lane_idx in range(3):
                lane_id = f"{edge}_{lane_idx}"
                try:
                    traci.lane.setMaxSpeed(lane_id, target_speed)
                except Exception:
                    pass

        veh_ids = traci.vehicle.getIDList()
        for vid in veh_ids:
            try:
                traci.vehicle.setSpeed(vid, min(traci.vehicle.getSpeed(vid), target_speed))
            except Exception:
                pass

        yellow_dur = self.rain_yellow_time if self.heavy_rain else self.base_yellow_time
        speed_kmh = target_speed * 3.6
        status_text = "HEAVY RAIN ACTIVE" if self.heavy_rain else "CLEAR / NORMAL WEATHER"
        self.log_event("weather", f"{status_text} -> Speed: {speed_kmh:.0f} km/h | Yellow Clearance: {yellow_dur:.1f}s (+2s rain buffer)", "weather")

    def get_current_yellow_time(self):
        return self.rain_yellow_time if self.heavy_rain else self.base_yellow_time

    def set_tls_phase(self, phase_name):
        self.current_phase = phase_name
        self.phase_timer = 0.0
        if phase_name == "SOUTH_GREEN":
            traci.trafficlight.setRedYellowGreenState(self.tls_id, PHASE_SOUTH_GREEN)
        elif phase_name == "SOUTH_YELLOW":
            traci.trafficlight.setRedYellowGreenState(self.tls_id, PHASE_SOUTH_YELLOW)
        elif phase_name == "NORTH_GREEN":
            traci.trafficlight.setRedYellowGreenState(self.tls_id, PHASE_NORTH_GREEN)
        elif phase_name == "NORTH_YELLOW":
            traci.trafficlight.setRedYellowGreenState(self.tls_id, PHASE_NORTH_YELLOW)
        elif phase_name == "EAST_GREEN":
            traci.trafficlight.setRedYellowGreenState(self.tls_id, PHASE_EAST_GREEN)
        elif phase_name == "EAST_YELLOW":
            traci.trafficlight.setRedYellowGreenState(self.tls_id, PHASE_EAST_YELLOW)
        elif phase_name == "WEST_GREEN":
            traci.trafficlight.setRedYellowGreenState(self.tls_id, PHASE_WEST_GREEN)
        elif phase_name == "WEST_YELLOW":
            traci.trafficlight.setRedYellowGreenState(self.tls_id, PHASE_WEST_YELLOW)
        else:
            # ALL_RED clearance
            traci.trafficlight.setRedYellowGreenState(self.tls_id, PHASE_ALL_RED)

    def scan_radar_sensors(self):
        radar_range = 100.0
        counts = {"North": 0, "South": 0, "East": 0, "West": 0}

        veh_ids = traci.vehicle.getIDList()
        for vid in veh_ids:
            try:
                edge = traci.vehicle.getRoadID(vid)
                if edge in INCOMING_EDGES:
                    lane_pos = traci.vehicle.getLanePosition(vid)
                    lane_len = traci.lane.getLength(f"{edge}_0")
                    dist_to_stopline = lane_len - lane_pos

                    if 0 <= dist_to_stopline <= radar_range:
                        if edge == EDGE_NORTH:
                            counts["North"] += 1
                        elif edge == EDGE_SOUTH:
                            counts["South"] += 1
                        elif edge == EDGE_EAST:
                            counts["East"] += 1
                        elif edge == EDGE_WEST:
                            counts["West"] += 1
            except Exception:
                pass

        self.radar_density = {
            "North": counts["North"],
            "South": counts["South"],
            "East": counts["East"],
            "West": counts["West"],
            "NS": counts["North"] + counts["South"],
            "EW": counts["East"] + counts["West"]
        }

        min_green = 8.0
        max_green = 22.0
        total_veh = max(1, sum(counts.values()))

        for arm in ["North", "South", "East", "West"]:
            ratio = counts[arm] / total_veh
            self.calculated_green[arm] = round(min_green + (max_green - min_green) * min(1.0, ratio * 2.5), 1)

    def detect_emergency_vehicles(self):
        """Feature 1: Automated Emergency Preemption for 4-Phase Isolated Control"""
        preemption_dist = 160.0
        active_ambulance = None
        amb_edge = None
        amb_dist = None

        all_veh = traci.vehicle.getIDList()

        if self.preemption_active and self.active_ambulance_id:
            if self.active_ambulance_id not in all_veh:
                active_ambulance = None
            else:
                road = traci.vehicle.getRoadID(self.active_ambulance_id)
                if road not in INCOMING_EDGES:
                    active_ambulance = None
                else:
                    lane_pos = traci.vehicle.getLanePosition(self.active_ambulance_id)
                    lane_len = traci.lane.getLength(f"{road}_0")
                    dist = lane_len - lane_pos
                    if dist <= 3.0:
                        active_ambulance = None
                    else:
                        active_ambulance = self.active_ambulance_id
                        amb_edge = road
                        amb_dist = dist

        if not active_ambulance:
            for vid in all_veh:
                try:
                    vtype = traci.vehicle.getTypeID(vid)
                    if "ambulance" in vtype.lower():
                        edge = traci.vehicle.getRoadID(vid)
                        if edge in INCOMING_EDGES:
                            lane_pos = traci.vehicle.getLanePosition(vid)
                            lane_len = traci.lane.getLength(f"{edge}_0")
                            dist = lane_len - lane_pos
                            if 0 <= dist <= preemption_dist:
                                active_ambulance = vid
                                amb_edge = edge
                                amb_dist = dist
                                break
                except Exception:
                    pass

        yellow_dur = self.get_current_yellow_time()

        if active_ambulance:
            arm_name = EDGE_TO_ARM.get(amb_edge, "SOUTH")
            desired_green = f"{arm_name}_GREEN"

            if not self.preemption_active:
                self.preemption_active = True
                self.active_ambulance_id = active_ambulance
                self.preempted_corridor = arm_name
                self.preemption_hold_time = 0.0
                self.log_event("emergency", f"AMBULANCE '{active_ambulance}' on {arm_name} approach ({amb_dist:.1f}m). Locking exclusive GREEN for {arm_name}.", "emergency")

                if self.current_phase == desired_green:
                    self.preemption_state = "LOCKED_GREEN"
                    self.phase_timer = 0.0
                else:
                    # Switch current green arm to yellow
                    current_arm = self.current_phase.split("_")[0]
                    if "GREEN" in self.current_phase:
                        self.set_tls_phase(f"{current_arm}_YELLOW")
                    self.preemption_state = "TRANSITION_YELLOW"
                    self.preemption_timer = 0.0
            else:
                self.preemption_hold_time += self.step_length
                self.preemption_timer += self.step_length

                if self.preemption_state == "TRANSITION_YELLOW":
                    if self.preemption_timer >= yellow_dur:
                        self.set_tls_phase("ALL_RED")
                        self.preemption_state = "TRANSITION_ALL_RED"
                        self.preemption_timer = 0.0
                        self.log_event("info", f"Emergency Clearance ({self.all_red_time}s All-Red) -> Flushing intersection for {arm_name} ambulance.", "info")

                elif self.preemption_state == "TRANSITION_ALL_RED":
                    if self.preemption_timer >= self.all_red_time:
                        self.set_tls_phase(desired_green)
                        self.preemption_state = "LOCKED_GREEN"
                        self.preemption_timer = 0.0
                        self.log_event("emergency", f"Intersection clear. LOCKED {desired_green} exclusive corridor for ambulance.", "emergency")

                elif self.preemption_state == "LOCKED_GREEN":
                    if self.current_phase != desired_green:
                        self.set_tls_phase(desired_green)
                    self.phase_timer = 0.0

                    if self.preemption_hold_time >= 20.0:
                        self.log_event("emergency", f"Ambulance '{self.active_ambulance_id}' preemption hold limit reached (20s). Resuming dynamic 4-phase cycle.", "emergency")
                        self.preemption_active = False
                        self.active_ambulance_id = None
                        self.preempted_corridor = None
                        self.preemption_state = "IDLE"
        else:
            if self.preemption_active:
                self.log_event("emergency", f"Ambulance '{self.active_ambulance_id}' cleared junction. RELEASING PREEMPTION -> Resuming 4-phase dynamic cycle.", "emergency")
                self.preemption_active = False
                self.active_ambulance_id = None
                self.preempted_corridor = None
                self.preemption_state = "IDLE"
                self.preemption_hold_time = 0.0

    def detect_transit_priority(self):
        tsp_detection_range = 80.0
        bus_info = []

        for vid in traci.vehicle.getIDList():
            try:
                vtype = traci.vehicle.getTypeID(vid)
                if "bus" in vtype.lower():
                    edge = traci.vehicle.getRoadID(vid)
                    if edge in INCOMING_EDGES:
                        lane_pos = traci.vehicle.getLanePosition(vid)
                        lane_len = traci.lane.getLength(f"{edge}_0")
                        dist = lane_len - lane_pos
                        if 0 <= dist <= tsp_detection_range:
                            arm_name = EDGE_TO_ARM.get(edge, "SOUTH")
                            bus_info.append((vid, arm_name, dist, edge))
            except Exception:
                pass

        if bus_info and not self.preemption_active:
            for vid, arm_name, dist, edge in bus_info:
                if vid not in self.active_bus_ids:
                    self.active_bus_ids.add(vid)
                    desired_green = f"{arm_name}_GREEN"
                    
                    if self.current_phase == desired_green:
                        if (self.target_green_duration - self.phase_timer) < 6.0:
                            self.target_green_duration += 5.0
                            self.tsp_extended_time += 5.0
                            self.log_event("tsp", f"Bus '{vid}' on {arm_name} ({dist:.1f}m) approaching GREEN -> EXTENDING GREEN by +5.0s (New target: {self.target_green_duration:.1f}s)", "tsp")
                    else:
                        if "GREEN" in self.current_phase and self.phase_timer < self.target_green_duration:
                            reduced_duration = max(self.phase_timer + 2.0, 5.0)
                            if self.target_green_duration > reduced_duration:
                                self.target_green_duration = reduced_duration
                                self.log_event("tsp", f"Bus '{vid}' on {arm_name} ({dist:.1f}m) waiting -> SHORTENING OTHER PHASE (Switching in {reduced_duration - self.phase_timer:.1f}s)", "tsp")

        try:
            active_on_road = set(traci.vehicle.getIDList())
            self.active_bus_ids = {b for b in self.active_bus_ids if b in active_on_road}
        except Exception:
            pass

    def step(self):
        traci.simulationStep()
        self.sim_time = traci.simulation.getTime()
        self.phase_timer += self.step_length

        self.scan_radar_sensors()
        self.detect_emergency_vehicles()
        self.detect_transit_priority()

        yellow_duration = self.get_current_yellow_time()

        if self.preemption_active:
            return

        current_arm = PHASE_CYCLE_ORDER[self.current_arm_idx]

        # 4-Phase Sequential Progression: (ARM_GREEN -> ARM_YELLOW -> ALL_RED -> NEXT_ARM_GREEN)
        if self.current_phase == f"{current_arm}_GREEN":
            arm_capital = current_arm.capitalize()
            if self.target_green_duration == 12.0 or self.phase_timer < 1.0:
                self.target_green_duration = self.calculated_green.get(arm_capital, 12.0)

            if self.phase_timer >= self.target_green_duration:
                self.set_tls_phase(f"{current_arm}_YELLOW")
                self.log_event("radar", f"{current_arm} Green completed ({self.phase_timer:.1f}s). Switching to {current_arm} YELLOW ({yellow_duration:.1f}s).", "radar")

        elif self.current_phase == f"{current_arm}_YELLOW":
            if self.phase_timer >= yellow_duration:
                self.set_tls_phase("ALL_RED")
                self.log_event("info", f"ALL-RED Clearance Interval ({self.all_red_time}s) -> Flushing intersection before next arm.", "info")

        elif self.current_phase == "ALL_RED":
            if self.phase_timer >= self.all_red_time:
                # Advance to next arm in cycle
                self.current_arm_idx = (self.current_arm_idx + 1) % len(PHASE_CYCLE_ORDER)
                next_arm = PHASE_CYCLE_ORDER[self.current_arm_idx]
                next_capital = next_arm.capitalize()
                self.set_tls_phase(f"{next_arm}_GREEN")
                self.target_green_duration = self.calculated_green.get(next_capital, 12.0)
                self.log_event("radar", f"{next_arm} EXCLUSIVE GREEN activated for {self.target_green_duration:.1f}s (Radar queue: {self.radar_density.get(next_capital, 0)} veh).", "radar")

    def inject_vehicle(self, vtype, origin="North", destination="South"):
        route_map = {
            ("North", "South"): "r_N_S",
            ("North", "East"): "r_N_E",
            ("North", "West"): "r_N_W",
            ("South", "North"): "r_S_N",
            ("South", "West"): "r_S_W",
            ("South", "East"): "r_S_E",
            ("East", "West"): "r_E_W",
            ("East", "South"): "r_E_S",
            ("East", "North"): "r_E_N",
            ("West", "East"): "r_W_E",
            ("West", "North"): "r_W_N",
            ("West", "South"): "r_W_S",
        }
        route_id = route_map.get((origin, destination), "r_N_S")
        self.spawn_counter += 1
        vid = f"{vtype}_{int(self.sim_time * 10)}_{self.spawn_counter}_{origin[0]}"
        try:
            color = (255, 30, 30, 255) if vtype == "ambulance" else (30, 144, 255, 255)
            # Spawn at pos 0.0 (the very beginning of the incoming approach road - 250m away from junction)
            # Use departLane="free" to guarantee immediate entry without queue blocking at the spawn point
            traci.vehicle.add(vid, route_id, typeID=vtype, depart="now", departPos="0.0", departSpeed="max", departLane="free")
            traci.vehicle.setColor(vid, color)
            traci.vehicle.setSpeedMode(vid, 31)
            
            if vtype == "ambulance":
                traci.vehicle.setMaxSpeed(vid, 22.2) # ~80 km/h emergency response speed
                traci.vehicle.setImperfection(vid, 0.0)
                traci.vehicle.setTau(vid, 0.8)
                self.log_event("emergency", f"🚨 DISPATCHED AMBULANCE '{vid}' at start of {origin} approach road (250m from junction).", "emergency")
            elif vtype == "bus":
                traci.vehicle.setMaxSpeed(vid, 11.1) # 40 km/h
                self.log_event("tsp", f"🚌 INJECTED TRANSIT BUS '{vid}' on {origin} approach road (250m from junction).", "tsp")
            else:
                self.log_event("info", f"Spawned {vtype.upper()} '{vid}' on {origin} approach.", "info")
            return vid
        except Exception as e:
            self.log_event("info", f"Failed to inject vehicle: {e}", "info")
            return None

    def get_simulation_state(self):
        vehicles_data = []
        try:
            for vid in traci.vehicle.getIDList():
                pos = traci.vehicle.getPosition(vid)
                angle = traci.vehicle.getAngle(vid)
                speed = traci.vehicle.getSpeed(vid) * 3.6
                vtype = traci.vehicle.getTypeID(vid)
                edge = traci.vehicle.getRoadID(vid)
                
                type_category = "passenger"
                if "ambulance" in vtype.lower():
                    type_category = "ambulance"
                elif "bus" in vtype.lower():
                    type_category = "bus"
                elif "auto" in vtype.lower() or "rickshaw" in vtype.lower():
                    type_category = "autorickshaw"

                vehicles_data.append({
                    "id": vid,
                    "type": type_category,
                    "x": round(pos[0], 2),
                    "y": round(pos[1], 2),
                    "angle": round(angle, 1),
                    "speed": round(speed, 1),
                    "edge": edge
                })
        except Exception:
            pass

        return {
            "sim_time": round(self.sim_time, 1),
            "current_phase": self.current_phase,
            "phase_timer": round(self.phase_timer, 1),
            "target_green": round(self.target_green_duration, 1),
            "yellow_duration": round(self.get_current_yellow_time(), 1),
            "heavy_rain": self.heavy_rain,
            "preemption_active": self.preemption_active,
            "preempted_corridor": self.preempted_corridor,
            "active_ambulance_id": self.active_ambulance_id,
            "active_buses": list(self.active_bus_ids),
            "radar_density": self.radar_density,
            "calculated_green": self.calculated_green,
            "vehicle_count": len(vehicles_data),
            "vehicles": vehicles_data,
            "recent_logs": self.logs[-15:]
        }
