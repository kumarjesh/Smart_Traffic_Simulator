import os
import subprocess
import sumolib

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

NODES_XML = os.path.join(BASE_DIR, "junction.nod.xml")
EDGES_XML = os.path.join(BASE_DIR, "junction.edg.xml")
TYPES_XML = os.path.join(BASE_DIR, "junction.typ.xml")
CONNECTIONS_XML = os.path.join(BASE_DIR, "junction.con.xml")
NET_XML = os.path.join(BASE_DIR, "junction.net.xml")

def create_network_files():
    # 1. Nodes (Center junction at 0,0 with generous 25m radius for clear visualization)
    with open(NODES_XML, "w") as f:
        f.write('''<nodes>
    <node id="center" x="0.0" y="0.0" type="traffic_light" radius="25.0"/>
    <node id="north" x="0.0" y="250.0" type="priority"/>
    <node id="south" x="0.0" y="-250.0" type="priority"/>
    <node id="east" x="250.0" y="0.0" type="priority"/>
    <node id="west" x="-250.0" y="0.0" type="priority"/>
</nodes>''')

    # 2. Edge types: 3 Lanes (Lane 0: Dedicated Free Left, Lane 1: Straight, Lane 2: Straight/Right)
    with open(TYPES_XML, "w") as f:
        f.write('''<types>
    <type id="urban_3lane" numLanes="3" speed="13.89"/>
</types>''')

    # 3. Edges
    with open(EDGES_XML, "w") as f:
        f.write('''<edges>
    <!-- Incoming to center (3 lanes) -->
    <edge id="N2C" from="north" to="center" type="urban_3lane" priority="2"/>
    <edge id="S2C" from="south" to="center" type="urban_3lane" priority="2"/>
    <edge id="E2C" from="east" to="center" type="urban_3lane" priority="2"/>
    <edge id="W2C" from="west" to="center" type="urban_3lane" priority="2"/>

    <!-- Outgoing from center (3 lanes) -->
    <edge id="C2N" from="center" to="north" type="urban_3lane" priority="2"/>
    <edge id="C2S" from="center" to="south" type="urban_3lane" priority="2"/>
    <edge id="C2E" from="center" to="east" type="urban_3lane" priority="2"/>
    <edge id="C2W" from="center" to="west" type="urban_3lane" priority="2"/>
</edges>''')

    # 4. Indian Left-Hand Traffic Connections with DEDICATED LANES:
    # Lane 0: ONLY Free Left Turn (Dedicated Slip Lane -> No red light cross-bleed!)
    # Lane 1: Through (Straight)
    # Lane 2: Through + Right Turn
    with open(CONNECTIONS_XML, "w") as f:
        f.write('''<connections>
    <!-- From North (LHD) -->
    <connection from="N2C" to="C2E" fromLane="0" toLane="0" keepClear="true"/>
    <connection from="N2C" to="C2S" fromLane="1" toLane="1" keepClear="true"/>
    <connection from="N2C" to="C2S" fromLane="2" toLane="2" keepClear="true"/>
    <connection from="N2C" to="C2W" fromLane="2" toLane="2" keepClear="true"/>

    <!-- From South (LHD) -->
    <connection from="S2C" to="C2W" fromLane="0" toLane="0" keepClear="true"/>
    <connection from="S2C" to="C2N" fromLane="1" toLane="1" keepClear="true"/>
    <connection from="S2C" to="C2N" fromLane="2" toLane="2" keepClear="true"/>
    <connection from="S2C" to="C2E" fromLane="2" toLane="2" keepClear="true"/>

    <!-- From East (LHD) -->
    <connection from="E2C" to="C2S" fromLane="0" toLane="0" keepClear="true"/>
    <connection from="E2C" to="C2W" fromLane="1" toLane="1" keepClear="true"/>
    <connection from="E2C" to="C2W" fromLane="2" toLane="2" keepClear="true"/>
    <connection from="E2C" to="C2N" fromLane="2" toLane="2" keepClear="true"/>

    <!-- From West (LHD) -->
    <connection from="W2C" to="C2N" fromLane="0" toLane="0" keepClear="true"/>
    <connection from="W2C" to="C2E" fromLane="1" toLane="1" keepClear="true"/>
    <connection from="W2C" to="C2E" fromLane="2" toLane="2" keepClear="true"/>
    <connection from="W2C" to="C2S" fromLane="2" toLane="2" keepClear="true"/>
</connections>''')

def build_net():
    create_network_files()
    netconvert_bin = sumolib.checkBinary("netconvert")
    cmd = [
        netconvert_bin,
        "--node-files", NODES_XML,
        "--edge-files", EDGES_XML,
        "--type-files", TYPES_XML,
        "--connection-files", CONNECTIONS_XML,
        "--output-file", NET_XML,
        "--lefthand", "true",
        "--no-turnarounds", "true",
        "--tls.guess", "true",
        "--tls.default-type", "static",
        "--junctions.corner-detail", "5",
        "--no-internal-links", "false"
    ]
    print("Running netconvert for 3-lane dedicated slip-lane junction...")
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        print("Netconvert error:", res.stderr)
        raise RuntimeError(res.stderr)
    print("Network successfully generated with 3-Lane Indian LHD & Dedicated Slip Lanes:", NET_XML)

if __name__ == "__main__":
    build_net()
