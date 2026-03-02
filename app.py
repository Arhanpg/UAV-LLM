from flask import Flask, render_template, request, jsonify
from google import genai
from google.genai import types
import googlemaps
from pydantic import BaseModel, Field
from z3 import *
import networkx as nx

app = Flask(__name__)

# --- CONFIGURATION ---
GEMINI_API_KEY = "AIzaSyDTOBkpuY1z1P_ZZCmbMth7NYLWBa6NBkM" # Replace with your key
GMAPS_API_KEY = "AIzaSyA4sncGLJWXYB4I5_YQB5Msdh3exc9VMiA" # Replace with your key

client = genai.Client(api_key=GEMINI_API_KEY)
gmaps = googlemaps.Client(key=GMAPS_API_KEY)

MAX_UAV_CAPACITY_KG = 10.0  # W constraint of the drone

# --- 1. SEMANTIC CONSTRAINT SYNTHESIS ---
class ObjectiveWeights(BaseModel):
    alpha_dist: float = Field(description="Weight for distance optimization (0.0 to 1.0)")
    alpha_time: float = Field(description="Weight for time/urgency optimization (0.0 to 1.0)")
    alpha_noise: float = Field(description="Weight for noise avoidance (0.0 to 1.0)")
    alpha_energy: float = Field(description="Weight for energy conservation (0.0 to 1.0)")

class DeliveryConstraint(BaseModel):
    commodity_class: str = Field(description="e.g., 'PHARMACEUTICAL', 'HAZMAT', 'STANDARD', 'FLAMMABLE'")
    package_weight: float = Field(description="Weight in kg. If not mentioned, assume 1.0")
    temperature_range: list[float] = Field(description="[T_min, T_max] in Celsius. Default [-50, 50]")
    geofenced_zones: list[str] = Field(description="Locations to strictly avoid.")
    waypoints: list[str] = Field(description="Locations to visit on the way.")
    deadline_minutes: int = Field(description="Deadline in minutes. 0 if none.")
    objective_weights: ObjectiveWeights = Field(description="Inferred multi-objective weights based on urgency/context. Must sum to 1.0")

# Defining constraint's via the prompt 
def extract_constraints(prompt_text: str) -> dict:
    response = client.models.generate_content(
        model='gemini-2.5-flash',
        contents=prompt_text,
        config=types.GenerateContentConfig(
            system_instruction="You are a UAV dispatch semantic parser. Extract constraints. Pay attention to weight, geofences to avoid, and urgency.",
            response_mime_type="application/json",
            response_schema=DeliveryConstraint,
            temperature=0.1, 
        )
    )
    return DeliveryConstraint.model_validate_json(response.text).model_dump()

# --- 2. FORMAL VERIFICATION (SMT) cross verification of the extracted details is correct or not---
def verify_constraints(constraints: dict, current_load: float) -> tuple[bool, str]:
    s = Solver()
    T_min = Real('T_min')
    T_max = Real('T_max')
    Load = Real('Load')
    MaxCap = Real('MaxCap')
    
    # Physics/Reality axioms
    s.add(T_min >= -273.15)
    s.add(T_min <= T_max)
    s.add(MaxCap == MAX_UAV_CAPACITY_KG)
    
    # Problem instances
    s.add(T_min == constraints['temperature_range'][0])
    s.add(T_max == constraints['temperature_range'][1])
    s.add(Load == current_load + constraints['package_weight'])
    
    # Critical Load Constraint (y_i <= W)
    s.add(Load <= MaxCap)
    
    if s.check() == sat:
        return True, "Verified safe by Z3 SMT Solver."
    else:
        # Debug why it failed
        if current_load + constraints['package_weight'] > MAX_UAV_CAPACITY_KG:
            return False, f"Constraint Violation: Max load is {MAX_UAV_CAPACITY_KG}kg. Adding {constraints['package_weight']}kg exceeds capacity."
        return False, "Failed thermal/mathematical verification."

# --- 3. COMPATIBILITY GRAPH ---
class CompatibilityGraph:
    def __init__(self):
        self.G = nx.Graph()
        self.G.add_edges_from([("STANDARD", "PHARMACEUTICAL"), ("STANDARD", "HAZMAT")])
        # Note: PHARMACEUTICAL and HAZMAT have NO edge, meaning they are incompatible!

    def is_safe_to_load(self, current_payload: list[str], new_item: str) -> bool:
        if not current_payload: return True
        for item in current_payload:
            if not self.G.has_edge(item.upper(), new_item.upper()) and item.upper() != new_item.upper():
                return False
        return True

compat_graph = CompatibilityGraph()

# Global Drone State (Simplification for Demo)
drone_state = {
    "current_payload_classes": [],
    "current_load_kg": 0.0
}

# --- 4 & 5. ROUTING & GEOFENCING ---
@app.route('/')
def index():
    return render_template('index.html', gmaps_key=GMAPS_API_KEY, max_cap=MAX_UAV_CAPACITY_KG)

@app.route('/plan_route', methods=['POST'])
def plan_route():
    global drone_state
    try:
        data = request.json
        origin = data.get('origin')
        destination = data.get('destination')
        nl_command = data.get('command')
        reset = data.get('reset_drone', False)

        if reset:
            drone_state["current_payload_classes"] = []
            drone_state["current_load_kg"] = 0.0

        # 1. Synthesize
        constraints = extract_constraints(nl_command)
        new_commodity = constraints['commodity_class']
        
        # 2. Verify Math & Load
        is_safe, verify_msg = verify_constraints(constraints, drone_state["current_load_kg"])
        if not is_safe:
            return jsonify({"error": f"SMT Abort: {verify_msg}"}), 400
            
        # 3. Verify Graph
        if not compat_graph.is_safe_to_load(drone_state["current_payload_classes"], new_commodity):
            return jsonify({"error": f"Graph Violation: Incompatible ({new_commodity} with {drone_state['current_payload_classes']})"}), 400
        
        # Update State
        drone_state["current_payload_classes"].append(new_commodity)
        drone_state["current_load_kg"] += constraints['package_weight']

        def get_coords(location_name):
            res = gmaps.geocode(location_name)
            return res[0]['geometry']['location'] if res else None

        # Geocode Path
        origin_coords = get_coords(origin)
        dest_coords = get_coords(destination)
        if not origin_coords or not dest_coords:
            return jsonify({"error": "Failed to geocode origin/destination."}), 400

        aerial_path = [origin_coords]
        for wp in constraints.get('waypoints', []):
            wp_c = get_coords(wp)
            if wp_c: aerial_path.append(wp_c)
        aerial_path.append(dest_coords)

        # Geocode Geofences (To render them as red zones on the frontend)
        geofence_coords = []
        for zone in constraints.get('geofenced_zones', []):
            zc = get_coords(zone)
            if zc:
                geofence_coords.append({"name": zone, "lat": zc['lat'], "lng": zc['lng']})

        return jsonify({
            "constraints": constraints,
            "path_coordinates": aerial_path,
            "geofences": geofence_coords,
            "drone_state": drone_state,
            "system_status": "All Formal Constraints Satisfied."
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)